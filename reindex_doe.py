#!/usr/bin/env python3
"""
DOE-Optimized Re-indexing Script
Re-indexes SBIR data with improved chunking and scientific embeddings
"""
import sys
import asyncio
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.config import settings
from src.core.logging import get_logger
from src.database.supabase import get_supabase_client
from src.database.pgvector import get_pgvector_manager
from src.indexing.pipeline import IndexingPipeline

logger = get_logger(__name__)

def fetch_sample_awards(limit: int = 100) -> list:
    """Fetch a sample of awards for testing"""
    try:
        supabase_client_wrapper = get_supabase_client()
        supabase_client = supabase_client_wrapper.get_client()

        awards_table = settings.AWARDS_TABLE_NAME

        response = supabase_client.table(awards_table).select("*").limit(limit).execute()

        awards = []
        for row in response.data:
            awards.append({
                'award_id': row.get('award_id', ''),
                'title': row.get('title', ''),
                'abstract': row.get('public_abstract', '') or row.get('abstract', ''),
                'agency': row.get('agency', ''),
            })

        logger.info(f"Fetched {len(awards)} sample awards for testing")
        return awards

    except Exception as e:
        logger.error(f"Failed to fetch sample awards: {e}")
        return []

async def reindex_sample_async(sample_size: int = 50):
    """Re-index a sample with async processing"""

    print("🔄 DOE-Optimized Re-indexing (Async)")
    print("=" * 50)
    print(f"Embedding Model: {settings.EMBEDDING_MODEL}")
    print(f"Embedding Provider: {settings.EMBEDDING_PROVIDER}")
    print(f"Chunk Size: {settings.CHUNK_SIZE} tokens")
    print(f"Sample Size: {sample_size} awards")
    print()

    # Fetch sample data
    print("Fetching sample awards...")
    awards = fetch_sample_awards(sample_size)
    if not awards:
        print("❌ Failed to fetch awards")
        return False

    # Initialize pipeline with optimized settings
    print("Initializing indexing pipeline...")
    pipeline = IndexingPipeline(
        vector_store=settings.VECTOR_STORE,
        use_cache=False,  # Force re-embedding with new model
        batch_size=20,    # Smaller batches for testing
        embedding_batch_size=10,  # Smaller for API limits
        max_concurrent=5,  # Conservative concurrent calls
        chunking_workers=2
    )

    # Clear existing chunks for these awards (optional - for clean re-indexing)
    try:
        print("Clearing existing chunks for sample awards...")
        pgvector_manager = get_pgvector_manager()

        award_ids = [a['award_id'] for a in awards if a['award_id']]
        if award_ids:
            # Note: This would require a delete method in pgvector manager
            # For now, we'll just overwrite
            pass

    except Exception as e:
        logger.warning(f"Could not clear existing chunks: {e}")

    # Run async indexing
    print("Starting async re-indexing...")
    start_time = time.time()

    try:
        stats = await pipeline.index_awards_async(awards)

        elapsed = time.time() - start_time

        print("✅ Re-indexing completed!")
        print(f"   Processed: {stats['processed_awards']} awards")
        print(f"   Total chunks: {stats['total_chunks']}")
        print(f"   New embeddings: {stats['new_chunks']}")
        print(".2f"        print(".2f"        print(f"   Success rate: {stats.get('success_rate', 0):.1f}%")

        return True

    except Exception as e:
        print(f"❌ Re-indexing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main re-indexing function"""
    import argparse

    parser = argparse.ArgumentParser(
        description="DOE-optimized re-indexing with scientific embeddings"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=50,
        help="Number of awards to re-index for testing"
    )
    parser.add_argument(
        "--full-reindex",
        action="store_true",
        help="Re-index all awards (WARNING: expensive operation)"
    )

    args = parser.parse_args()

    if args.full_reindex:
        print("⚠️  FULL RE-INDEX REQUESTED")
        print("This will re-embed ALL awards with new model - very expensive!")
        confirm = input("Continue? (yes/no): ")
        if confirm.lower() != "yes":
            print("Cancelled.")
            return

        # Would implement full re-indexing here
        print("Full re-indexing not implemented yet - use sample testing first")
        return

    # Run sample re-indexing
    success = asyncio.run(reindex_sample_async(args.sample_size))

    if success:
        print("\n🎯 Next Steps:")
        print("1. Run DOE test suite: python doe_test_suite.py")
        print("2. Validate semantic precision")
        print("3. If successful, proceed with full re-indexing")
    else:
        print("\n❌ Re-indexing failed - check configuration and try again")

if __name__ == "__main__":
    main()
