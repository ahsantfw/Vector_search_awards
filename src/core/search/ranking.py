"""
Ranking and Re-ranking
Functions for ranking and re-ranking search results
"""
from typing import List, Dict, Any

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def apply_lexical_boost(
    results: List[Dict[str, Any]],
    lexical_scores: Dict[str, float],
    beta: float = None
) -> List[Dict[str, Any]]:
    """
    Apply lexical boost to results
    
    Args:
        results: List of search results
        lexical_scores: Dictionary mapping award_id -> lexical_score
        beta: Lexical boost multiplier (defaults to settings.LEXICAL_BOOST)
    
    Returns:
        List of results with boosted scores
    """
    beta = beta or settings.LEXICAL_BOOST
    
    for result in results:
        award_id = result.get("award_id")
        lexical_score = lexical_scores.get(award_id, 0.0)
        
        # Boost final score if lexical match exists
        if lexical_score > 0:
            current_score = result.get("final_score", result.get("semantic_score", 0.0))
            result["final_score"] = current_score + (beta * lexical_score)
            result["lexical_score"] = lexical_score
    
    return results


def deduplicate_by_award_id(
    results: List[Dict[str, Any]],
    keep_highest_score: bool = True
) -> List[Dict[str, Any]]:
    """
    Deduplicate results by award_id, keeping the best score
    
    Args:
        results: List of search results (may have duplicates)
        keep_highest_score: If True, keep result with highest score
    
    Returns:
        Deduplicated list of results
    """
    award_results = {}
    
    for result in results:
        award_id = result.get("award_id")
        if not award_id:
            continue
        
        score_key = "final_score" if "final_score" in result else "semantic_score" if "semantic_score" in result else "lexical_score"
        current_score = result.get(score_key, 0.0)
        
        if award_id not in award_results:
            award_results[award_id] = result
        elif keep_highest_score:
            existing_score = award_results[award_id].get(score_key, 0.0)
            if current_score > existing_score:
                award_results[award_id] = result
    
    return list(award_results.values())


def rank_results(
    results: List[Dict[str, Any]],
    sort_key: str = "final_score",
    reverse: bool = True
) -> List[Dict[str, Any]]:
    """
    Rank results by score
    
    Args:
        results: List of search results
        sort_key: Key to sort by (default: "final_score")
        reverse: Sort in descending order (default: True)
    
    Returns:
        Sorted list of results
    """
    return sorted(results, key=lambda x: x.get(sort_key, 0.0), reverse=reverse)
