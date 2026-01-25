"""
Indexing Pipeline
Complete ETL pipeline for indexing SBIR awards into vector database

Integrates:
- Chunking service (STEP 6)
- Embedding service (STEP 7)
- Vector database storage (pgvector/Qdrant)

Supports both sync and async processing for maximum performance.
"""
import time
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.core.config import settings
from src.core.logging import get_logger
from src.indexing.chunking import get_chunking_service
from src.indexing.embeddings import get_embedding_service

logger = get_logger(__name__)


class IndexingPipeline:
    """Complete indexing pipeline for SBIR awards"""
    
    def __init__(
        self,
        vector_store: Optional[str] = None,
        use_cache: bool = True,
        batch_size: int = 200,
        embedding_batch_size: int = 200,
        max_workers: int = 10,
        chunking_workers: int = 4,
        max_concurrent: int = 20
    ):
        """
        Initialize indexing pipeline
        
        Args:
            vector_store: "pgvector" or "qdrant" (defaults to settings.VECTOR_STORE)
            use_cache: Use cached embeddings (text_hash-based)
            batch_size: Process awards in batches (increased default: 200)
            embedding_batch_size: Number of chunks to embed per API call (increased default: 200)
            max_workers: Maximum number of parallel workers for sync embedding generation (default: 10)
            chunking_workers: Maximum number of parallel workers for chunking (default: 4)
            max_concurrent: Maximum concurrent async API calls (default: 20)
        """
        self.vector_store = vector_store or settings.VECTOR_STORE
        self.use_cache = use_cache
        self.batch_size = batch_size
        self.embedding_batch_size = embedding_batch_size
        self.max_workers = max_workers
        self.chunking_workers = chunking_workers
        self.max_concurrent = max_concurrent
        
        # Initialize services
        self.chunking_service = get_chunking_service()
        self.embedding_service = get_embedding_service()
        
        # Cache store for embeddings (text_hash -> embedding)
        self.cache_store: Dict[str, List[float]] = {}
        
        # Statistics tracking
        self.stats = {
            "total_awards": 0,
            "processed_awards": 0,
            "failed_awards": 0,
            "total_chunks": 0,
            "cached_chunks": 0,
            "new_chunks": 0,
            "total_tokens": 0,
            "estimated_cost": 0.0,
            "start_time": None,
            "end_time": None,
            "duration_seconds": 0.0
        }
        
        logger.info(
            "IndexingPipeline initialized",
            extra={
                "vector_store": self.vector_store,
                "use_cache": use_cache,
                "batch_size": batch_size,
                "embedding_batch_size": embedding_batch_size,
                "max_workers": max_workers
            }
        )
    
    def index_awards(
        self,
        awards: List[Dict[str, Any]],
        fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Index a list of awards into the vector database
        
        Args:
            awards: List of award dictionaries
            fields: Fields to index (default: ["title", "abstract"])
        
        Returns:
            Statistics dictionary with indexing results
        """
        if fields is None:
            fields = ["title", "abstract"]
        
        self.stats["start_time"] = datetime.utcnow()
        self.stats["total_awards"] = len(awards)
        
        logger.info(
            "Starting indexing pipeline",
            extra={
                "total_awards": len(awards),
                "vector_store": self.vector_store,
                "fields": fields
            }
        )
        
        # Process awards in batches with optimized chunking and parallel embedding
        failed_awards = []
        
        for batch_start in range(0, len(awards), self.batch_size):
            batch_end = min(batch_start + self.batch_size, len(awards))
            batch = awards[batch_start:batch_end]
            
            logger.info(
                f"Processing batch {batch_start // self.batch_size + 1}",
                extra={
                    "batch_start": batch_start,
                    "batch_end": batch_end,
                    "batch_size": len(batch)
                }
            )
            
            # Step 1: Chunk all awards in parallel (much faster!)
            award_chunks_map: Dict[str, List[Dict[str, Any]]] = {}
            all_chunks: List[Dict[str, Any]] = []
            chunk_to_award_map: Dict[int, str] = {}  # chunk index -> award_id
            
            # Parallel chunking
            def chunk_award_worker(award: Dict[str, Any]) -> tuple[str, List[Dict[str, Any]]]:
                """Worker function for parallel chunking"""
                award_id = award.get("award_id", "unknown")
                try:
                    chunks = self.chunking_service.chunk_award(award, fields=fields)
                    return award_id, chunks
                except Exception as e:
                    logger.error(
                        f"Failed to chunk award {award_id}",
                        extra={"error": str(e)}
                    )
                    return award_id, []
            
            # Process chunking in parallel
            with ThreadPoolExecutor(max_workers=self.chunking_workers) as executor:
                chunk_results = list(executor.map(chunk_award_worker, batch))
            
            # Collect results
            for award_id, chunks in chunk_results:
                if chunks:
                    award_chunks_map[award_id] = chunks
                    start_idx = len(all_chunks)
                    all_chunks.extend(chunks)
                    # Map chunk indices to award_id
                    for i in range(len(chunks)):
                        chunk_to_award_map[start_idx + i] = award_id
                    self.stats["total_chunks"] += len(chunks)
                else:
                    logger.warning(f"No chunks generated for award {award_id}")
                    failed_awards.append(award_id)
                    self.stats["failed_awards"] += 1
            
            # Step 2: Batch embed all chunks together (with parallel processing)
            if all_chunks:
                logger.info(
                    f"Embedding {len(all_chunks)} chunks in batches with parallel processing",
                    extra={
                        "total_chunks": len(all_chunks),
                        "embedding_batch_size": self.embedding_batch_size,
                        "max_workers": self.max_workers
                    }
                )
                
                chunks_with_embeddings = self._embed_chunks_parallel(all_chunks)
                
                # Step 3: Update statistics and batch store all chunks
                # Filter valid chunks with embeddings
                valid_chunks_with_embeddings = [
                    chunk for chunk in chunks_with_embeddings
                    if chunk and chunk.get("embedding")
                ]
                
                # Update statistics for all chunks
                for chunk in valid_chunks_with_embeddings:
                    text_hash = chunk.get("text_hash")
                    if text_hash and text_hash in self.cache_store:
                        self.stats["cached_chunks"] += 1
                    else:
                        self.stats["new_chunks"] += 1
                    
                    # Count tokens
                    self.stats["total_tokens"] += chunk.get("token_count", 0)
                
                # Batch store all chunks at once (much faster!)
                if valid_chunks_with_embeddings:
                    try:
                        logger.info(
                            f"Batch storing {len(valid_chunks_with_embeddings)} chunks",
                            extra={"chunk_count": len(valid_chunks_with_embeddings)}
                        )
                        self._store_chunks(valid_chunks_with_embeddings)
                        
                        # Mark all awards in batch as processed
                        for award in batch:
                            award_id = award.get("award_id", "unknown")
                            if award_id in award_chunks_map:
                                self.stats["processed_awards"] += 1
                            else:
                                # Award was chunked but no embeddings generated
                                logger.warning(
                                    f"No embeddings generated for award {award_id}"
                                )
                                failed_awards.append(award_id)
                                self.stats["failed_awards"] += 1
                    except Exception as e:
                        logger.error(
                            f"Failed to batch store chunks",
                            extra={"error": str(e), "chunk_count": len(valid_chunks_with_embeddings)}
                        )
                        # Mark all awards in batch as failed
                        for award in batch:
                            award_id = award.get("award_id", "unknown")
                            failed_awards.append(award_id)
                            self.stats["failed_awards"] += 1
            
            # Log progress
            progress = (self.stats["processed_awards"] / self.stats["total_awards"]) * 100
            logger.info(
                f"Progress: {self.stats['processed_awards']}/{self.stats['total_awards']} "
                f"({progress:.1f}%)"
            )
        
        # Finalize statistics
        self.stats["end_time"] = datetime.utcnow()
        duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()
        self.stats["duration_seconds"] = duration
        
        # Estimate cost
        self.stats["estimated_cost"] = self.embedding_service.estimate_cost(
            self.stats["total_tokens"]
        )
        
        logger.info(
            "Indexing pipeline completed",
            extra={
                "total_awards": self.stats["total_awards"],
                "processed": self.stats["processed_awards"],
                "failed": self.stats["failed_awards"],
                "total_chunks": self.stats["total_chunks"],
                "cached_chunks": self.stats["cached_chunks"],
                "new_chunks": self.stats["new_chunks"],
                "estimated_cost": self.stats["estimated_cost"],
                "duration_seconds": duration
            }
        )
        
        return {
            **self.stats,
            "failed_award_ids": failed_awards,
            "success_rate": (
                self.stats["processed_awards"] / self.stats["total_awards"] * 100
                if self.stats["total_awards"] > 0 else 0
            )
        }
    
    async def index_awards_async(
        self,
        awards: List[Dict[str, Any]],
        fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Index a list of awards into the vector database (ASYNC - MUCH FASTER!)
        
        Uses async/await for parallel processing similar to the Qdrant ingestion script.
        This can process 100K+ awards in seconds/minutes instead of hours.
        
        Args:
            awards: List of award dictionaries
            fields: Fields to index (default: ["title", "abstract"])
        
        Returns:
            Statistics dictionary with indexing results
        """
        if fields is None:
            fields = ["title", "abstract"]
        
        # Validate and limit max_concurrent to prevent system overload
        if self.max_concurrent > 50:
            logger.warning(
                f"max_concurrent ({self.max_concurrent}) is very high. "
                "This may cause rate limiting or system overload. Consider reducing to 20-30."
            )
        
        self.stats["start_time"] = datetime.utcnow()
        self.stats["total_awards"] = len(awards)
        
        logger.info(
            "Starting async indexing pipeline",
            extra={
                "total_awards": len(awards),
                "vector_store": self.vector_store,
                "fields": fields,
                "max_concurrent": self.max_concurrent,
                "batch_size": self.batch_size
            }
        )
        
        # Process awards in batches with async parallel processing
        failed_awards = []
        total_batches = (len(awards) + self.batch_size - 1) // self.batch_size
        logger.info(f"Will process {total_batches} batch(es) of awards")
        
        for batch_start in range(0, len(awards), self.batch_size):
            batch_end = min(batch_start + self.batch_size, len(awards))
            batch = awards[batch_start:batch_end]
            
            logger.info(
                f"Processing batch {batch_start // self.batch_size + 1}",
                extra={
                    "batch_start": batch_start,
                    "batch_end": batch_end,
                    "batch_size": len(batch)
                }
            )
            
            # Step 1: Chunk all awards in PARALLEL (optimized - 8+ awards simultaneously)
            logger.info(f"Chunking {len(batch)} awards in parallel...")
            award_chunks_map: Dict[str, List[Dict[str, Any]]] = {}
            all_chunks: List[Dict[str, Any]] = []
            chunk_to_award_map: Dict[int, str] = {}  # chunk index -> award_id
            
            # Parallel chunking using asyncio (8+ awards simultaneously)
            async def chunk_single_award(award: Dict[str, Any]) -> tuple[str, List[Dict[str, Any]]]:
                """Chunk a single award (async wrapper for parallel execution)"""
                award_id = award.get("award_id", "unknown")
                try:
                    # Run chunking in thread pool (CPU-bound operation)
                    loop = asyncio.get_event_loop()
                    chunks = await loop.run_in_executor(
                        None,  # Default ThreadPoolExecutor
                        self.chunking_service.chunk_award,
                        award,
                        fields
                    )
                    return award_id, chunks
                except Exception as e:
                    logger.error(
                        f"Failed to chunk award {award_id}",
                        extra={"error": str(e)}
                    )
                    return award_id, []
            
            # Process all awards in parallel (8+ at once)
            chunk_tasks = [chunk_single_award(award) for award in batch]
            chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
            
            # Filter out exceptions and collect valid results
            valid_chunk_results = []
            for result in chunk_results:
                if isinstance(result, Exception):
                    logger.error(f"Chunking task failed: {result}")
                else:
                    valid_chunk_results.append(result)
            
            logger.info(f"Chunking complete: {len(valid_chunk_results)} awards processed (parallel)")
            
            # Collect results
            logger.info("Collecting chunking results...")
            for award_id, chunks in chunk_results:
                if chunks:
                    award_chunks_map[award_id] = chunks
                    start_idx = len(all_chunks)
                    all_chunks.extend(chunks)
                    # Map chunk indices to award_id
                    for i in range(len(chunks)):
                        chunk_to_award_map[start_idx + i] = award_id
                    self.stats["total_chunks"] += len(chunks)
                else:
                    logger.warning(f"No chunks generated for award {award_id}")
                    failed_awards.append(award_id)
                    self.stats["failed_awards"] += 1
            
            logger.info(f"Total chunks created: {len(all_chunks)} from {len(batch)} awards")
            
            # Step 2: Async embed all chunks together (with parallel processing)
            if all_chunks:
                logger.info(
                    f"Embedding {len(all_chunks)} chunks async with {self.max_concurrent} concurrent calls",
                    extra={
                        "total_chunks": len(all_chunks),
                        "embedding_batch_size": self.embedding_batch_size,
                        "max_concurrent": self.max_concurrent
                    }
                )
                
                # Use async embedding service
                chunks_with_embeddings = await self.embedding_service.embed_chunks_async(
                    chunks=all_chunks,
                    use_cache=self.use_cache,
                    cache_store=self.cache_store,
                    max_concurrent=self.max_concurrent,
                    batch_size=self.embedding_batch_size
                )
                
                # Step 3: Update statistics and batch store all chunks
                # Filter valid chunks with embeddings
                valid_chunks_with_embeddings = [
                    chunk for chunk in chunks_with_embeddings
                    if chunk and chunk.get("embedding")
                ]
                
                # Update statistics for all chunks
                for chunk in valid_chunks_with_embeddings:
                    text_hash = chunk.get("text_hash")
                    if text_hash and text_hash in self.cache_store:
                        self.stats["cached_chunks"] += 1
                    else:
                        self.stats["new_chunks"] += 1
                    
                    # Count tokens
                    self.stats["total_tokens"] += chunk.get("token_count", 0)
                
                # Batch store all chunks at once (much faster!)
                # Run in executor to avoid blocking the event loop
                if valid_chunks_with_embeddings:
                    try:
                        logger.info(
                            f"Batch storing {len(valid_chunks_with_embeddings)} chunks",
                            extra={"chunk_count": len(valid_chunks_with_embeddings)}
                        )
                        # Run blocking database operation in executor to avoid blocking event loop
                        try:
                            loop = asyncio.get_running_loop()
                        except RuntimeError:
                            loop = asyncio.get_event_loop()
                        
                        await loop.run_in_executor(
                            None,  # Use default ThreadPoolExecutor
                            self._store_chunks,
                            valid_chunks_with_embeddings
                        )
                        
                        # Mark all awards in batch as processed
                        for award in batch:
                            award_id = award.get("award_id", "unknown")
                            if award_id in award_chunks_map:
                                self.stats["processed_awards"] += 1
                            else:
                                # Award was chunked but no embeddings generated
                                logger.warning(
                                    f"No embeddings generated for award {award_id}"
                                )
                                failed_awards.append(award_id)
                                self.stats["failed_awards"] += 1
                    except Exception as e:
                        logger.error(
                            f"Failed to batch store chunks",
                            extra={"error": str(e), "chunk_count": len(valid_chunks_with_embeddings)}
                        )
                        # Mark all awards in batch as failed
                        for award in batch:
                            award_id = award.get("award_id", "unknown")
                            failed_awards.append(award_id)
                            self.stats["failed_awards"] += 1
            
            # Log progress
            progress = (self.stats["processed_awards"] / self.stats["total_awards"]) * 100
            logger.info(
                f"Progress: {self.stats['processed_awards']}/{self.stats['total_awards']} "
                f"({progress:.1f}%)"
            )
        
        # Finalize statistics
        self.stats["end_time"] = datetime.utcnow()
        duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()
        self.stats["duration_seconds"] = duration
        
        # Estimate cost
        self.stats["estimated_cost"] = self.embedding_service.estimate_cost(
            self.stats["total_tokens"]
        )
        
        logger.info(
            "Async indexing pipeline completed",
            extra={
                "total_awards": self.stats["total_awards"],
                "processed": self.stats["processed_awards"],
                "failed": self.stats["failed_awards"],
                "total_chunks": self.stats["total_chunks"],
                "cached_chunks": self.stats["cached_chunks"],
                "new_chunks": self.stats["new_chunks"],
                "estimated_cost": self.stats["estimated_cost"],
                "duration_seconds": duration
            }
        )
        
        return {
            **self.stats,
            "failed_award_ids": failed_awards,
            "success_rate": (
                self.stats["processed_awards"] / self.stats["total_awards"] * 100
                if self.stats["total_awards"] > 0 else 0
            )
        }
    
    def _embed_chunks_parallel(
        self,
        chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Embed chunks in batches with parallel processing
        
        Args:
            chunks: List of chunk dictionaries
            
        Returns:
            List of chunk dictionaries with embeddings
        """
        if not chunks:
            return []
        
        # Separate cached and uncached chunks
        cached_chunks = []
        uncached_chunks = []
        uncached_indices = []
        
        for idx, chunk in enumerate(chunks):
            text_hash = chunk.get("text_hash")
            
            if self.use_cache and text_hash and text_hash in self.cache_store:
                # Use cached embedding
                chunk["embedding"] = self.cache_store[text_hash]
                cached_chunks.append((idx, chunk))
            else:
                # Need to generate embedding
                uncached_chunks.append(chunk)
                uncached_indices.append(idx)
        
        logger.info(
            f"Preparing to embed {len(uncached_chunks)} chunks "
            f"({len(cached_chunks)} cached)",
            extra={
                "total": len(chunks),
                "cached": len(cached_chunks),
                "uncached": len(uncached_chunks)
            }
        )
        
        # Generate embeddings for uncached chunks in parallel batches
        if uncached_chunks:
            # Split into batches for parallel processing
            batch_texts = []
            batch_chunks = []
            
            for i in range(0, len(uncached_chunks), self.embedding_batch_size):
                batch = uncached_chunks[i:i + self.embedding_batch_size]
                batch_texts.append([chunk["chunk_text"] for chunk in batch])
                batch_chunks.append(batch)
            
            # Process batches in parallel
            all_embeddings = []
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all batches
                future_to_batch = {
                    executor.submit(
                        self.embedding_service.embed_batch,
                        texts
                    ): batch_idx
                    for batch_idx, texts in enumerate(batch_texts)
                }
                
                # Collect results as they complete
                batch_results = {}
                for future in as_completed(future_to_batch):
                    batch_idx = future_to_batch[future]
                    try:
                        embeddings = future.result()
                        batch_results[batch_idx] = embeddings
                        logger.info(
                            f"Completed embedding batch {batch_idx + 1}/{len(batch_texts)}",
                            extra={"batch_size": len(embeddings)}
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to embed batch {batch_idx}",
                            extra={"error": str(e)}
                        )
                        # Add None embeddings for failed batch
                        batch_results[batch_idx] = [None] * len(batch_texts[batch_idx])
                
                # Combine results in order
                for batch_idx in sorted(batch_results.keys()):
                    all_embeddings.extend(batch_results[batch_idx])
            
            # Add embeddings to chunks and update cache
            for chunk, embedding in zip(uncached_chunks, all_embeddings):
                if embedding:
                    chunk["embedding"] = embedding
                    # Update cache
                    text_hash = chunk.get("text_hash")
                    if text_hash and self.use_cache:
                        self.cache_store[text_hash] = embedding
        
        # Combine cached and newly embedded chunks in original order
        result = [None] * len(chunks)
        
        # Place cached chunks
        for idx, chunk in cached_chunks:
            result[idx] = chunk
        
        # Place newly embedded chunks
        for idx, chunk in zip(uncached_indices, uncached_chunks):
            result[idx] = chunk
        
        return result
    
    def _store_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """
        Store chunks in vector database
        
        Args:
            chunks: List of chunk dictionaries with embeddings
        """
        if not chunks:
            return
        
        # Filter out chunks without embeddings
        valid_chunks = [c for c in chunks if c and c.get("embedding")]
        
        if not valid_chunks:
            logger.warning("No valid chunks with embeddings to store")
            return
        
        if self.vector_store == "pgvector":
            self._store_pgvector(valid_chunks)
        elif self.vector_store == "qdrant":
            self._store_qdrant(valid_chunks)
        else:
            logger.error(f"Unknown vector store: {self.vector_store}")
            raise ValueError(f"Unsupported vector store: {self.vector_store}")
    
    def _store_pgvector(self, chunks: List[Dict[str, Any]]) -> None:
        """
        Store chunks in pgvector (Supabase)
        
        Args:
            chunks: List of chunk dictionaries with embeddings
        """
        try:
            from src.database.pgvector import get_pgvector_manager
            
            manager = get_pgvector_manager()
            
            # Prepare vectors for insertion
            vectors = []
            for chunk in chunks:
                vectors.append({
                    "award_id": chunk.get("award_id", ""),
                    "chunk_index": chunk.get("chunk_index", 0),
                    "chunk_text": chunk.get("chunk_text", ""),
                    "embedding": chunk.get("embedding", []),
                    "field_name": chunk.get("field_name", ""),
                    "text_hash": chunk.get("text_hash", "")
                })
            
            # Insert vectors (uses configured table name from settings)
            manager.insert_vectors(vectors, table_name=settings.AWARD_CHUNKS_TABLE_NAME)
            
            logger.debug(f"Stored {len(vectors)} chunks in pgvector table: {settings.AWARD_CHUNKS_TABLE_NAME}")
            
        except ImportError:
            logger.warning("pgvector not available, skipping storage")
        except Exception as e:
            logger.error(f"Failed to store in pgvector: {e}")
            raise
    
    def _store_qdrant(self, chunks: List[Dict[str, Any]]) -> None:
        """
        Store chunks in Qdrant
        
        Args:
            chunks: List of chunk dictionaries with embeddings
        """
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.models import PointStruct, Distance, VectorParams
            
            # Initialize Qdrant client
            qdrant_url = settings.QDRANT_URL
            qdrant_api_key = settings.QDRANT_API_KEY or None
            
            if qdrant_api_key:
                client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
            else:
                client = QdrantClient(url=qdrant_url)
            
            collection_name = "sbir_awards"
            
            # Ensure collection exists
            try:
                client.get_collection(collection_name)
            except Exception:
                # Create collection if it doesn't exist
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=settings.EMBEDDING_DIMENSION,
                        distance=Distance.COSINE
                    )
                )
            
            # Prepare points
            points = []
            for chunk in chunks:
                award_id = chunk.get("award_id", "")
                chunk_index = chunk.get("chunk_index", 0)
                
                # Generate unique ID
                import hashlib
                point_id = hashlib.md5(
                    f"{award_id}_{chunk_index}".encode()
                ).hexdigest()
                
                point = PointStruct(
                    id=point_id,
                    vector=chunk.get("embedding", []),
                    payload={
                        "award_id": award_id,
                        "agency": chunk.get("agency", ""),
                        "chunk_index": chunk_index,
                        "chunk_text": chunk.get("chunk_text", ""),
                        "field_name": chunk.get("field_name", ""),
                        "text_hash": chunk.get("text_hash", ""),
                        "model": settings.EMBEDDING_MODEL
                    }
                )
                points.append(point)
            
            # Upsert points
            client.upsert(
                collection_name=collection_name,
                points=points
            )
            
            logger.debug(f"Stored {len(points)} chunks in Qdrant")
            
        except ImportError:
            logger.warning("Qdrant client not available, skipping storage")
        except Exception as e:
            logger.error(f"Failed to store in Qdrant: {e}")
            raise
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get current indexing statistics"""
        return self.stats.copy()
    
    def reset_statistics(self) -> None:
        """Reset statistics"""
        self.stats = {
            "total_awards": 0,
            "processed_awards": 0,
            "failed_awards": 0,
            "total_chunks": 0,
            "cached_chunks": 0,
            "new_chunks": 0,
            "total_tokens": 0,
            "estimated_cost": 0.0,
            "start_time": None,
            "end_time": None,
            "duration_seconds": 0.0
        }


# Singleton instance
_indexing_pipeline: Optional[IndexingPipeline] = None


def get_indexing_pipeline() -> IndexingPipeline:
    """
    Get singleton indexing pipeline instance
    
    Returns:
        IndexingPipeline: Configured pipeline instance
    """
    global _indexing_pipeline
    
    if _indexing_pipeline is None:
        _indexing_pipeline = IndexingPipeline()
    
    return _indexing_pipeline


# Convenience function
def index_awards(
    awards: List[Dict[str, Any]],
    vector_store: Optional[str] = None,
    use_cache: bool = True,
    batch_size: int = 100
) -> Dict[str, Any]:
    """
    Convenience function to index awards
    
    Args:
        awards: List of award dictionaries
        vector_store: "pgvector" or "qdrant"
        use_cache: Use cached embeddings
        batch_size: Process awards in batches
    
    Returns:
        Statistics dictionary
    """
    pipeline = IndexingPipeline(
        vector_store=vector_store,
        use_cache=use_cache,
        batch_size=batch_size
    )
    return pipeline.index_awards(awards)
