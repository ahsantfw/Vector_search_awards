"""
Search API Routes
Search endpoint implementation with multi-approach support
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.core.logging import get_logger
from src.core.models.search import SearchRequest, SearchResponse, SearchResult
from src.core.search.hybrid_search import search_all, search_all_async
from src.database.supabase import get_supabase_client, SupabaseClient
from src.database.pgvector import PgVectorManager, get_pgvector_manager

logger = get_logger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


def get_vector_store_client():
    """
    Dependency to get vector store client based on configuration
    
    Returns:
        PgVectorManager or QdrantClient based on settings.VECTOR_STORE
    """
    if settings.VECTOR_STORE == "pgvector":
        return get_pgvector_manager()
    elif settings.VECTOR_STORE == "qdrant":
        # Import Qdrant client if needed
        try:
            from qdrant_client import QdrantClient
            return QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY if settings.QDRANT_API_KEY else None
            )
        except ImportError:
            logger.warning("Qdrant client not available. Install with: pip install qdrant-client")
            return None
    else:
        return None


@router.post("", response_model=SearchResponse)
@router.post("/", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    supabase_client: Optional[SupabaseClient] = Depends(lambda: get_supabase_client() if settings.SUPABASE_URL else None),
    vector_store_client = Depends(get_vector_store_client)
):
    """
    Multi-approach search endpoint
    
    Returns results from all three search approaches:
    - Hybrid (default): Combines lexical + semantic
    - Lexical: Exact match search only
    - Semantic: Meaning-based search only
    
    Args:
        request: Search request with query, top_k, and optional parameters
        supabase_client: Supabase client for lexical search
        vector_store_client: Vector store client for semantic search
    
    Returns:
        SearchResponse with hybrid_results, lexical_results, semantic_results
    
    Example:
        ```json
        {
          "query": "quantum computing",
          "top_k": 10,
          "alpha": 0.5,
          "beta": 10.0
        }
        ```
    """
    try:
        logger.info(
            f"Search request received",
            extra={
                "query": request.query,
                "top_k": request.top_k,
                "approach": request.approach,
                "alpha": request.alpha,
                "beta": request.beta
            }
        )
        
        # Validate top_k
        if request.top_k > settings.MAX_TOP_K:
            raise HTTPException(
                status_code=400,
                detail=f"top_k cannot exceed {settings.MAX_TOP_K}"
            )
        
        # Get Supabase client for lexical search
        supabase_raw_client = None
        if supabase_client:
            try:
                supabase_raw_client = supabase_client.get_client()
            except Exception as e:
                logger.warning(f"Could not get Supabase client: {e}")
        
        # Run multi-approach search in PARALLEL (async - 2x faster!)
        results = await search_all_async(
            query=request.query,
            supabase_client=supabase_raw_client,
            vector_store_client=vector_store_client,
            top_k=request.top_k,
            alpha=request.alpha,
            beta=request.beta
        )
        
        # Convert to Pydantic models (include ALL schema columns)
        def to_search_result(item: dict) -> SearchResult:
            return SearchResult(
                # Core identifiers
                award_id=item.get("award_id", ""),
                award_number=item.get("award_number"),
                # Basic info
                title=item.get("title", ""),
                agency=item.get("agency", ""),
                snippet=item.get("snippet", ""),
                url=item.get("url") or item.get("public_abstract_url"),
                # Search scores
                final_score=item.get("final_score"),
                lexical_score=item.get("lexical_score"),
                semantic_score=item.get("semantic_score"),
                chunk_index=item.get("chunk_index") or item.get("best_chunk_index"),
                chunks=item.get("chunks"),  # All matching chunks
                # All schema columns
                award_status=item.get("award_status"),
                institution=item.get("institution"),
                uei=item.get("uei"),
                duns=item.get("duns"),
                most_recent_award_date=item.get("most_recent_award_date"),
                num_support_periods=item.get("num_support_periods"),
                pm=item.get("pm"),
                current_budget_period=item.get("current_budget_period"),
                current_project_period=item.get("current_project_period"),
                pi=item.get("pi"),
                supplement_budget_period=item.get("supplement_budget_period"),
                public_abstract=item.get("public_abstract"),
                public_abstract_url=item.get("public_abstract_url") or item.get("url")
            )
        
        response = SearchResponse(
            query=results["query"],
            hybrid_results=[to_search_result(r) for r in results["hybrid_results"]],
            lexical_results=[to_search_result(r) for r in results["lexical_results"]],
            semantic_results=[to_search_result(r) for r in results["semantic_results"]],
            metadata=results["metadata"]
        )
        
        logger.info(
            f"Search completed successfully",
            extra={
                "query": request.query,
                "hybrid_count": len(response.hybrid_results),
                "lexical_count": len(response.lexical_results),
                "semantic_count": len(response.semantic_results)
            }
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}", extra={"query": request.query}, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/health")
async def search_health():
    """
    Health check for search functionality
    
    Returns:
        dict: Health status of search components
    """
    health_status = {
        "status": "healthy",
        "components": {
            "vector_store": settings.VECTOR_STORE,
            "supabase_configured": bool(settings.SUPABASE_URL and settings.SUPABASE_KEY),
            "openai_configured": bool(settings.OPENAI_API_KEY)
        }
    }
    
    # Check vector store availability
    try:
        vector_client = get_vector_store_client()
        if vector_client:
            health_status["components"]["vector_store_available"] = True
        else:
            health_status["components"]["vector_store_available"] = False
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["components"]["vector_store_available"] = False
        health_status["components"]["vector_store_error"] = str(e)
        health_status["status"] = "degraded"
    
    # Check Supabase connection
    try:
        if settings.SUPABASE_URL and settings.SUPABASE_KEY:
            supabase_client = get_supabase_client()
            if supabase_client.health_check():
                health_status["components"]["supabase_connected"] = True
            else:
                health_status["components"]["supabase_connected"] = False
                health_status["status"] = "degraded"
        else:
            health_status["components"]["supabase_connected"] = False
    except Exception as e:
        health_status["components"]["supabase_connected"] = False
        health_status["components"]["supabase_error"] = str(e)
        health_status["status"] = "degraded"
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(content=health_status, status_code=status_code)
