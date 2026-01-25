"""
Search Models
Pydantic models for search requests and responses
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Search request model"""
    query: str = Field(..., description="Search query string")
    top_k: int = Field(10, ge=1, le=100, description="Number of results to return")
    approach: Optional[str] = Field("hybrid", description="Search approach: 'hybrid', 'lexical', or 'semantic'")
    alpha: Optional[float] = Field(None, ge=0.0, le=1.0, description="Semantic weight (for hybrid)")
    beta: Optional[float] = Field(None, ge=0.0, description="Lexical boost (for hybrid)")
    filter_agency: Optional[str] = Field(None, description="Filter by agency")


class SearchResult(BaseModel):
    """Individual search result model with all schema columns"""
    # Core identifiers
    award_id: str
    award_number: Optional[str] = None
    
    # Basic info
    title: str = ""
    agency: str = ""
    snippet: str = ""
    url: Optional[str] = None  # public_abstract_url
    
    # Search scores
    final_score: Optional[float] = None
    lexical_score: Optional[float] = None
    semantic_score: Optional[float] = None
    chunk_index: Optional[int] = None
    chunks: Optional[List[Dict[str, Any]]] = None  # All matching chunks for this award
    
    # All schema columns (optional - only included if present)
    award_status: Optional[str] = None
    institution: Optional[str] = None
    uei: Optional[str] = None
    duns: Optional[str] = None
    most_recent_award_date: Optional[str] = None  # ISO date string
    num_support_periods: Optional[int] = None
    pm: Optional[str] = None
    current_budget_period: Optional[str] = None
    current_project_period: Optional[str] = None
    pi: Optional[str] = None
    supplement_budget_period: Optional[str] = None
    public_abstract: Optional[str] = None
    public_abstract_url: Optional[str] = None


class SearchResponse(BaseModel):
    """Search response model with all three approaches"""
    query: str
    hybrid_results: List[SearchResult] = Field(default_factory=list)
    lexical_results: List[SearchResult] = Field(default_factory=list)
    semantic_results: List[SearchResult] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class SingleSearchResponse(BaseModel):
    """Single search approach response"""
    query: str
    approach: str
    results: List[SearchResult]
    metadata: dict = Field(default_factory=dict)
