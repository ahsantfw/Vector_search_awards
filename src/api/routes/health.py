"""
Health Check API Routes
Health check endpoint implementation
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.core.logging import get_logger
from src.database.supabase import get_supabase_client
from src.database.pgvector import get_pgvector_manager

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/health/")
async def health_check():
    """
    System health check endpoint
    
    Checks the health of all system components:
    - Database connection (Supabase)
    - Vector store (pgvector/Qdrant)
    - Configuration
    
    Returns:
        dict: Health status with component details
    
    Example Response:
        ```json
        {
          "status": "healthy",
          "version": "1.0.0",
          "components": {
            "database": "connected",
            "vector_store": "connected",
            "config": "valid"
          }
        }
        ```
    """
    health_status = {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
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
    
    # Check OpenAI API key (for embeddings)
    if settings.OPENAI_API_KEY:
        health_status["components"]["embeddings"] = "configured"
    else:
        health_status["components"]["embeddings"] = "not_configured"
        health_status["status"] = "degraded"
    
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
    
    # OpenAI API key must be configured for embeddings
    if not settings.OPENAI_API_KEY:
        readiness["checks"]["embeddings"] = "not_configured"
        critical_checks.append(False)
    else:
        readiness["checks"]["embeddings"] = "ready"
        critical_checks.append(True)
    
    # System is ready only if all critical checks pass
    readiness["ready"] = all(critical_checks)
    
    status_code = 200 if readiness["ready"] else 503
    return JSONResponse(content=readiness, status_code=status_code)
