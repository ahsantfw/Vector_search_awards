"""
Deduplication and Grouping
Groups search results by award_id and collects all matching chunks
"""
from typing import List, Dict, Any, Optional

from src.core.logging import get_logger

logger = get_logger(__name__)


def deduplicate_and_group_results(
    results: List[Dict[str, Any]],
    group_chunks: bool = True
) -> List[Dict[str, Any]]:
    """
    Deduplicate results by award_id and group all chunks together
    
    Args:
        results: List of search results (may contain multiple chunks per award)
        group_chunks: If True, group all chunks under each award
    
    Returns:
        List of unique awards with grouped chunks
    """
    if not results:
        return []
    
    # Group by award_id
    award_map: Dict[str, Dict[str, Any]] = {}
    
    for result in results:
        award_id = result.get("award_id", "")
        if not award_id:
            continue
        
        if award_id not in award_map:
            # First occurrence - create award entry
            award_map[award_id] = {
                "award_id": award_id,
                "title": result.get("title", ""),
                "agency": result.get("agency", ""),
                "url": result.get("url"),
                "final_score": result.get("final_score"),
                "lexical_score": result.get("lexical_score"),
                "semantic_score": result.get("semantic_score"),
                "chunks": [] if group_chunks else None,
                "snippet": result.get("snippet", ""),  # Best snippet
                "best_chunk_index": result.get("chunk_index", 0)
            }
        
        # Update best scores if this result has higher scores
        current = award_map[award_id]
        
        # Update final_score if higher
        if result.get("final_score") is not None:
            if current["final_score"] is None or result["final_score"] > current["final_score"]:
                current["final_score"] = result["final_score"]
        
        # Update lexical_score if higher
        if result.get("lexical_score") is not None:
            if current["lexical_score"] is None or result["lexical_score"] > current["lexical_score"]:
                current["lexical_score"] = result["lexical_score"]
        
        # Update semantic_score if higher
        if result.get("semantic_score") is not None:
            if current["semantic_score"] is None or result["semantic_score"] > current["semantic_score"]:
                current["semantic_score"] = result["semantic_score"]
                # Update snippet from best semantic match
                if result.get("snippet"):
                    current["snippet"] = result["snippet"]
                    current["best_chunk_index"] = result.get("chunk_index", 0)
        
        # Add chunk if grouping is enabled
        if group_chunks:
            chunk_data = {
                "chunk_index": result.get("chunk_index", 0),
                "chunk_text": result.get("chunk_text", result.get("snippet", "")),
                "semantic_score": result.get("semantic_score"),
                "lexical_score": result.get("lexical_score")
            }
            # Only add if not duplicate chunk_index
            existing_indices = {c["chunk_index"] for c in current["chunks"]}
            if chunk_data["chunk_index"] not in existing_indices:
                current["chunks"].append(chunk_data)
    
    # Convert to list and sort by final_score (or best available score)
    deduplicated = list(award_map.values())
    
    # Sort chunks within each award by score (best first)
    for award in deduplicated:
        if award["chunks"]:
            award["chunks"].sort(
                key=lambda c: c.get("semantic_score", 0) or c.get("lexical_score", 0),
                reverse=True
            )
    
    # Sort awards by final_score (descending)
    deduplicated.sort(
        key=lambda x: x.get("final_score") or x.get("semantic_score") or x.get("lexical_score") or 0,
        reverse=True
    )
    
    logger.debug(
        f"Deduplicated {len(results)} results to {len(deduplicated)} unique awards",
        extra={"group_chunks": group_chunks}
    )
    
    return deduplicated

