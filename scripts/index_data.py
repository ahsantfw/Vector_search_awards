"""
Index Data Pipeline
Runs the complete indexing pipeline to chunk, embed, and store awards

Supports both sync and async processing. Async is MUCH faster for large datasets.
"""
import sys
import asyncio
from pathlib import Path
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings
from src.core.logging import get_logger
from src.database.supabase import get_supabase_client
from src.database.pgvector import get_pgvector_manager
from src.indexing.pipeline import IndexingPipeline

logger = get_logger(__name__)


def get_awards_from_supabase(limit: int = None):
    """
    Fetch awards from Supabase with pagination to get ALL awards
    
    Args:
        limit: Optional limit on number of awards to fetch (for testing)
    
    Returns:
        List of award dictionaries
    """
    try:
        supabase_client_wrapper = get_supabase_client()
        supabase_client = supabase_client_wrapper.get_client()
        
        # Use configured table name
        awards_table = settings.AWARDS_TABLE_NAME
        
        awards = []
        page_size = 1000  # Supabase default max per page
        offset = 0
        
        while True:
            # Build query with pagination
            query = supabase_client.table(awards_table).select("*")
            
            # Apply limit if specified (for testing)
            if limit and len(awards) >= limit:
                break
            
            # Fetch page
            query = query.range(offset, offset + page_size - 1)
            response = query.execute()
            
            if not response.data:
                break  # No more data
            
            # Process this page
            for row in response.data:
                awards.append({
                    'award_id': row.get('award_id', ''),
                    'title': row.get('title', ''),
                    'abstract': row.get('public_abstract', '') or row.get('abstract', ''),  # Use public_abstract from new schema
                    'agency': row.get('agency', ''),
                    # Include all other schema columns
                    'award_number': row.get('award_number'),
                    'award_status': row.get('award_status'),
                    'institution': row.get('institution'),
                    'uei': row.get('uei'),
                    'duns': row.get('duns'),
                    'most_recent_award_date': row.get('most_recent_award_date'),
                    'num_support_periods': row.get('num_support_periods'),
                    'pm': row.get('pm'),
                    'current_budget_period': row.get('current_budget_period'),
                    'current_project_period': row.get('current_project_period'),
                    'pi': row.get('pi'),
                    'supplement_budget_period': row.get('supplement_budget_period'),
                    'public_abstract_url': row.get('public_abstract_url'),
                })
            
            # Check if we got fewer rows than page_size (last page)
            if len(response.data) < page_size:
                break
            
            # Move to next page
            offset += page_size
            
            # Apply limit if specified
            if limit and len(awards) >= limit:
                awards = awards[:limit]
                break
        
        logger.info(f"Fetched {len(awards)} awards from Supabase (with pagination)")
        return awards
        
    except Exception as e:
        logger.error(f"Failed to fetch awards from Supabase: {e}")
        raise


