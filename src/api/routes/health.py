"""
Health Check API Routes
Health check endpoint implementation with Cloud Run optimizations
"""
import time
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.core.logging import get_logger
from src.database.supabase import get_supabase_client
from src.database.pgvector import get_pgvector_manager

# Import Cloud Run startup utilities
try:
    from src.core.startup import check_memory_usage, health_check_manager
    STARTUP_MODULE_AVAILABLE = True
except ImportError:
    STARTUP_MODULE_AVAILABLE = False
    health_check_manager = None

logger = get_logger(__name__)

# Track startup time for monitoring
_startup_time = datetime.utcnow()

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/health/")
async def health_check():
    """
    System health check endpoint (Cloud Run compatible)
    
    Checks the health of all system components:
    - Database connection (Supabase)
    - Vector store (pgvector/Qdrant)
    - Configuration
    - Memory usage
    - Response time
    - Uptime
    
    Returns:
        dict: Health status with component details
    
    Example Response:
        ```json
        {
          "status": "healthy",
          "version": "1.0.0",
          "uptime_seconds": 3600,
          "components": {
            "database": "connected",
            "vector_store": "connected",
            "config": "valid"
          },
          "system": {
            "memory_percent": 45.2,
            "memory_available_mb": 1024.5
          }
        }
        ```
    """
    start_time = time.time()
    
    health_status = {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": (datetime.utcnow() - _startup_time).total_seconds(),
        "components": {}
    }
    
    # Check database (Supabase)
    try:
        if settings.SUPABASE_URL and settings.SUPABASE_KEY:
            supabase_client = get_supabase_client()
            if supabase_client.health_check():
                health_status["components"]["database"] = "connected"
            else:
                health_status["components"]["database"] = "disconnected"
                health_status["status"] = "degraded"
        else:
            health_status["components"]["database"] = "not_configured"
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["components"]["database"] = "error"
        health_status["components"]["database_error"] = str(e)
        health_status["status"] = "unhealthy"
        logger.error(f"Database health check failed: {e}")
    
    # Check vector store
    try:
        if settings.VECTOR_STORE == "pgvector":
            if settings.DATABASE_URL:
                pgvector_manager = get_pgvector_manager()
                # Simple check - just verify manager is initialized
                if pgvector_manager.database_url:
                    health_status["components"]["vector_store"] = "configured"
                else:
                    health_status["components"]["vector_store"] = "not_configured"
                    health_status["status"] = "degraded"
            else:
                health_status["components"]["vector_store"] = "not_configured"
                health_status["status"] = "degraded"
        elif settings.VECTOR_STORE == "qdrant":
            if settings.QDRANT_URL:
                health_status["components"]["vector_store"] = "configured"
            else:
                health_status["components"]["vector_store"] = "not_configured"
                health_status["status"] = "degraded"
        else:
            health_status["components"]["vector_store"] = "unknown"
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["components"]["vector_store"] = "error"
        health_status["components"]["vector_store_error"] = str(e)
        health_status["status"] = "degraded"
        logger.error(f"Vector store health check failed: {e}")
    
    # Check configuration
    try:
        settings.validate_vector_store()
        settings.validate_chunking()
        health_status["components"]["config"] = "valid"
    except Exception as e:
        health_status["components"]["config"] = "invalid"
        health_status["components"]["config_error"] = str(e)
        health_status["status"] = "unhealthy"
        logger.error(f"Configuration validation failed: {e}")
    
    # Check embedding provider
    if settings.EMBEDDING_PROVIDER == "openai":
        if settings.OPENAI_API_KEY:
            health_status["components"]["embeddings"] = "openai_configured"
        else:
            health_status["components"]["embeddings"] = "openai_not_configured"
            health_status["status"] = "degraded"
    elif settings.EMBEDDING_PROVIDER == "sentence-transformers":
        health_status["components"]["embeddings"] = "sentence_transformers"
    else:
        health_status["components"]["embeddings"] = "unknown_provider"
        health_status["status"] = "degraded"
    
    # Check system resources (Cloud Run monitoring)
    if STARTUP_MODULE_AVAILABLE:
        try:
            memory_stats = check_memory_usage()
            if memory_stats:
                health_status["system"] = memory_stats
                
                # Warn if memory usage is high
                if memory_stats.get("memory_percent", 0) > 85:
                    health_status["warnings"] = health_status.get("warnings", [])
                    health_status["warnings"].append("High memory usage")
                    health_status["status"] = "degraded"
                
                # Warn if disk usage is high
                if memory_stats.get("disk_percent", 0) > 90:
                    health_status["warnings"] = health_status.get("warnings", [])
                    health_status["warnings"].append("Low disk space")
                    health_status["status"] = "degraded"
        except Exception as e:
            logger.warning(f"Could not check system resources: {e}")
    
    # Add response time
    response_time_ms = (time.time() - start_time) * 1000
    health_status["response_time_ms"] = round(response_time_ms, 2)
    
    # Warn if response time is slow
    if response_time_ms > 1000:  # > 1 second
        health_status["warnings"] = health_status.get("warnings", [])
        health_status["warnings"].append("Slow health check response")
    
    # Determine HTTP status code
    status_code = 200
    if health_status["status"] == "unhealthy":
        status_code = 503
    elif health_status["status"] == "degraded":
        status_code = 200  # Still return 200, but indicate degraded status
    
    return JSONResponse(content=health_status, status_code=status_code)


