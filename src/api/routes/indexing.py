"""
Indexing API Routes
Endpoints for triggering data indexing/embedding operations via n8n webhooks

Security: All endpoints require API key authentication via X-API-Key header
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Header, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from datetime import datetime
import asyncio

from src.core.config import settings
from src.core.logging import get_logger
from src.database.supabase import get_supabase_client
from src.indexing.pipeline import get_indexing_pipeline

logger = get_logger(__name__)

router = APIRouter(prefix="/indexing", tags=["indexing"])

# In-memory job tracking (for simple deployments)
# For production, consider using Redis or a database
_indexing_jobs: Dict[str, Dict[str, Any]] = {}


class IndexingRequest(BaseModel):
    """Request model for triggering indexing"""
    batch_size: Optional[int] = Field(default=100, description="Batch size for processing")
    force_reindex: Optional[bool] = Field(default=False, description="Force reindexing even if already indexed")


class IncrementalIndexingRequest(BaseModel):
    """Request model for incremental indexing"""
    award_ids: Optional[List[str]] = Field(default=None, description="Specific award IDs to index")
    since_date: Optional[str] = Field(default=None, description="Index awards modified since this date (ISO format)")
    batch_size: Optional[int] = Field(default=100, description="Batch size for processing")


class SingleAwardIndexingRequest(BaseModel):
    """Request model for indexing a single award"""
    award_id: str = Field(..., description="Award ID to index")
    award_data: Optional[Dict[str, Any]] = Field(default=None, description="Award data (if not in database)")


class IndexingResponse(BaseModel):
    """Response model for indexing operations"""
    job_id: str
    status: str
    message: str
    started_at: str
    metadata: Optional[Dict[str, Any]] = None


class JobStatusResponse(BaseModel):
    """Response model for job status"""
    job_id: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def verify_api_key(x_api_key: str = Header(..., description="API Key for authentication")) -> bool:
    """
    Verify API key for indexing endpoints
    
    Args:
        x_api_key: API key from request header
        
    Returns:
        bool: True if valid
        
    Raises:
        HTTPException: If API key is invalid
    """
    # Get API key from environment
    expected_key = settings.__dict__.get("INDEXING_API_KEY", None)
    
    # If no API key is configured, allow access (for development)
    if not expected_key:
        logger.warning("No INDEXING_API_KEY configured - indexing endpoints are unprotected!")
        return True
    
    if x_api_key != expected_key:
        logger.warning(f"Invalid API key attempt")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return True


async def run_full_indexing(job_id: str, batch_size: int, force_reindex: bool):
    """
    Background task to run full indexing
    
    Args:
        job_id: Job ID for tracking
        batch_size: Batch size for processing
        force_reindex: Force reindexing flag
    """
    try:
        logger.info(f"Starting full indexing job: {job_id}")
        _indexing_jobs[job_id]["status"] = "running"
        
        # Get Supabase client
        supabase = get_supabase_client()
        
        # Fetch all awards
        response = supabase.get_client().table(settings.AWARDS_TABLE_NAME).select("*").execute()
        awards = response.data
        
        logger.info(f"Found {len(awards)} awards to index")
        _indexing_jobs[job_id]["progress"] = {
            "total": len(awards),
            "processed": 0
        }
        
        # Get indexing pipeline
        pipeline = get_indexing_pipeline()
        
        # Process in batches
        results = {
            "total_awards": len(awards),
            "indexed_awards": 0,
            "total_chunks": 0,
            "errors": []
        }
        
        for i in range(0, len(awards), batch_size):
            batch = awards[i:i + batch_size]
            
            try:
                # Index batch
                batch_result = pipeline.index_awards(
                    awards=batch,
                    use_cache=not force_reindex
                )
                
                results["indexed_awards"] += batch_result.get("indexed_count", 0)
                results["total_chunks"] += batch_result.get("total_chunks", 0)
                
                # Update progress
                _indexing_jobs[job_id]["progress"]["processed"] = min(i + batch_size, len(awards))
                
                logger.info(f"Indexed batch {i//batch_size + 1}: {len(batch)} awards")
                
            except Exception as e:
                error_msg = f"Error indexing batch {i//batch_size + 1}: {str(e)}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
        
        # Mark as completed
        _indexing_jobs[job_id]["status"] = "completed"
        _indexing_jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
        _indexing_jobs[job_id]["result"] = results
        
        logger.info(f"Completed full indexing job: {job_id}")
        
    except Exception as e:
        logger.error(f"Full indexing job {job_id} failed: {e}", exc_info=True)
        _indexing_jobs[job_id]["status"] = "failed"
        _indexing_jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
        _indexing_jobs[job_id]["error"] = str(e)


async def run_incremental_indexing(job_id: str, award_ids: Optional[List[str]], since_date: Optional[str], batch_size: int):
    """
    Background task to run incremental indexing
    
    Args:
        job_id: Job ID for tracking
        award_ids: Specific award IDs to index
        since_date: Index awards modified since this date
        batch_size: Batch size for processing
    """
    try:
        logger.info(f"Starting incremental indexing job: {job_id}")
        _indexing_jobs[job_id]["status"] = "running"
        
        # Get Supabase client
        supabase = get_supabase_client()
        
        # Build query
        query = supabase.get_client().table(settings.AWARDS_TABLE_NAME).select("*")
        
        if award_ids:
            query = query.in_("award_id", award_ids)
        elif since_date:
            query = query.gte("most_recent_award_date", since_date)
        
        response = query.execute()
        awards = response.data
        
        logger.info(f"Found {len(awards)} awards to index incrementally")
        _indexing_jobs[job_id]["progress"] = {
            "total": len(awards),
            "processed": 0
        }
        
        # Get indexing pipeline
        pipeline = get_indexing_pipeline()
        
        # Index awards
        result = pipeline.index_awards(
            awards=awards,
            use_cache=False  # Always reindex for incremental updates
        )
        
        # Mark as completed
        _indexing_jobs[job_id]["status"] = "completed"
        _indexing_jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
        _indexing_jobs[job_id]["result"] = result
        _indexing_jobs[job_id]["progress"]["processed"] = len(awards)
        
        logger.info(f"Completed incremental indexing job: {job_id}")
        
    except Exception as e:
        logger.error(f"Incremental indexing job {job_id} failed: {e}", exc_info=True)
        _indexing_jobs[job_id]["status"] = "failed"
        _indexing_jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
        _indexing_jobs[job_id]["error"] = str(e)


async def run_single_award_indexing(job_id: str, award_id: str, award_data: Optional[Dict[str, Any]]):
    """
    Background task to index a single award
    
    Args:
        job_id: Job ID for tracking
        award_id: Award ID to index
        award_data: Award data (if not in database)
    """
    try:
        logger.info(f"Starting single award indexing job: {job_id} for award: {award_id}")
        _indexing_jobs[job_id]["status"] = "running"
        
        # Get award data if not provided
        if not award_data:
            supabase = get_supabase_client()
            response = supabase.get_client().table(settings.AWARDS_TABLE_NAME).select("*").eq("award_id", award_id).execute()
            
            if not response.data:
                raise ValueError(f"Award {award_id} not found in database")
            
            award_data = response.data[0]
        
        # Get indexing pipeline
        pipeline = get_indexing_pipeline()
        
        # Index single award
        result = pipeline.index_awards(
            awards=[award_data],
            use_cache=False
        )
        
        # Mark as completed
        _indexing_jobs[job_id]["status"] = "completed"
        _indexing_jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
        _indexing_jobs[job_id]["result"] = result
        
        logger.info(f"Completed single award indexing job: {job_id}")
        
    except Exception as e:
        logger.error(f"Single award indexing job {job_id} failed: {e}", exc_info=True)
        _indexing_jobs[job_id]["status"] = "failed"
        _indexing_jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
        _indexing_jobs[job_id]["error"] = str(e)


@router.post("/trigger", response_model=IndexingResponse, dependencies=[Depends(verify_api_key)])
async def trigger_full_indexing(
    request: IndexingRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger full reindexing of all awards
    
    This endpoint starts a background job to index all awards in the database.
    Use this when you want to rebuild the entire search index.
    
    **Authentication**: Requires X-API-Key header
    
    **Example**:
    ```bash
    curl -X POST https://your-service.run.app/indexing/trigger \
      -H "X-API-Key: your-api-key" \
      -H "Content-Type: application/json" \
      -d '{"batch_size": 100, "force_reindex": true}'
    ```
    
    Args:
        request: Indexing request parameters
        background_tasks: FastAPI background tasks
        
    Returns:
        IndexingResponse with job ID and status
    """
    # Generate job ID
    job_id = f"full_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    
    # Initialize job tracking
    _indexing_jobs[job_id] = {
        "job_id": job_id,
        "type": "full",
        "status": "queued",
        "started_at": datetime.utcnow().isoformat(),
        "progress": None,
        "result": None,
        "error": None
    }
    
    # Add background task
    background_tasks.add_task(
        run_full_indexing,
        job_id=job_id,
        batch_size=request.batch_size,
        force_reindex=request.force_reindex
    )
    
    logger.info(f"Queued full indexing job: {job_id}")
    
    return IndexingResponse(
        job_id=job_id,
        status="queued",
        message="Full indexing job queued successfully",
        started_at=_indexing_jobs[job_id]["started_at"]
    )


