"""
Startup Optimization Module
Handles lazy loading, connection pooling, and startup/shutdown optimizations for Cloud Run

This module improves container startup time and resource efficiency.
"""
import asyncio
from typing import Optional
from contextlib import asynccontextmanager
from functools import lru_cache

from src.core.logging import get_logger
from src.core.config import settings

logger = get_logger(__name__)

# Global instances (lazy loaded)
_embedding_service = None
_supabase_client = None
_pgvector_manager = None


@lru_cache(maxsize=1)
def get_embedding_service_lazy():
    """
    Lazy load embedding service (only when first search is made)
    
    This prevents loading the model during container startup,
    reducing cold start time significantly.
    
    Returns:
        EmbeddingService instance
    """
    global _embedding_service
    
    if _embedding_service is None:
        logger.info("Lazy loading embedding service...")
        
        if settings.EMBEDDING_PROVIDER == "openai":
            from src.indexing.embeddings import get_embedding_service
            _embedding_service = get_embedding_service()
            logger.info("OpenAI embedding service loaded")
        else:
            from src.indexing.embeddings_sentence_transformers import get_sentence_transformers_service
            _embedding_service = get_sentence_transformers_service()
            logger.info("Sentence Transformers embedding service loaded")
    
    return _embedding_service


@lru_cache(maxsize=1)
def get_supabase_client_lazy():
    """
    Lazy load Supabase client with connection pooling
    
    Returns:
        SupabaseClient instance
    """
    global _supabase_client
    
    if _supabase_client is None:
        logger.info("Lazy loading Supabase client...")
        from src.database.supabase import get_supabase_client
        _supabase_client = get_supabase_client()
        logger.info("Supabase client loaded")
    
    return _supabase_client


@lru_cache(maxsize=1)
def get_pgvector_manager_lazy():
    """
    Lazy load PgVector manager with connection pooling
    
    Returns:
        PgVectorManager instance
    """
    global _pgvector_manager
    
    if _pgvector_manager is None:
        logger.info("Lazy loading PgVector manager...")
        from src.database.pgvector import get_pgvector_manager
        _pgvector_manager = get_pgvector_manager()
        logger.info("PgVector manager loaded")
    
    return _pgvector_manager


async def warmup_services():
    """
    Warm up critical services in the background
    
    This is called after the container starts to pre-load
    services without blocking the initial health check.
    """
    try:
        logger.info("Starting service warmup...")
        
        # Warm up in order of importance
        # 1. Database connections (fast)
        if settings.SUPABASE_URL:
            get_supabase_client_lazy()
        
        if settings.VECTOR_STORE == "pgvector" and settings.DATABASE_URL:
            get_pgvector_manager_lazy()
        
        # 2. Embedding service (slower, only if needed)
        # Only warm up if we're using OpenAI (fast) or if explicitly configured
        if settings.EMBEDDING_PROVIDER == "openai" or settings.__dict__.get("WARMUP_EMBEDDINGS", False):
            get_embedding_service_lazy()
        
        logger.info("Service warmup completed")
        
    except Exception as e:
        logger.warning(f"Service warmup partially failed (non-critical): {e}")


def cleanup_services():
    """
    Cleanup services on shutdown
    
    This ensures graceful shutdown and proper connection cleanup.
    """
    global _embedding_service, _supabase_client, _pgvector_manager
    
    logger.info("Cleaning up services...")
    
    try:
        # Close database connections
        if _pgvector_manager is not None:
            try:
                _pgvector_manager.close()
                logger.info("PgVector manager closed")
            except Exception as e:
                logger.warning(f"Error closing PgVector manager: {e}")
        
        # Reset globals
        _embedding_service = None
        _supabase_client = None
        _pgvector_manager = None
        
        logger.info("Service cleanup completed")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")


@asynccontextmanager
async def lifespan_manager(app):
    """
    FastAPI lifespan manager for startup and shutdown
    
    This replaces the deprecated @app.on_event("startup") and @app.on_event("shutdown")
    
    Args:
        app: FastAPI application instance
    """
    # Startup
    logger.info("Application starting up...")
    logger.info(
        "Configuration loaded",
        extra={
            "environment": settings.ENVIRONMENT,
            "vector_store": settings.VECTOR_STORE,
            "embedding_provider": settings.EMBEDDING_PROVIDER,
            "api_host": settings.API_HOST,
            "api_port": settings.API_PORT
        }
    )
    
    # Start warmup in background (non-blocking)
    asyncio.create_task(warmup_services())
    
    yield
    
    # Shutdown
    logger.info("Application shutting down...")
    cleanup_services()


# Health check utilities for Cloud Run
class HealthCheckManager:
    """Manager for health check status and readiness"""
    
    def __init__(self):
        self.ready = False
        self.startup_complete = False
    
    def mark_ready(self):
        """Mark the service as ready to receive traffic"""
        self.ready = True
        self.startup_complete = True
        logger.info("Service marked as ready")
    
    def is_ready(self) -> bool:
        """Check if service is ready"""
        return self.ready
    
    def is_healthy(self) -> bool:
        """
        Check if service is healthy
        
        For now, same as ready, but could include additional checks
        like memory usage, disk space, etc.
        """
        return self.ready


# Global health check manager
health_check_manager = HealthCheckManager()


def check_memory_usage() -> dict:
    """
    Check memory usage for health monitoring
    
    Returns:
        dict with memory stats
    """
    try:
        import psutil
        
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "memory_percent": memory.percent,
            "memory_available_mb": memory.available / (1024 * 1024),
            "disk_percent": disk.percent,
            "disk_available_gb": disk.free / (1024 * 1024 * 1024)
        }
    except ImportError:
        # psutil not available, return None
        return {}
    except Exception as e:
        logger.warning(f"Could not check memory usage: {e}")
        return {}


async def preload_model_if_needed():
    """
    Preload ML model if using Sentence Transformers
    
    This is useful for Cloud Run to avoid the first request being slow.
    Should be called after startup event.
    """
    if settings.EMBEDDING_PROVIDER == "sentence-transformers":
        try:
            logger.info("Preloading Sentence Transformers model...")
            get_embedding_service_lazy()
            logger.info("Model preloaded successfully")
        except Exception as e:
            logger.warning(f"Could not preload model: {e}")


# Connection pooling configuration for psycopg2
def get_connection_pool_config() -> dict:
    """
    Get optimal connection pool configuration for Cloud Run
    
    Returns:
        dict with connection pool settings
    """
    return {
        "min_connections": 1,
        "max_connections": 10,  # Cloud Run can handle ~10 concurrent connections per instance
        "connection_timeout": 30,
        "idle_timeout": 600,  # 10 minutes
    }
