"""
Chunking Service using LangChain
Optimized chunking for SBIR award data using LangChain's RecursiveCharacterTextSplitter

Benefits:
- Well-tested and optimized
- Handles edge cases automatically
- Token-aware chunking with tiktoken
- Much simpler and faster than manual implementation
"""
import hashlib
from typing import List, Dict, Optional
from functools import lru_cache

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    RecursiveCharacterTextSplitter = None  # type: ignore

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class ChunkingService:
    """Service for chunking text using LangChain's optimized text splitter"""
    
    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ):
        """
        Initialize chunking service with LangChain
        
        Args:
            chunk_size: Maximum tokens per chunk (defaults to settings.CHUNK_SIZE)
            chunk_overlap: Overlap tokens between chunks (defaults to settings.CHUNK_OVERLAP)
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError(
                "langchain-text-splitters is not installed. "
                "Install it with: pip install langchain-text-splitters"
            )
        
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        
        # Initialize LangChain's RecursiveCharacterTextSplitter
        # This is optimized, well-tested, and handles many edge cases
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=self._count_tokens,  # Use token count, not character count
            separators=[
                "\n\n",  # Paragraphs first
                "\n",    # Then lines
                ". ",    # Then sentences
                " ",     # Then words
                "",      # Finally characters
            ],
            is_separator_regex=False,
        )
        
        logger.info(
            "ChunkingService initialized (using LangChain)",
            extra={
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
                "method": "LangChain RecursiveCharacterTextSplitter"
            }
        )
    
    @lru_cache(maxsize=1)
    def _get_tokenizer(self):
        """Get tiktoken tokenizer (cached)"""
        try:
            import tiktoken
            return tiktoken.get_encoding("cl100k_base")
        except ImportError:
            logger.warning("tiktoken not available, using character count")
            return None
    
    def _count_tokens(self, text: str) -> int:
        """
        Count tokens in text using tiktoken
        
        Args:
            text: Input text
        
        Returns:
            Number of tokens
        """
        tokenizer = self._get_tokenizer()
        if tokenizer:
            return len(tokenizer.encode(text))
        else:
            # Fallback to character count if tiktoken not available
            return len(text)
    
    def chunk_text(
        self,
        text: str,
        field_name: str = "abstract"
    ) -> List[Dict[str, any]]:
        """
        Chunk text using LangChain's optimized splitter
        
        Args:
            text: Text to chunk
            field_name: Name of the field being chunked (for metadata)
        
        Returns:
            List of chunk dictionaries with:
            - chunk_text: The chunk text
            - chunk_index: Index of chunk (0-based)
            - token_count: Number of tokens in chunk
            - field_name: Source field name
            - text_hash: SHA256 hash of chunk text
        """
        if not text or not text.strip():
            logger.warning(f"Empty text provided for chunking (field: {field_name})")
            return []
        
        # Use LangChain's splitter (much faster and more reliable!)
        chunks = self.text_splitter.split_text(text)
        
        # Convert to our format with metadata
        result = []
        for idx, chunk_text in enumerate(chunks):
            chunk_text = chunk_text.strip()
            if not chunk_text:
                continue
            
            # Count tokens
            token_count = self._count_tokens(chunk_text)
            
            # Generate hash for incremental processing
            text_hash = hashlib.sha256(chunk_text.encode()).hexdigest()
            
            result.append({
                "chunk_text": chunk_text,
                "chunk_index": idx,
                "token_count": token_count,
                "field_name": field_name,
                "text_hash": text_hash
            })
        
        logger.debug(
            f"Chunked text into {len(result)} chunks",
            extra={
                "field_name": field_name,
                "chunk_count": len(result),
                "method": "LangChain"
            }
        )
        
        return result
    
    def chunk_award(
        self,
        award: Dict,
        fields: Optional[List[str]] = None
    ) -> List[Dict[str, any]]:
        """
        Chunk an award record with field-specific strategies

        For DOE technical content, we use different chunking strategies:
        - Technical content (abstracts): 400 tokens, 40 overlap
        - Titles: 100 tokens, 20 overlap
        - Combined: 500 tokens, 50 overlap for cross-field context

        Args:
            award: Award dictionary
            fields: List of field names to chunk (default: auto-detect)

        Returns:
            List of chunk dictionaries with award metadata
        """
        if fields is None:
            # Auto-detect available technical fields
            available_fields = []
            if award.get("title"):
                available_fields.append("title")
            if award.get("public_abstract") or award.get("abstract"):
                available_fields.append("abstract")
            fields = available_fields

        if not fields:
            logger.warning(f"No text fields found for award {award.get('award_id', 'unknown')}")
            return []

        all_chunks = []
        chunk_index_counter = 0  # Global counter for unique chunk indices

        # Strategy 1: Chunk technical content (abstract) with optimal settings
        if "abstract" in fields:
            abstract_text = award.get("public_abstract") or award.get("abstract", "")
            if abstract_text and len(abstract_text.strip()) > 50:  # Minimum content check
                # Use optimized settings for technical content
                tech_chunks = self.chunk_text(
                    abstract_text.strip(),
                    field_name="abstract"
                )
                for chunk in tech_chunks:
                    chunk.update({
                        "award_id": award.get("award_id", ""),
                        "agency": award.get("agency", ""),
                        "source_fields": ["abstract"],
                        "content_type": "technical",
                        "chunk_index": chunk_index_counter  # Assign unique index
                    })
                    chunk_index_counter += 1
                all_chunks.extend(tech_chunks)

        # Strategy 2: Chunk titles separately (smaller chunks for exact matching)
        if "title" in fields:
            title_text = award.get("title", "")
            if title_text and len(title_text.strip()) > 10:
                # Smaller chunks for titles to preserve exact phrases
                title_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=100,  # Smaller for titles
                    chunk_overlap=20,  # Less overlap
                    length_function=self._count_tokens,
                    separators=[" ", "", "."],  # Word and character level
                    is_separator_regex=False,
                )
                title_chunks_raw = title_splitter.split_text(title_text.strip())

                for chunk_text in title_chunks_raw:
                    chunk_text = chunk_text.strip()
                    if len(chunk_text) < 5:  # Skip very short chunks
                        continue

                    token_count = self._count_tokens(chunk_text)
                    text_hash = hashlib.sha256(chunk_text.encode()).hexdigest()

                    title_chunk = {
                        "chunk_text": chunk_text,
                        "chunk_index": chunk_index_counter,  # Use global counter
                        "token_count": token_count,
                        "field_name": "title",
                        "text_hash": text_hash,
                        "award_id": award.get("award_id", ""),
                        "agency": award.get("agency", ""),
                        "source_fields": ["title"],
                        "content_type": "title"
                    }
                    all_chunks.append(title_chunk)
                    chunk_index_counter += 1

        # Strategy 3: Create some overlapping chunks across title+abstract for context
        if len(fields) > 1 and all_chunks:
            # Combine title + first part of abstract for contextual chunks
            title = award.get("title", "")
            abstract = (award.get("public_abstract") or award.get("abstract", ""))[:1000]  # First 1000 chars

            if title and abstract:
                combined = f"{title}. {abstract}"
                context_chunks = self.chunk_text(combined, field_name="title_abstract_context")

                # Only keep the first few context chunks to avoid duplication
                for chunk in context_chunks[:2]:  # Limit to 2 context chunks
                    chunk.update({
                        "award_id": award.get("award_id", ""),
                        "agency": award.get("agency", ""),
                        "source_fields": ["title", "abstract"],
                        "content_type": "context",
                        "chunk_index": chunk_index_counter  # Assign unique index
                    })
                    chunk_index_counter += 1
                all_chunks.extend(context_chunks[:2])

        logger.info(
            f"Created {len(all_chunks)} chunks for award {award.get('award_id', 'unknown')}: "
            f"technical={len([c for c in all_chunks if c.get('content_type') == 'technical'])}, "
            f"title={len([c for c in all_chunks if c.get('content_type') == 'title'])}, "
            f"context={len([c for c in all_chunks if c.get('content_type') == 'context'])}"
        )

        return all_chunks


# Singleton instance
_chunking_service: Optional[ChunkingService] = None


def get_chunking_service() -> ChunkingService:
    """
    Get singleton chunking service instance
    
    Returns:
        ChunkingService: Configured chunking service
    """
    global _chunking_service
    
    if _chunking_service is None:
        _chunking_service = ChunkingService()
    
    return _chunking_service


# Convenience function
def chunk_text(text: str, field_name: str = "abstract") -> List[Dict[str, any]]:
    """
    Convenience function to chunk text
    
    Args:
        text: Text to chunk
        field_name: Field name
    
    Returns:
        List of chunk dictionaries
    """
    service = get_chunking_service()
    return service.chunk_text(text, field_name)