async def main_async(
    limit: int = None,
    fresh_index: bool = False
):
    """Main async indexing function - MUCH FASTER for large datasets"""
    
    # Check configuration
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        logger.error("Supabase credentials not configured")
        sys.exit(1)

    # Check embedding provider configuration
    if settings.EMBEDDING_PROVIDER == "openai" and not settings.OPENAI_API_KEY:
        logger.error("OpenAI API key not configured (required when EMBEDDING_PROVIDER=openai)")
        sys.exit(1)
    elif settings.EMBEDDING_PROVIDER == "sentence-transformers":
        # Check if sentence-transformers is available
        try:
            import sentence_transformers
        except ImportError:
            logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
            sys.exit(1)

    if settings.VECTOR_STORE == "pgvector" and not settings.DATABASE_URL:
        logger.error("DATABASE_URL not configured for pgvector")
        sys.exit(1)
    
    # Get awards from Supabase
    logger.info("Fetching awards from Supabase...")
    awards = get_awards_from_supabase(limit=limit)
    
    if not awards:
        logger.error("No awards found in Supabase. Please load data first.")
        sys.exit(1)
    
    logger.info(f"Found {len(awards)} awards to index")
    
    # Use config settings directly
    batch_size = settings.INDEXING_BATCH_SIZE
    max_concurrent = settings.INDEXING_MAX_CONCURRENT
    embedding_batch_size = settings.INDEXING_EMBEDDING_BATCH_SIZE
    chunking_workers = settings.INDEXING_CHUNKING_WORKERS
    
    # Initialize pipeline with async settings
    logger.info("Initializing async indexing pipeline...")
    if fresh_index:
        logger.info("🔄 FRESH INDEX MODE: Disabling cache, forcing complete re-embedding")
        use_cache = False
    else:
        use_cache = True

    # Display comprehensive configuration settings
    logger.info(f"   Mode: {'Fresh Index (No Cache)' if fresh_index else 'Incremental (With Cache)'}")
    logger.info(f"   Model: {settings.EMBEDDING_MODEL} ({settings.EMBEDDING_PROVIDER}) - {settings.EMBEDDING_DIMENSION} dimensions")

    # Indexing settings
    logger.info(f"   Batch size: {batch_size} awards")
    logger.info(f"   Max concurrent: {max_concurrent} calls")
    logger.info(f"   Embedding batch size: {embedding_batch_size} chunks")
    logger.info(f"   Chunking workers: {chunking_workers}")

    # Chunking settings
    logger.info(f"   Chunk size: {settings.CHUNK_SIZE} tokens")
    logger.info(f"   Chunk overlap: {settings.CHUNK_OVERLAP} tokens")

    # Storage settings
    logger.info(f"   Vector store: {settings.VECTOR_STORE}")
    logger.info(f"   Awards table: {settings.AWARDS_TABLE_NAME}")
    logger.info(f"   Chunks table: {settings.AWARD_CHUNKS_TABLE_NAME}")

    # Database
    logger.info(f"   Database: {settings.DATABASE_URL.split('@')[-1] if settings.DATABASE_URL else 'Not configured'}")

    pipeline = IndexingPipeline(
        vector_store=settings.VECTOR_STORE,
        use_cache=use_cache,
        batch_size=batch_size,
        embedding_batch_size=embedding_batch_size,
        max_concurrent=max_concurrent,
        chunking_workers=chunking_workers
    )
    
    # Run async indexing
    logger.info("Starting async indexing pipeline...")
    try:
        stats = await pipeline.index_awards_async(awards)
        
        logger.info("✅ Async indexing complete!")
        logger.info(f"   Processed: {stats['processed_awards']} awards")
        logger.info(f"   Chunks created: {stats['total_chunks']}")
        logger.info(f"   New chunks: {stats['new_chunks']}")
        logger.info(f"   Cached chunks: {stats['cached_chunks']}")
        logger.info(f"   Duration: {stats.get('duration_seconds', 0):.1f} seconds")
        logger.info(f"   Cost estimate: ${stats.get('estimated_cost', 0):.2f}")
        
    except Exception as e:
        logger.error(f"Indexing failed: {e}", exc_info=True)
        sys.exit(1)