@router.get("/ready")
@router.get("/ready/")
async def readiness_check():
    """
    Readiness check endpoint
    
    More strict than health check - returns 200 only if system is ready
    to serve requests. Returns 503 if any critical component is unavailable.
    
    Returns:
        dict: Readiness status
    """
    readiness = {
        "ready": True,
        "checks": {}
    }
    
    # Check critical components
    critical_checks = []
    
    # Database must be configured
    if not (settings.SUPABASE_URL and settings.SUPABASE_KEY):
        readiness["checks"]["database"] = "not_configured"
        critical_checks.append(False)
    else:
        try:
            supabase_client = get_supabase_client()
            if supabase_client.health_check():
                readiness["checks"]["database"] = "ready"
                critical_checks.append(True)
            else:
                readiness["checks"]["database"] = "not_connected"
                critical_checks.append(False)
        except Exception as e:
            readiness["checks"]["database"] = f"error: {str(e)}"
            critical_checks.append(False)
    
    # Vector store must be configured
    if settings.VECTOR_STORE == "pgvector":
        if not settings.DATABASE_URL:
            readiness["checks"]["vector_store"] = "not_configured"
            critical_checks.append(False)
        else:
            readiness["checks"]["vector_store"] = "ready"
            critical_checks.append(True)
    elif settings.VECTOR_STORE == "qdrant":
        if not settings.QDRANT_URL:
            readiness["checks"]["vector_store"] = "not_configured"
            critical_checks.append(False)
        else:
            readiness["checks"]["vector_store"] = "ready"
            critical_checks.append(True)
    else:
        readiness["checks"]["vector_store"] = "unknown"
        critical_checks.append(False)
    
    # Embedding provider must be configured
    if settings.EMBEDDING_PROVIDER == "openai":
        if not settings.OPENAI_API_KEY:
            readiness["checks"]["embeddings"] = "openai_not_configured"
            critical_checks.append(False)
        else:
            readiness["checks"]["embeddings"] = "openai_ready"
            critical_checks.append(True)
    elif settings.EMBEDDING_PROVIDER == "sentence-transformers":
        readiness["checks"]["embeddings"] = "sentence_transformers_ready"
        critical_checks.append(True)
    else:
        readiness["checks"]["embeddings"] = "unknown_provider"
        critical_checks.append(False)
    
    # System is ready only if all critical checks pass
    readiness["ready"] = all(critical_checks)
    
    status_code = 200 if readiness["ready"] else 503
    return JSONResponse(content=readiness, status_code=status_code)


@router.get("/liveness")
@router.get("/liveness/")
async def liveness_check():
    """
    Liveness check endpoint for Cloud Run
    
    Simple check that returns 200 if the service is alive.
    This is used by Cloud Run to determine if the container should be restarted.
    
    Returns:
        dict: Simple status message
    """
    return JSONResponse(
        content={
            "alive": True,
            "timestamp": datetime.utcnow().isoformat()
        },
        status_code=200
    )
