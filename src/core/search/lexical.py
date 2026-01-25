"""
Lexical Search
Exact match search using Supabase Full-Text Search (FTS)
"""
from typing import List, Dict, Optional, Any
import re

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def lexical_search_supabase(
    query: str,
    supabase_client,
    top_k: int = 10,
    fields: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Perform lexical search using Supabase Full-Text Search
    
    Args:
        query: Search query string
        supabase_client: Supabase client instance
        top_k: Number of results to return
        fields: Fields to search (default: ["title", "abstract"])
    
    Returns:
        List of dictionaries with award_id and lexical_score
    """
    if fields is None:
        fields = ["title", "abstract"]
    
    try:
        # Use Supabase's ilike for text search (works with FTS indexes)
        # Search in both title and abstract using OR condition
        query_escaped = query.replace("'", "''")  # Escape single quotes
        
        # Use configured table name
        awards_table = settings.AWARDS_TABLE_NAME
        
        # Select ALL columns from schema for complete data
        all_columns = (
            "award_id, award_number, title, award_status, institution, uei, duns, "
            "most_recent_award_date, num_support_periods, pm, current_budget_period, "
            "current_project_period, pi, supplement_budget_period, public_abstract, "
            "public_abstract_url, agency"
        )
        
        # Search title first (fetch all columns)
        try:
            title_response = supabase_client.table(awards_table).select(
                all_columns
            ).ilike("title", f"%{query_escaped}%").limit(top_k * 2).execute()
        except Exception as e:
            # Fallback to basic columns if some don't exist
            logger.warning(f"Could not fetch all columns, using fallback: {e}")
            title_response = supabase_client.table(awards_table).select(
                "award_id, award_number, title, public_abstract, agency, public_abstract_url"
            ).ilike("title", f"%{query_escaped}%").limit(top_k * 2).execute()
        
        # Search abstract (fetch all columns)
        try:
            abstract_response = supabase_client.table(awards_table).select(
                all_columns
            ).ilike("public_abstract", f"%{query_escaped}%").limit(top_k * 2).execute()
        except Exception as e:
            # Fallback to basic columns if some don't exist
            logger.warning(f"Could not fetch all columns, using fallback: {e}")
            abstract_response = supabase_client.table(awards_table).select(
                "award_id, award_number, title, public_abstract, agency, public_abstract_url"
            ).ilike("public_abstract", f"%{query_escaped}%").limit(top_k * 2).execute()
        
        # Combine and deduplicate
        seen_ids = set()
        all_rows = []
        
        for row in title_response.data:
            if row.get("award_id") not in seen_ids:
                all_rows.append(row)
                seen_ids.add(row.get("award_id"))
        
        for row in abstract_response.data:
            if row.get("award_id") not in seen_ids:
                all_rows.append(row)
                seen_ids.add(row.get("award_id"))
        
        results = []
        for row in all_rows:
            # Calculate lexical score based on term frequency
            abstract_text = row.get("public_abstract") or row.get("abstract", "")
            score = _calculate_lexical_score(query, row.get("title", ""), abstract_text)
            
            if score > 0:  # Only include results with matches
                # Include ALL schema columns in result
                result = {
                    "award_id": row.get("award_id", ""),
                    "award_number": row.get("award_number"),
                    "lexical_score": score,
                    "title": row.get("title", ""),
                    "agency": row.get("agency", ""),
                    "url": row.get("public_abstract_url") or row.get("url") or None,
                    "public_abstract_url": row.get("public_abstract_url") or row.get("url") or None,
                    "snippet": _get_snippet(abstract_text, query),
                    # All other schema columns
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
                    "public_abstract": abstract_text
                }
                results.append(result)
        
        # Sort by score and limit
        results = sorted(results, key=lambda x: x["lexical_score"], reverse=True)[:top_k]
        
        logger.debug(
            f"Lexical search found {len(results)} results",
            extra={"query": query, "top_k": top_k}
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Lexical search failed: {e}", extra={"query": query}, exc_info=True)
        # Fallback to simple text matching
        return _lexical_search_fallback(query, supabase_client, top_k)


def lexical_search_in_memory(
    query: str,
    awards: List[Dict[str, Any]],
    top_k: int = 10
) -> List[Dict[str, Any]]:
    """
    Perform lexical search on in-memory award list (for testing/fallback)
    
    Args:
        query: Search query string
        awards: List of award dictionaries
        top_k: Number of results to return
    
    Returns:
        List of dictionaries with award_id and lexical_score
    """
    query_terms = query.lower().split()
    results = []
    
    for award in awards:
        score = 0.0
        title = award.get("title", "").lower()
        abstract = award.get("abstract", "").lower()
        
        # Exact title match boost
        if query.lower() == title:
            score += 100.0
        
        # Exact phrase match in title
        if query.lower() in title:
            score += 50.0
        
        # Term matching
        for term in query_terms:
            # Title matches are worth more
            if term in title:
                score += 5.0
            # Abstract matches
            if term in abstract:
                score += 1.0
        
        # Normalize score to 0-1 range (for scores < 100)
        if score > 0:
            normalized_score = min(score / 100.0, 1.0) if score < 100 else 1.0
            
            results.append({
                "award_id": award.get("award_id", ""),
                "lexical_score": normalized_score,
                "title": award.get("title", ""),
                "agency": award.get("agency", ""),
                "snippet": _get_snippet(abstract, query)
            })
    
    # Sort by score and return top_k
    sorted_results = sorted(results, key=lambda x: x["lexical_score"], reverse=True)
    
    logger.debug(
        f"Lexical search (in-memory) found {len(sorted_results)} results",
        extra={"query": query, "top_k": top_k}
    )
    
    return sorted_results[:top_k]


def _calculate_lexical_score(
    query: str,
    title: str,
    abstract: str
) -> float:
    """
    Calculate lexical score based on term frequency
    
    Args:
        query: Search query
        title: Award title
        abstract: Award abstract
    
    Returns:
        Lexical score (0.0 to 1.0)
    """
    query_terms = query.lower().split()
    title_lower = title.lower()
    abstract_lower = abstract.lower()
    
    score = 0.0
    
    # Exact title match
    if query.lower() == title_lower:
        return 1.0
    
    # Exact phrase match in title
    if query.lower() in title_lower:
        score += 0.8
    
    # Term frequency in title (weighted higher)
    title_matches = sum(1 for term in query_terms if term in title_lower)
    if title_matches > 0:
        score += (title_matches / len(query_terms)) * 0.5
    
    # Term frequency in abstract
    abstract_matches = sum(1 for term in query_terms if term in abstract_lower)
    if abstract_matches > 0:
        score += (abstract_matches / len(query_terms)) * 0.2
    
    return min(score, 1.0)


def _get_snippet(text: str, query: str, max_length: int = 200) -> str:
    """
    Extract a snippet from text containing query terms
    
    Args:
        text: Full text
        query: Search query
        max_length: Maximum snippet length
    
    Returns:
        Text snippet with query terms highlighted
    """
    if not text:
        return ""
    
    query_terms = query.lower().split()
    text_lower = text.lower()
    
    # Find first occurrence of any query term
    for term in query_terms:
        idx = text_lower.find(term.lower())
        if idx != -1:
            # Extract snippet around match
            start = max(0, idx - 50)
            end = min(len(text), idx + max_length - 50)
            snippet = text[start:end]
            
            # Add ellipsis if needed
            if start > 0:
                snippet = "..." + snippet
            if end < len(text):
                snippet = snippet + "..."
            
            return snippet
    
    # Fallback: return beginning of text
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


def _lexical_search_fallback(
    query: str,
    supabase_client,
    top_k: int
) -> List[Dict[str, Any]]:
    """
    Fallback lexical search if FTS fails
    
    Args:
        query: Search query
        supabase_client: Supabase client
        top_k: Number of results
    
    Returns:
        List of search results
    """
    try:
        # Use configured table name
        awards_table = settings.AWARDS_TABLE_NAME
        
        # Simple text search fallback (fetch all columns)
        all_columns = (
            "award_id, award_number, title, award_status, institution, uei, duns, "
            "most_recent_award_date, num_support_periods, pm, current_budget_period, "
            "current_project_period, pi, supplement_budget_period, public_abstract, "
            "public_abstract_url, agency"
        )
        
        try:
            response = supabase_client.table(awards_table).select(
                all_columns
            ).ilike("title", f"%{query}%").limit(top_k).execute()
        except Exception as e:
            logger.warning(f"Could not fetch all columns in fallback, using basic: {e}")
            response = supabase_client.table(awards_table).select(
                "award_id, award_number, title, public_abstract, agency, public_abstract_url"
            ).ilike("title", f"%{query}%").limit(top_k).execute()
        
        results = []
        for row in response.data:
            abstract_text = row.get("public_abstract") or row.get("abstract", "")
            score = _calculate_lexical_score(
                query,
                row.get("title", ""),
                abstract_text
            )
            
            # Include ALL schema columns
            result = {
                "award_id": row.get("award_id", ""),
                "award_number": row.get("award_number"),
                "lexical_score": score,
                "title": row.get("title", ""),
                "agency": row.get("agency", ""),
                "url": row.get("public_abstract_url") or row.get("url") or None,
                "public_abstract_url": row.get("public_abstract_url") or row.get("url") or None,
                "snippet": _get_snippet(abstract_text, query),
                # All other schema columns
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
                "public_abstract": abstract_text
            }
            results.append(result)
        
        return sorted(results, key=lambda x: x["lexical_score"], reverse=True)
        
    except Exception as e:
        logger.error(f"Fallback lexical search failed: {e}")
        return []