@router.post("/incremental", response_model=IndexingResponse, dependencies=[Depends(verify_api_key)])
async def trigger_incremental_indexing(
    request: IncrementalIndexingRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger incremental indexing of specific awards or recent changes
    
    This endpoint indexes only specific awards or awards modified since a certain date.
    Use this for updating the search index without reindexing everything.
    
    **Authentication**: Requires X-API-Key header
    
    **Example 1** (specific awards):
    ```bash
    curl -X POST https://your-service.run.app/indexing/incremental \
      -H "X-API-Key: your-api-key" \
      -H "Content-Type: application/json" \
      -d '{"award_ids": ["award123", "award456"]}'
    ```
    
    **Example 2** (recent awards):
    ```bash
    curl -X POST https://your-service.run.app/indexing/incremental \
      -H "X-API-Key: your-api-key" \
      -H "Content-Type: application/json" \
      -d '{"since_date": "2026-01-01"}'
    ```
    
    Args:
        request: Incremental indexing request parameters
        background_tasks: FastAPI background tasks
        
    Returns:
        IndexingResponse with job ID and status
    """
    # Generate job ID
    job_id = f"incremental_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    
    # Initialize job tracking
    _indexing_jobs[job_id] = {
        "job_id": job_id,
        "type": "incremental",
        "status": "queued",
        "started_at": datetime.utcnow().isoformat(),
        "progress": None,
        "result": None,
        "error": None
    }
    
    # Add background task
    background_tasks.add_task(
        run_incremental_indexing,
        job_id=job_id,
        award_ids=request.award_ids,
        since_date=request.since_date,
        batch_size=request.batch_size
    )
    
    logger.info(f"Queued incremental indexing job: {job_id}")
    
    return IndexingResponse(
        job_id=job_id,
        status="queued",
        message="Incremental indexing job queued successfully",
        started_at=_indexing_jobs[job_id]["started_at"]
    )


@router.post("/single", response_model=IndexingResponse, dependencies=[Depends(verify_api_key)])
async def trigger_single_award_indexing(
    request: SingleAwardIndexingRequest,
    background_tasks: BackgroundTasks
):
    """
    Index a single award by ID
    
    This endpoint indexes a single award, useful for immediate updates.
    
    **Authentication**: Requires X-API-Key header
    
    **Example**:
    ```bash
    curl -X POST https://your-service.run.app/indexing/single \
      -H "X-API-Key: your-api-key" \
      -H "Content-Type: application/json" \
      -d '{"award_id": "award123"}'
    ```
    
    Args:
        request: Single award indexing request
        background_tasks: FastAPI background tasks
        
    Returns:
        IndexingResponse with job ID and status
    """
    # Generate job ID
    job_id = f"single_{request.award_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    
    # Initialize job tracking
    _indexing_jobs[job_id] = {
        "job_id": job_id,
        "type": "single",
        "status": "queued",
        "started_at": datetime.utcnow().isoformat(),
        "progress": None,
        "result": None,
        "error": None
    }
    
    # Add background task
    background_tasks.add_task(
        run_single_award_indexing,
        job_id=job_id,
        award_id=request.award_id,
        award_data=request.award_data
    )
    
    logger.info(f"Queued single award indexing job: {job_id}")
    
    return IndexingResponse(
        job_id=job_id,
        status="queued",
        message=f"Single award indexing job queued for award {request.award_id}",
        started_at=_indexing_jobs[job_id]["started_at"]
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Get the status of an indexing job
    
    This endpoint returns the current status and progress of an indexing job.
    No authentication required for status checks.
    
    **Example**:
    ```bash
    curl https://your-service.run.app/indexing/status/full_20260201_120000
    ```
    
    Args:
        job_id: Job ID to check
        
    Returns:
        JobStatusResponse with job status and progress
    """
    if job_id not in _indexing_jobs:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found"
        )
    
    job = _indexing_jobs[job_id]
    
    return JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        started_at=job["started_at"],
        completed_at=job.get("completed_at"),
        progress=job.get("progress"),
        result=job.get("result"),
        error=job.get("error")
    )


@router.get("/jobs")
async def list_jobs():
    """
    List all indexing jobs
    
    Returns a list of all indexing jobs with their current status.
    No authentication required.
    
    **Example**:
    ```bash
    curl https://your-service.run.app/indexing/jobs
    ```
    
    Returns:
        List of all jobs with their status
    """
    return {
        "total": len(_indexing_jobs),
        "jobs": list(_indexing_jobs.values())
    }


@router.delete("/jobs/{job_id}", dependencies=[Depends(verify_api_key)])
async def delete_job(job_id: str):
    """
    Delete a job from tracking
    
    This endpoint removes a job from the in-memory tracking.
    Use this to clean up old jobs.
    
    **Authentication**: Requires X-API-Key header
    
    Args:
        job_id: Job ID to delete
        
    Returns:
        Success message
    """
    if job_id not in _indexing_jobs:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found"
        )
    
    del _indexing_jobs[job_id]
    
    return {"message": f"Job {job_id} deleted successfully"}
