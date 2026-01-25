"""
Search Module
Core search functionality for lexical, semantic, and hybrid search
"""
from src.core.search.lexical import (
    lexical_search_in_memory,
    lexical_search_supabase
)
from src.core.search.semantic import (
    semantic_search,
    semantic_search_pgvector,
    semantic_search_qdrant
)
from src.core.search.hybrid_search import (
    hybrid_search,
    search_all
)
from src.core.search.ranking import (
    apply_lexical_boost,
    deduplicate_by_award_id,
    rank_results
)

__all__ = [
    # Lexical search
    "lexical_search_in_memory",
    "lexical_search_supabase",
    # Semantic search
    "semantic_search",
    "semantic_search_pgvector",
    "semantic_search_qdrant",
    # Hybrid search
    "hybrid_search",
    "search_all",
    # Ranking
    "apply_lexical_boost",
    "deduplicate_by_award_id",
    "rank_results",
]

