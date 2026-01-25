"""
Hybrid Search
Combines lexical and semantic search with lexical boost
Supports both sync and async (parallel) execution
"""
import asyncio
from typing import List, Dict, Optional, Any

from src.core.config import settings
from src.core.logging import get_logger
from src.core.search.lexical import lexical_search_in_memory, lexical_search_supabase
from src.core.search.semantic import semantic_search
from src.core.search.deduplication import deduplicate_and_group_results

logger = get_logger(__name__)


def hybrid_search(
    query: str,
    lexical_results: List[Dict[str, Any]],
    semantic_results: List[Dict[str, Any]],
    alpha: Optional[float] = None,
    beta: Optional[float] = None,
    top_k: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Combine lexical and semantic search results with hybrid scoring
    
    Args:
        query: Search query string
        lexical_results: Results from lexical search
        semantic_results: Results from semantic search
        alpha: Semantic weight (defaults to settings.SEMANTIC_WEIGHT)
        beta: Lexical boost (defaults to settings.LEXICAL_BOOST)
        top_k: Number of results to return (defaults to settings.DEFAULT_TOP_K)
    
    Returns:
        List of dictionaries with hybrid scores, sorted by final_score
    """
    # Use explicit None check to allow 0.0 values
    # This is important: if alpha=0.0 or beta=0.0, we want to use those values, not defaults
    alpha = alpha if alpha is not None else settings.SEMANTIC_WEIGHT
    beta = beta if beta is not None else settings.LEXICAL_BOOST
    top_k = top_k if top_k is not None else settings.DEFAULT_TOP_K
    
    logger.debug(
        f"hybrid_search using alpha={alpha}, beta={beta}, top_k={top_k}",
        extra={"alpha": alpha, "beta": beta, "top_k": top_k, "query": query}
    )
    
    # Create maps for easy lookup
    lexical_map = {r["award_id"]: r["lexical_score"] for r in lexical_results}
    semantic_map = {}
    
    # Keep best semantic score per award_id
    for r in semantic_results:
        award_id = r["award_id"]
        if award_id not in semantic_map or r["semantic_score"] > semantic_map[award_id]["semantic_score"]:
            semantic_map[award_id] = r
    
    # Union of all award IDs
    all_award_ids = set(lexical_map.keys()) | set(semantic_map.keys())
    
    # Calculate hybrid scores
    hybrid_results = []
    for award_id in all_award_ids:
        lexical_score = lexical_map.get(award_id, 0.0)
        semantic_data = semantic_map.get(award_id, {})
        semantic_score = semantic_data.get("semantic_score", 0.0)
        
        # Filter: If one parameter is 0, only include awards with contribution from the other
        # When beta=0: Only include awards that were found by semantic search (in semantic_map)
        if beta == 0.0 and award_id not in semantic_map:
            continue
        # When alpha=0: Only include awards that were found by lexical search (in lexical_map)
        if alpha == 0.0 and award_id not in lexical_map:
            continue
        
        # Hybrid Score = (alpha × semantic) + (beta × lexical)
        final_score = (alpha * semantic_score) + (beta * lexical_score)
        
        # Get metadata from either source (prefer semantic as it has more complete data)
        metadata = semantic_data.copy() if semantic_data else {}
        
        # Add/override with lexical info if available (lexical might have better snippet)
        if award_id in lexical_map:
            lexical_result = next((r for r in lexical_results if r["award_id"] == award_id), None)
            if lexical_result:
                # Merge lexical data, but keep semantic data for fields not in lexical
                metadata.update({
                    "title": lexical_result.get("title", metadata.get("title", "")),
                    "agency": lexical_result.get("agency", metadata.get("agency", "")),
                    "snippet": lexical_result.get("snippet", metadata.get("snippet", "")),
                    "url": lexical_result.get("url") or lexical_result.get("public_abstract_url") or metadata.get("url"),
                    "public_abstract_url": lexical_result.get("public_abstract_url") or lexical_result.get("url") or metadata.get("public_abstract_url")
                })
                # Add any other columns from lexical that semantic might not have
                for key in ["award_number", "award_status", "institution", "uei", "duns", 
                           "most_recent_award_date", "num_support_periods", "pm", 
                           "current_budget_period", "current_project_period", "pi", 
                           "supplement_budget_period", "public_abstract"]:
                    if key in lexical_result and lexical_result[key] is not None:
                        metadata[key] = lexical_result[key]
        
        # Build result with ALL schema columns
        hybrid_result = {
            "award_id": award_id,
            "award_number": metadata.get("award_number"),
            "final_score": final_score,
            "lexical_score": lexical_score,
            "semantic_score": semantic_score,
            "title": metadata.get("title", ""),
            "agency": metadata.get("agency", ""),
            "snippet": metadata.get("snippet", ""),
            "url": metadata.get("url") or metadata.get("public_abstract_url"),
            "public_abstract_url": metadata.get("public_abstract_url") or metadata.get("url"),
            "chunk_index": metadata.get("chunk_index", 0),
            # All other schema columns
            "award_status": metadata.get("award_status"),
            "institution": metadata.get("institution"),
            "uei": metadata.get("uei"),
            "duns": metadata.get("duns"),
            "most_recent_award_date": metadata.get("most_recent_award_date"),
            "num_support_periods": metadata.get("num_support_periods"),
            "pm": metadata.get("pm"),
            "current_budget_period": metadata.get("current_budget_period"),
            "current_project_period": metadata.get("current_project_period"),
            "pi": metadata.get("pi"),
            "supplement_budget_period": metadata.get("supplement_budget_period"),
            "public_abstract": metadata.get("public_abstract")
        }
        hybrid_results.append(hybrid_result)
    
    # Sort by final score (descending)
    hybrid_results.sort(key=lambda x: x["final_score"], reverse=True)
    
    logger.debug(
        f"Hybrid search combined {len(lexical_results)} lexical + {len(semantic_results)} semantic = {len(hybrid_results)} unique results",
        extra={"query": query, "top_k": top_k}
    )
    
    return hybrid_results[:top_k]


async def search_all_async(
    query: str,
    awards: Optional[List[Dict[str, Any]]] = None,
    supabase_client=None,
    vector_store_client=None,
    top_k: Optional[int] = None,
    alpha: Optional[float] = None,
    beta: Optional[float] = None
) -> Dict[str, Any]:
    """
    Perform all search types in TRUE PARALLEL (async version)
    
    Runs lexical and semantic searches simultaneously using asyncio.
    This is 2x faster than sequential execution.
    
    Args:
        query: Search query string
        awards: List of awards (for in-memory lexical search)
        supabase_client: Supabase client (for database lexical search)
        vector_store_client: Vector store client (pgvector/Qdrant)
        top_k: Number of results per search type
        alpha: Semantic weight
        beta: Lexical boost
    
    Returns:
        Dictionary with all three result sets and metadata
    """
    import time
    
    top_k = top_k or settings.DEFAULT_TOP_K
    start_time = time.time()
    
    logger.info(f"Running parallel search for query: {query}", extra={"top_k": top_k})
    
    # Define async search functions
    async def run_lexical_search():
        """Run lexical search async"""
        try:
            if supabase_client:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    lexical_search_supabase,
                    query,
                    supabase_client,
                    top_k
                )
            elif awards:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    lexical_search_in_memory,
                    query,
                    awards,
                    top_k
                )
            else:
                logger.warning("No data source available for lexical search")
                return []
        except Exception as e:
            logger.error(f"Lexical search failed: {e}")
            return []
    
    async def run_semantic_search():
        """Run semantic search async"""
        try:
            if vector_store_client:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    semantic_search,
                    query,
                    vector_store_client,
                    top_k
                )
            else:
                logger.warning("No vector store available for semantic search")
                return []
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
    
    # Run BOTH searches in parallel! ✅
    lexical_task = run_lexical_search()
    semantic_task = run_semantic_search()
    
    # Wait for both to complete (parallel execution)
    lexical_results, semantic_results = await asyncio.gather(
        lexical_task,
        semantic_task,
        return_exceptions=True
    )
    
    # Handle exceptions
    if isinstance(lexical_results, Exception):
        logger.error(f"Lexical search failed: {lexical_results}")
        lexical_results = []
    
    if isinstance(semantic_results, Exception):
        logger.error(f"Semantic search failed: {semantic_results}")
        semantic_results = []
    
    # Run hybrid search (combines lexical + semantic)
    hybrid_results = []
    try:
        if lexical_results or semantic_results:
            logger.debug(
                f"Calling hybrid_search with alpha={alpha}, beta={beta}",
                extra={"alpha": alpha, "beta": beta, "top_k": top_k}
            )
            hybrid_results = hybrid_search(
                query,
                lexical_results,
                semantic_results,
                alpha=alpha,
                beta=beta,
                top_k=top_k
            )
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
    
    duration_ms = (time.time() - start_time) * 1000
    
    logger.info(
        f"Parallel search completed in {duration_ms:.2f}ms",
        extra={
            "query": query,
            "lexical_count": len(lexical_results),
            "semantic_count": len(semantic_results),
            "hybrid_count": len(hybrid_results),
            "duration_ms": duration_ms
        }
    )
    
    # Deduplicate and group results by award_id
    hybrid_deduplicated = deduplicate_and_group_results(hybrid_results, group_chunks=True)
    lexical_deduplicated = deduplicate_and_group_results(lexical_results, group_chunks=True)
    semantic_deduplicated = deduplicate_and_group_results(semantic_results, group_chunks=True)
    
    return {
        "query": query,
        "hybrid_results": hybrid_deduplicated[:top_k],
        "lexical_results": lexical_deduplicated[:top_k],
        "semantic_results": semantic_deduplicated[:top_k],
        "metadata": {
            "hybrid_count": len(hybrid_deduplicated),
            "lexical_count": len(lexical_deduplicated),
            "semantic_count": len(semantic_deduplicated),
            "search_time_ms": duration_ms,
            "vector_store": settings.VECTOR_STORE
        }
    }


def search_all(
    query: str,
    awards: Optional[List[Dict[str, Any]]] = None,
    supabase_client=None,
    vector_store_client=None,
    top_k: Optional[int] = None,
    alpha: Optional[float] = None,
    beta: Optional[float] = None
) -> Dict[str, Any]:
    """
    Perform all three search types and return all results (SYNC version)
    
    This is the synchronous version. For better performance, use search_all_async().
    Runs lexical, semantic, and hybrid searches sequentially.
    
    Args:
        query: Search query string
        awards: List of awards (for in-memory lexical search)
        supabase_client: Supabase client (for database lexical search)
        vector_store_client: Vector store client (pgvector/Qdrant)
        top_k: Number of results per search type
        alpha: Semantic weight
        beta: Lexical boost
    
    Returns:
        Dictionary with all three result sets and metadata
    """
    import time
    
    top_k = top_k or settings.DEFAULT_TOP_K
    start_time = time.time()
    
    logger.info(f"Running all search types for query: {query}", extra={"top_k": top_k})
    
    # Run lexical search
    lexical_results = []
    try:
        if supabase_client:
            lexical_results = lexical_search_supabase(query, supabase_client, top_k=top_k)
        elif awards:
            lexical_results = lexical_search_in_memory(query, awards, top_k=top_k)
        else:
            logger.warning("No data source available for lexical search")
    except Exception as e:
        logger.error(f"Lexical search failed: {e}")
    
    # Run semantic search
    semantic_results = []
    try:
        if vector_store_client:
            semantic_results = semantic_search(query, vector_store_client, top_k=top_k)
        else:
            logger.warning("No vector store available for semantic search")
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
    
    # Run hybrid search (combines lexical + semantic)
    hybrid_results = []
    try:
        if lexical_results or semantic_results:
            hybrid_results = hybrid_search(
                query,
                lexical_results,
                semantic_results,
                alpha=alpha,
                beta=beta,
                top_k=top_k
            )
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
    
    duration_ms = (time.time() - start_time) * 1000
    
    logger.info(
        f"Search completed in {duration_ms:.2f}ms",
        extra={
            "query": query,
            "lexical_count": len(lexical_results),
            "semantic_count": len(semantic_results),
            "hybrid_count": len(hybrid_results),
            "duration_ms": duration_ms
        }
    )
    
    # Deduplicate and group results by award_id
    hybrid_deduplicated = deduplicate_and_group_results(hybrid_results, group_chunks=True)
    lexical_deduplicated = deduplicate_and_group_results(lexical_results, group_chunks=True)
    semantic_deduplicated = deduplicate_and_group_results(semantic_results, group_chunks=True)
    
    return {
        "query": query,
        "hybrid_results": hybrid_deduplicated[:top_k],
        "lexical_results": lexical_deduplicated[:top_k],
        "semantic_results": semantic_deduplicated[:top_k],
        "metadata": {
            "hybrid_count": len(hybrid_deduplicated),
            "lexical_count": len(lexical_deduplicated),
            "semantic_count": len(semantic_deduplicated),
            "search_time_ms": duration_ms,
            "vector_store": settings.VECTOR_STORE
        }
    }