def main():
    """Main indexing function"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Index SBIR awards data with SciBERT embeddings (supports both sync and async)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fresh index with SciBERT (recommended after model change):
  python index_data.py --async --fresh --max-concurrent 5

  # Incremental indexing (use cache):
  python index_data.py --async --limit 1000 --max-concurrent 10

  # Sync processing (for small datasets):
  python index_data.py --limit 100

Performance:
  Async mode can process 100K+ awards in minutes instead of hours!
  Use --fresh for complete re-indexing when changing embedding models
  SciBERT provides excellent results for scientific/technical content
        """
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of awards to index (for testing)"
    )
    parser.add_argument(
        "--async",
        action="store_true",
        dest="use_async",
        help="Use async processing (MUCH FASTER - recommended for large datasets)"
    )
    parser.add_argument(
        "--fresh",
        "--from-scratch",
        action="store_true",
        help="Fresh index from scratch - disable cache and re-embed everything (for model changes)"
    )
    
    args = parser.parse_args()
    
    if args.use_async:
        # Use async processing
        asyncio.run(main_async(
            limit=args.limit,
            fresh_index=getattr(args, 'fresh', False)
        ))
    else:
        # Use sync processing (legacy)
        logger.warning("Using sync processing. For better performance, use --async flag!")
        
        # Check configuration
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            logger.error("Supabase credentials not configured")
            sys.exit(1)

        # Check embedding provider configuration
        if settings.EMBEDDING_PROVIDER == "openai" and not settings.OPENAI_API_KEY:
            logger.error("OpenAI API key not configured (required when EMBEDDING_PROVIDER=openai)")
            sys.exit(1)
        elif settings.EMBEDDING_PROVIDER == "sentence-transformers":
            # Check if sentence-transformers is available
            try:
                import sentence_transformers
            except ImportError:
                logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
                sys.exit(1)

        if settings.VECTOR_STORE == "pgvector" and not settings.DATABASE_URL:
            logger.error("DATABASE_URL not configured for pgvector")
            sys.exit(1)
        
        # Get awards from Supabase
        logger.info("Fetching awards from Supabase...")
        awards = get_awards_from_supabase(limit=args.limit)
        
        if not awards:
            logger.error("No awards found in Supabase. Please load data first.")
            sys.exit(1)
        
        logger.info(f"Found {len(awards)} awards to index")
        
        # Use config settings directly
        batch_size = settings.INDEXING_BATCH_SIZE
        chunking_workers = settings.INDEXING_CHUNKING_WORKERS
        fresh_index = getattr(args, 'fresh', False)

        # Initialize pipeline
        logger.info("Initializing indexing pipeline...")
        if fresh_index:
            logger.info("🔄 FRESH INDEX MODE: Disabling cache, forcing complete re-embedding")
            use_cache = False
        else:
            use_cache = True

        # Display comprehensive configuration settings
        logger.info(f"   Mode: {'Fresh Index (No Cache)' if fresh_index else 'Incremental (With Cache)'}")
        logger.info(f"   Model: {settings.EMBEDDING_MODEL} ({settings.EMBEDDING_PROVIDER}) - {settings.EMBEDDING_DIMENSION} dimensions")
        logger.info(f"   Batch size: {batch_size} awards")
        logger.info(f"   Chunking workers: {chunking_workers}")
        logger.info(f"   Chunk size: {settings.CHUNK_SIZE} tokens")
        logger.info(f"   Chunk overlap: {settings.CHUNK_OVERLAP} tokens")
        logger.info(f"   Vector store: {settings.VECTOR_STORE}")
        logger.info(f"   Awards table: {settings.AWARDS_TABLE_NAME}")
        logger.info(f"   Chunks table: {settings.AWARD_CHUNKS_TABLE_NAME}")
        logger.info(f"   Database: {settings.DATABASE_URL.split('@')[-1] if settings.DATABASE_URL else 'Not configured'}")

        pipeline = IndexingPipeline(
            vector_store=settings.VECTOR_STORE,
            use_cache=use_cache,
            batch_size=batch_size,
            chunking_workers=chunking_workers
        )
        
        # Run indexing
        logger.info("Starting indexing pipeline...")
        try:
            stats = pipeline.index_awards(awards)
            
            logger.info("✅ Indexing complete!")
            logger.info(f"   Processed: {stats['processed_awards']} awards")
            logger.info(f"   Chunks created: {stats['total_chunks']}")
            logger.info(f"   New chunks: {stats['new_chunks']}")
            logger.info(f"   Cached chunks: {stats['cached_chunks']}")
            logger.info(f"   Cost estimate: ${stats.get('estimated_cost', 0):.2f}")
            
        except Exception as e:
            logger.error(f"Indexing failed: {e}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()

