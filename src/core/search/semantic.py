"""
Semantic Search
Vector similarity search using embeddings
"""
from typing import List, Dict, Optional, Any

from src.core.config import settings
from src.core.logging import get_logger
from src.indexing.embeddings import get_embedding_service

logger = get_logger(__name__)


def semantic_search_pgvector(
    query: str,
    pgvector_manager,
    top_k: int = 10,
    filter_agency: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Perform semantic search using pgvector
    
    Args:
        query: Search query string
        pgvector_manager: PgVectorManager instance
        top_k: Number of results to return
        filter_agency: Optional agency filter
    
    Returns:
        List of dictionaries with award_id and semantic_score
    """
    try:
        # Generate query embedding
        embedding_service = get_embedding_service()
        query_embedding = embedding_service.embed_text(query)
        
        # Search vectors
        results = pgvector_manager.search_vectors(
            query_vector=query_embedding,
            top_k=top_k,
            filter_agency=filter_agency
        )
        
        # Fetch full award data from Supabase for titles and agency
        formatted_results = []
        award_ids = list(set([r["award_id"] for r in results]))  # Get unique award IDs
        
        # Fetch award metadata from Supabase
        award_metadata = {}
        try:
            from src.database.supabase import get_supabase_client
            supabase_client = get_supabase_client()
            supabase_raw = supabase_client.get_client()
            
            if award_ids:
                # Use configured table name
                awards_table = settings.AWARDS_TABLE_NAME
                
                # Fetch ALL columns from schema
                all_columns = (
                    "award_id, award_number, title, award_status, institution, uei, duns, "
                    "most_recent_award_date, num_support_periods, pm, current_budget_period, "
                    "current_project_period, pi, supplement_budget_period, public_abstract, "
                    "public_abstract_url, agency"
                )
                
                try:
                    # Try to fetch all columns
                    metadata_response = supabase_raw.table(awards_table).select(
                        all_columns
                    ).in_("award_id", award_ids).execute()
                except Exception as e1:
                    # Fallback to basic columns if some don't exist
                    logger.warning(f"Could not fetch all columns, using fallback: {e1}")
                    try:
                        metadata_response = supabase_raw.table(awards_table).select(
                            "award_id, award_number, title, public_abstract, agency, public_abstract_url"
                        ).in_("award_id", award_ids).execute()
                    except:
                        # Final fallback
                        metadata_response = supabase_raw.table(awards_table).select(
                            "award_id, title, agency"
                        ).in_("award_id", award_ids).execute()
                
                for row in metadata_response.data:
                    # Store ALL columns in metadata
                    award_metadata[row["award_id"]] = {
                        "award_id": row.get("award_id", ""),
                        "award_number": row.get("award_number"),
                        "title": row.get("title", ""),
                        "agency": row.get("agency", ""),
                        "url": row.get("public_abstract_url") or row.get("url") or None,
                        "public_abstract_url": row.get("public_abstract_url") or row.get("url") or None,
                        "award_status": row.get("award_status"),
                        "institution": row.get("institution"),
                        "uei": row.get("uei"),
                        "duns": row.get("duns"),
                        "most_recent_award_date": row.get("most_recent_award_date"),
                        "num_support_periods": row.get("num_support_periods"),
                        "pm": row.get("pm"),
                        "current_budget_period": row.get("current_budget_period"),
                        "current_project_period": row.get("current_project_period"),
                        "pi": row.get("pi"),
                        "supplement_budget_period": row.get("supplement_budget_period"),
                        "public_abstract": row.get("public_abstract")
                    }
        except Exception as e:
            logger.warning(f"Could not fetch award metadata: {e}")
        
        # Format results with full metadata (keep all chunks, will deduplicate later)
        for result in results:
            award_id = result["award_id"]
            metadata = award_metadata.get(award_id, {})
            chunk_text = result.get("chunk_text", "")
            
            # Include ALL schema columns in result
            formatted_result = {
                "award_id": award_id,
                "award_number": metadata.get("award_number"),
                "semantic_score": result["similarity"],
                "title": metadata.get("title", ""),
                "agency": metadata.get("agency", ""),
                "url": metadata.get("url") or metadata.get("public_abstract_url"),
                "public_abstract_url": metadata.get("public_abstract_url") or metadata.get("url"),
                "chunk_index": result.get("chunk_index", 0),
                "chunk_text": chunk_text,
                "snippet": chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text,
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
            formatted_results.append(formatted_result)
        
        logger.debug(
            f"Semantic search (pgvector) found {len(formatted_results)} results",
            extra={"query": query, "top_k": top_k}
        )
        
        return formatted_results
        
    except Exception as e:
        logger.error(f"Semantic search (pgvector) failed: {e}", extra={"query": query})
        return []


def semantic_search_qdrant(
    query: str,
    qdrant_client,
    top_k: int = 10,
    filter_agency: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Perform semantic search using Qdrant
    
    Args:
        query: Search query string
        qdrant_client: QdrantClient instance
        top_k: Number of results to return
        filter_agency: Optional agency filter
    
    Returns:
        List of dictionaries with award_id and semantic_score
    """
    try:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        
        # Generate query embedding
        embedding_service = get_embedding_service()
        query_embedding = embedding_service.embed_text(query)
        
        # Build filter if agency specified
        search_filter = None
        if filter_agency:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="agency",
                        match=MatchValue(value=filter_agency)
                    )
                ]
            )
        
        # Search in Qdrant
        collection_name = "sbir_awards"
        search_results = qdrant_client.search(
            collection_name=collection_name,
            query_vector=query_embedding,
            limit=top_k,
            query_filter=search_filter
        )
        
        # Format results
        results = []
        for hit in search_results:
            # Get best score per award_id (deduplicate chunks)
            award_id = hit.payload.get("award_id", "")
            
            results.append({
                "award_id": award_id,
                "semantic_score": hit.score,
                "chunk_index": hit.payload.get("chunk_index", 0),
                "chunk_text": hit.payload.get("chunk_text", ""),
                "agency": hit.payload.get("agency", ""),
                "snippet": hit.payload.get("chunk_text", "")[:200] + "..."
            })
        
        # Deduplicate by award_id (keep highest score)
        award_scores = {}
        for result in results:
            award_id = result["award_id"]
            if award_id not in award_scores or result["semantic_score"] > award_scores[award_id]["semantic_score"]:
                award_scores[award_id] = result
        
        formatted_results = list(award_scores.values())
        formatted_results.sort(key=lambda x: x["semantic_score"], reverse=True)
        
        logger.debug(
            f"Semantic search (Qdrant) found {len(formatted_results)} results",
            extra={"query": query, "top_k": top_k}
        )
        
        return formatted_results[:top_k]
        
    except Exception as e:
        logger.error(f"Semantic search (Qdrant) failed: {e}", extra={"query": query})
        return []


def semantic_search(
    query: str,
    vector_store_client,
    top_k: int = 10,
    filter_agency: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Perform semantic search (auto-detects vector store type)
    
    Args:
        query: Search query string
        vector_store_client: pgvector manager or Qdrant client
        top_k: Number of results to return
        filter_agency: Optional agency filter
    
    Returns:
        List of dictionaries with award_id and semantic_score
    """
    if settings.VECTOR_STORE == "pgvector":
        return semantic_search_pgvector(query, vector_store_client, top_k, filter_agency)
    elif settings.VECTOR_STORE == "qdrant":
        return semantic_search_qdrant(query, vector_store_client, top_k, filter_agency)
    else:
        logger.error(f"Unknown vector store: {settings.VECTOR_STORE}")
        return []
