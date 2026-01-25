"""
Test OpenAI Embeddings with 100 Awards
Quick test script to validate OpenAI embedding performance
"""
import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings
from src.core.logging import get_logger
from src.database.supabase import get_supabase_client
from src.indexing.pipeline import IndexingPipeline

logger = get_logger(__name__)


async def test_openai_embeddings(num_awards: int = 100):
    """
    Test OpenAI embeddings with limited number of awards
    
    Args:
        num_awards: Number of awards to index (default: 100)
    """
    # Verify OpenAI configuration
    if settings.EMBEDDING_PROVIDER != "openai":
        logger.error("EMBEDDING_PROVIDER must be 'openai' for this test")
        logger.info("Please set in .env: EMBEDDING_PROVIDER=openai")
        return False
    
    if not settings.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not configured")
        logger.info("Please set OPENAI_API_KEY in .env")
        return False
    
    if settings.EMBEDDING_DIMENSION != 3072:
        logger.warning(f"EMBEDDING_DIMENSION is {settings.EMBEDDING_DIMENSION}, expected 3072 for OpenAI")
        logger.info("Please set in .env: EMBEDDING_DIMENSION=3072")
    
    logger.info("=" * 80)
    logger.info("OPENAI EMBEDDINGS TEST - 100 Awards")
    logger.info("=" * 80)
    logger.info(f"Configuration:")
    logger.info(f"  Provider: {settings.EMBEDDING_PROVIDER}")
    logger.info(f"  Model: {settings.EMBEDDING_MODEL}")
    logger.info(f"  Dimension: {settings.EMBEDDING_DIMENSION}")
    logger.info(f"  Awards to index: {num_awards}")
    logger.info(f"  Awards table: {settings.AWARDS_TABLE_NAME}")
    logger.info(f"  Chunks table: {settings.AWARD_CHUNKS_TABLE_NAME}")
    logger.info("")
    
    # Fetch awards from Supabase
    logger.info(f"Fetching {num_awards} awards from Supabase...")
    supabase = get_supabase_client()
    supabase_raw = supabase.get_client()
    awards_table = settings.AWARDS_TABLE_NAME
    
    try:
        response = supabase_raw.table(awards_table).select("*").limit(num_awards).execute()
        awards = response.data
        logger.info(f"✅ Fetched {len(awards)} awards")
    except Exception as e:
        logger.error(f"Failed to fetch awards: {e}")
        return False
    
    if not awards:
        logger.error("No awards found in database")
        return False
    
    # Initialize pipeline with fresh indexing (no cache)
    logger.info("Initializing OpenAI embedding pipeline...")
    pipeline = IndexingPipeline(
        vector_store=settings.VECTOR_STORE,
        use_cache=False,  # Fresh embeddings for testing
        batch_size=10,  # Smaller batches for testing
        embedding_batch_size=10,  # Smaller embedding batches
        max_concurrent=1,  # Conservative for testing
        chunking_workers=2
    )
    
    # Run async indexing
    logger.info("Starting indexing with OpenAI embeddings...")
    try:
        stats = await pipeline.index_awards_async(awards)
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ INDEXING COMPLETE!")
        logger.info("=" * 80)
        logger.info(f"  Processed: {stats['processed_awards']} awards")
        logger.info(f"  Chunks created: {stats['total_chunks']}")
        logger.info(f"  New chunks: {stats['new_chunks']}")
        logger.info(f"  Skipped (cached): {stats.get('skipped_chunks', 0)}")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Run: uv run python scripts/test_complex_queries.py")
        logger.info("  2. Run: uv run python scripts/validation_benchmark.py --num-awards 20")
        logger.info("  3. Check Recall@5 improvement!")
        
        return True
        
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test OpenAI embeddings with limited awards"
    )
    parser.add_argument(
        "--num-awards",
        type=int,
        default=100,
        help="Number of awards to index (default: 100)"
    )
    
    args = parser.parse_args()
    
    # Run async test
    success = asyncio.run(test_openai_embeddings(num_awards=args.num_awards))
    
    if success:
        logger.info("")
        logger.info("✅ Test completed successfully!")
        sys.exit(0)
    else:
        logger.error("")
        logger.error("❌ Test failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()

