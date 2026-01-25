"""
Embedding Service
OpenAI embedding generation for SBIR award chunks

Implements:
- OpenAI text-embedding-3-large (3072 dimensions)
- Async batch processing for efficiency
- Error handling and retries
- Caching support (text_hash-based)
- Cost tracking
- Parallel processing with asyncio
"""
import time
import asyncio
from typing import List, Dict, Optional, Any
from functools import lru_cache

try:
    from openai import OpenAI, AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None  # type: ignore
    AsyncOpenAI = None  # type: ignore

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """Service for generating embeddings using OpenAI API"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        dimension: Optional[int] = None,
        batch_size: int = 100
    ):
        """
        Initialize embedding service
        
        Args:
            api_key: OpenAI API key (defaults to settings.OPENAI_API_KEY)
            model: Embedding model name (defaults to settings.EMBEDDING_MODEL)
            dimension: Embedding dimension (defaults to settings.EMBEDDING_DIMENSION)
            batch_size: Number of texts to process per batch
        """
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai package is not installed. "
                "Install it with: pip install openai"
            )
        
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.EMBEDDING_MODEL
        self.dimension = dimension or settings.EMBEDDING_DIMENSION
        self.batch_size = batch_size
        
        if not self.api_key:
            logger.warning(
                "OpenAI API key not configured. "
                "Set OPENAI_API_KEY environment variable."
            )
        
        # Initialize OpenAI clients (sync and async)
        if self.api_key:
            try:
                self.client = OpenAI(api_key=self.api_key)
                self.async_client = AsyncOpenAI(api_key=self.api_key)
                logger.info("OpenAI clients initialized", extra={"model": self.model})
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                raise
        else:
            self.client = None
            self.async_client = None
        
        logger.info(
            "EmbeddingService initialized",
            extra={
                "model": self.model,
                "dimension": self.dimension,
                "batch_size": batch_size
            }
        )
    
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text
        
        Args:
            text: Text to embed
        
        Returns:
            List of floats representing the embedding vector
        
        Raises:
            RuntimeError: If API key not configured
            Exception: If embedding generation fails
        """
        if not self.client:
            raise RuntimeError("OpenAI API key not configured")
        
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return []
        
        try:
            logger.debug("Generating embedding", extra={"text_length": len(text)})
            
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimension
            )
            
            embedding = response.data[0].embedding
            
            logger.debug(
                "Embedding generated",
                extra={
                    "dimension": len(embedding),
                    "model": response.model
                }
            )
            
            return embedding
            
        except Exception as e:
            logger.error("Failed to generate embedding", extra={"error": str(e)})
            raise
    
    def embed_batch(
        self,
        texts: List[str],
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts
        
        Args:
            texts: List of texts to embed
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (exponential backoff)
        
        Returns:
            List of embedding vectors
        
        Raises:
            RuntimeError: If API key not configured
            Exception: If embedding generation fails after retries
        """
        if not self.client:
            raise RuntimeError("OpenAI API key not configured")
        
        if not texts:
            return []
        
        # Filter empty texts
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            logger.warning("No valid texts provided for embedding")
            return []
        
        # Track which texts were valid
        valid_indices = [i for i, t in enumerate(texts) if t and t.strip()]
        
        for attempt in range(max_retries):
            try:
                logger.debug(
                    f"Generating embeddings for batch (attempt {attempt + 1}/{max_retries})",
                    extra={"batch_size": len(valid_texts)}
                )
                
                response = self.client.embeddings.create(
                    model=self.model,
                    input=valid_texts,
                    dimensions=self.dimension
                )
                
                # Extract embeddings
                embeddings = [item.embedding for item in response.data]
                
                # Create full result list (with None for empty texts)
                result = [None] * len(texts)
                for idx, emb in zip(valid_indices, embeddings):
                    result[idx] = emb
                
                logger.info(
                    f"Generated {len(embeddings)} embeddings",
                    extra={
                        "batch_size": len(valid_texts),
                        "model": response.model
                    }
                )
                
                return result
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if it's a rate limit error
                if "rate limit" in error_str or "429" in error_str:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Rate limit hit, retrying in {wait_time:.1f}s",
                        extra={"attempt": attempt + 1, "max_retries": max_retries}
                    )
                    time.sleep(wait_time)
                    continue
                
                # Check if it's a temporary error
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Embedding failed, retrying in {wait_time:.1f}s",
                        extra={"error": str(e), "attempt": attempt + 1}
                    )
                    time.sleep(wait_time)
                    continue
                
                # Final attempt failed
                logger.error(
                    "Failed to generate embeddings after retries",
                    extra={"error": str(e), "attempts": max_retries}
                )
                raise
        
        # Should not reach here, but just in case
        raise RuntimeError("Failed to generate embeddings after all retries")
    
    async def embed_batch_async(
        self,
        texts: List[str],
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts (ASYNC)
        
        Args:
            texts: List of texts to embed
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (exponential backoff)
        
        Returns:
            List of embedding vectors
        
        Raises:
            RuntimeError: If API key not configured
            Exception: If embedding generation fails after retries
        """
        if not self.async_client:
            raise RuntimeError("OpenAI API key not configured")
        
        if not texts:
            return []
        
        # Filter empty texts
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            logger.warning("No valid texts provided for embedding")
            return []
        
        # Track which texts were valid
        valid_indices = [i for i, t in enumerate(texts) if t and t.strip()]
        
        for attempt in range(max_retries):
            try:
                logger.debug(
                    f"Generating embeddings async for batch (attempt {attempt + 1}/{max_retries})",
                    extra={"batch_size": len(valid_texts)}
                )
                
                response = await self.async_client.embeddings.create(
                    model=self.model,
                    input=valid_texts,
                    dimensions=self.dimension
                )
                
                # Extract embeddings
                embeddings = [item.embedding for item in response.data]
                
                # Create full result list (with None for empty texts)
                result = [None] * len(texts)
                for idx, emb in zip(valid_indices, embeddings):
                    result[idx] = emb
                
                logger.info(
                    f"Generated {len(embeddings)} embeddings (async)",
                    extra={
                        "batch_size": len(valid_texts),
                        "model": response.model
                    }
                )
                
                return result
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if it's a rate limit error
                if "rate limit" in error_str or "429" in error_str:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Rate limit hit, retrying in {wait_time:.1f}s",
                        extra={"attempt": attempt + 1, "max_retries": max_retries}
                    )
                    await asyncio.sleep(wait_time)
                    continue
                
                # Check if it's a temporary error
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Embedding failed, retrying in {wait_time:.1f}s",
                        extra={"error": str(e), "attempt": attempt + 1}
                    )
                    await asyncio.sleep(wait_time)
                    continue
                
                # Final attempt failed
                logger.error(
                    "Failed to generate embeddings after retries",
                    extra={"error": str(e), "attempts": max_retries}
                )
                raise
        
        # Should not reach here, but just in case
        raise RuntimeError("Failed to generate embeddings after all retries")
    
    async def embed_chunks_async(
        self,
        chunks: List[Dict[str, Any]],
        use_cache: bool = True,
        cache_store: Optional[Dict[str, List[float]]] = None,
        max_concurrent: int = 20,
        batch_size: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Generate embeddings for chunk dictionaries (ASYNC with parallel processing)
        
        Args:
            chunks: List of chunk dictionaries (from chunking service)
            use_cache: Whether to use cached embeddings (text_hash-based)
            cache_store: Dictionary mapping text_hash -> embedding
            max_concurrent: Maximum concurrent API calls
            batch_size: Number of chunks per API call
        
        Returns:
            List of chunk dictionaries with 'embedding' field added
        """
        if not chunks:
            return []
        
        if cache_store is None:
            cache_store = {}
        
        # Separate chunks into cached and uncached
        cached_chunks = []
        uncached_chunks = []
        uncached_indices = []
        
        for idx, chunk in enumerate(chunks):
            text_hash = chunk.get("text_hash")
            
            if use_cache and text_hash and text_hash in cache_store:
                # Use cached embedding
                chunk["embedding"] = cache_store[text_hash]
                cached_chunks.append((idx, chunk))
            else:
                # Need to generate embedding
                uncached_chunks.append(chunk)
                uncached_indices.append(idx)
        
        logger.info(
            "Embedding chunks (async)",
            extra={
                "total": len(chunks),
                "cached": len(cached_chunks),
                "uncached": len(uncached_chunks),
                "max_concurrent": max_concurrent,
                "batch_size": batch_size
            }
        )
        
        if uncached_chunks:
            logger.info(f"Processing {len(uncached_chunks)} uncached chunks in {len(uncached_chunks) // batch_size + 1} batches")
        
        # Generate embeddings for uncached chunks in parallel batches
        if uncached_chunks:
            texts = [chunk["chunk_text"] for chunk in uncached_chunks]
            
            # Split into batches
            batches = []
            for i in range(0, len(texts), batch_size):
                batches.append((i, texts[i:i + batch_size]))
            
            # Process batches concurrently with semaphore to limit concurrency
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def process_batch(batch_idx: int, batch_texts: List[str]) -> tuple[int, List[List[float]]]:
                async with semaphore:
                    try:
                        embeddings = await self.embed_batch_async(batch_texts)
                        logger.debug(f"Completed embedding batch {batch_idx + 1}/{len(batches)}")
                        return batch_idx, embeddings
                    except Exception as e:
                        logger.error(f"Failed to embed batch {batch_idx}", extra={"error": str(e)})
                        return batch_idx, [None] * len(batch_texts)
            
            # Create tasks for all batches
            tasks = [
                process_batch(batch_idx, batch_texts)
                for batch_idx, batch_texts in batches
            ]
            
            # Wait for all batches to complete
            # Use return_exceptions=True to prevent one failure from crashing everything
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Handle exceptions in results
            valid_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        f"Exception in embedding batch {i}",
                        extra={"error": str(result), "exception_type": type(result).__name__},
                        exc_info=result
                    )
                    # Return empty embeddings for failed batch
                    batch_texts = batches[i][1]
                    valid_results.append((i, [None] * len(batch_texts)))
                else:
                    valid_results.append(result)
            
            results = valid_results
            
            # Sort results by batch index and combine
            results.sort(key=lambda x: x[0])
            all_embeddings = []
            for _, embeddings in results:
                all_embeddings.extend(embeddings)
            
            # Add embeddings to chunks and update cache
            for chunk, embedding in zip(uncached_chunks, all_embeddings):
                if embedding:
                    chunk["embedding"] = embedding
                    # Update cache
                    text_hash = chunk.get("text_hash")
                    if text_hash and use_cache:
                        cache_store[text_hash] = embedding
        
        # Combine cached and newly embedded chunks in original order
        result = [None] * len(chunks)
        
        # Place cached chunks
        for idx, chunk in cached_chunks:
            result[idx] = chunk
        
        # Place newly embedded chunks
        for idx, chunk in zip(uncached_indices, uncached_chunks):
            result[idx] = chunk
        
        return result
    
    def embed_chunks(
        self,
        chunks: List[Dict[str, Any]],
        use_cache: bool = True,
        cache_store: Optional[Dict[str, List[float]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate embeddings for chunk dictionaries
        
        Args:
            chunks: List of chunk dictionaries (from chunking service)
            use_cache: Whether to use cached embeddings (text_hash-based)
            cache_store: Dictionary mapping text_hash -> embedding
        
        Returns:
            List of chunk dictionaries with 'embedding' field added
        """
        if not chunks:
            return []
        
        if cache_store is None:
            cache_store = {}
        
        # Separate chunks into cached and uncached
        cached_chunks = []
        uncached_chunks = []
        uncached_indices = []
        
        for idx, chunk in enumerate(chunks):
            text_hash = chunk.get("text_hash")
            
            if use_cache and text_hash and text_hash in cache_store:
                # Use cached embedding
                chunk["embedding"] = cache_store[text_hash]
                cached_chunks.append(chunk)
            else:
                # Need to generate embedding
                uncached_chunks.append(chunk)
                uncached_indices.append(idx)
        
        logger.info(
            "Embedding chunks",
            extra={
                "total": len(chunks),
                "cached": len(cached_chunks),
                "uncached": len(uncached_chunks)
            }
        )
        
        # Generate embeddings for uncached chunks
        if uncached_chunks:
            texts = [chunk["chunk_text"] for chunk in uncached_chunks]
            
            # Process in batches
            all_embeddings = []
            for i in range(0, len(texts), self.batch_size):
                batch_texts = texts[i:i + self.batch_size]
                batch_embeddings = self.embed_batch(batch_texts)
                all_embeddings.extend(batch_embeddings)
            
            # Add embeddings to chunks and update cache
            for chunk, embedding in zip(uncached_chunks, all_embeddings):
                if embedding:
                    chunk["embedding"] = embedding
                    # Update cache
                    text_hash = chunk.get("text_hash")
                    if text_hash and use_cache:
                        cache_store[text_hash] = embedding
        
        # Combine cached and newly embedded chunks
        result = [None] * len(chunks)
        for chunk in cached_chunks + uncached_chunks:
            # Find original index
            for idx, orig_chunk in enumerate(chunks):
                if orig_chunk.get("text_hash") == chunk.get("text_hash"):
                    result[idx] = chunk
                    break
        
        return result
    
    def estimate_cost(self, num_tokens: int) -> float:
        """
        Estimate cost for embedding generation
        
        Args:
            num_tokens: Number of tokens to embed
        
        Returns:
            Estimated cost in USD
        """
        # Cost per 1K tokens for text-embedding-3-large
        # 3072 dimensions: $0.00013 per 1K tokens
        # 256 dimensions: $0.00002 per 1K tokens
        
        if self.dimension == 3072:
            cost_per_1k = 0.00013
        elif self.dimension == 256:
            cost_per_1k = 0.00002
        else:
            # Default to 3072 pricing
            cost_per_1k = 0.00013
        
        cost = (num_tokens / 1000) * cost_per_1k
        return cost


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service():
    """
    Get singleton embedding service instance
    Automatically chooses between OpenAI and Sentence Transformers based on config
    
    Returns:
        EmbeddingService or SentenceTransformersEmbeddingService
    """
    global _embedding_service
    
    # Check if we should use Sentence Transformers (default for free/fast)
    if settings.EMBEDDING_PROVIDER == "sentence-transformers":
        from src.indexing.embeddings_sentence_transformers import get_sentence_transformers_service
        return get_sentence_transformers_service()
    
    # Otherwise use OpenAI
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    
    return _embedding_service


# Convenience functions
def embed_text(text: str) -> List[float]:
    """
    Convenience function to embed a single text
    
    Args:
        text: Text to embed
    
    Returns:
        Embedding vector
    """
    service = get_embedding_service()
    return service.embed_text(text)


def embed_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convenience function to embed chunks
    
    Args:
        chunks: List of chunk dictionaries
    
    Returns:
        List of chunk dictionaries with embeddings
    """
    service = get_embedding_service()
    return service.embed_chunks(chunks)
