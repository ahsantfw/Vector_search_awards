"""
FastAPI Application
Main application entry point
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
import os
from pathlib import Path

from src.core.config import settings
from src.core.logging import get_logger
from src.api.routes import search, health, indexing

logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="SBIR Vector Search API",
    description="Hybrid vector search API for SBIR award data",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Mount static files directory for UI
static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Middleware to skip ngrok browser warning
class NgrokSkipWarningMiddleware(BaseHTTPMiddleware):
    """Middleware to add ngrok-skip-browser-warning header to all responses"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Add header to skip ngrok warning page
        response.headers["ngrok-skip-browser-warning"] = "true"
        return response

# Add ngrok skip warning middleware (before CORS)
app.add_middleware(NgrokSkipWarningMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(search.router)
app.include_router(health.router)
app.include_router(indexing.router)


@app.get("/")
async def root():
    """
    Root endpoint - serves the UI or API information
    
    Returns:
        FileResponse: UI HTML file if available, otherwise API info
    """
    ui_file = static_dir / "index.html"
    if ui_file.exists():
        return FileResponse(str(ui_file))
    
    return JSONResponse(content={
        "name": "SBIR Vector Search API",
        "version": "1.0.0",
        "description": "Hybrid vector search API for SBIR award data",
        "endpoints": {
            "search": "/search",
            "health": "/health",
            "indexing": "/indexing",
            "docs": "/docs",
            "redoc": "/redoc",
            "ui": "/static/index.html"
        },
        "features": [
            "Hybrid search (lexical + semantic)",
            "Multi-approach search (hybrid, lexical, semantic)",
            "Dynamic indexing via API webhooks",
            "Supabase integration",
            "pgvector/Qdrant support"
        ]
    })


@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    logger.info(
        "SBIR Vector Search API starting",
        extra={
            "environment": settings.ENVIRONMENT,
            "vector_store": settings.VECTOR_STORE,
            "api_host": settings.API_HOST,
            "api_port": settings.API_PORT
        }
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event"""
    logger.info("SBIR Vector Search API shutting down")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.app:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
