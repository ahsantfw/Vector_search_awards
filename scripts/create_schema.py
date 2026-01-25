"""
Create Database Schema (First Time Setup)
Creates complete schema with all CSV columns and configurable table names
"""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def create_schema_from_template(
    sql_template_path: str,
    awards_table_name: str = None,
    chunks_table_name: str = None,
    embedding_dimension: int = None
) -> str:
    """
    Read SQL template and replace table names and dimensions with configured values
    
    Args:
        sql_template_path: Path to SQL template file
        awards_table_name: Name for awards table (defaults to settings)
        chunks_table_name: Name for chunks table (defaults to settings)
        embedding_dimension: Embedding dimension (defaults to settings.EMBEDDING_DIMENSION)
    
    Returns:
        str: SQL with table names and dimensions replaced
    """
    awards_table = awards_table_name or settings.AWARDS_TABLE_NAME
    chunks_table = chunks_table_name or settings.AWARD_CHUNKS_TABLE_NAME
    embedding_dim = embedding_dimension or settings.EMBEDDING_DIMENSION
    
    with open(sql_template_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # Replace embedding dimension first (before table name replacement)
    sql_content = sql_content.replace('vector(768)', f'vector({embedding_dim})')
    sql_content = sql_content.replace('vector(3072)', f'vector({embedding_dim})')
    
    # Choose index type based on dimension
    # pgvector limits: 
    #   - ivfflat: max 2000 dimensions
    #   - hnsw: max 2000 dimensions (standard vector type)
    #   - hnsw with halfvec: supports up to 4000 dimensions (for > 2000)
    if embedding_dim > 2000:
        # Use HNSW with halfvec casting for high-dimensional vectors (OpenAI 3072)
        # This allows indexing vectors with > 2000 dimensions
        index_pattern = (
            '-- Vector Index for Fast Similarity Search (ivfflat for 768 dimensions)\n'
            'CREATE INDEX idx_chunks_embedding \n'
            'ON award_chunks \n'
            'USING ivfflat (embedding vector_cosine_ops) \n'
            'WITH (lists = 100);'
        )
        index_replacement = (
            f'-- Vector Index for Fast Similarity Search (hnsw with halfvec for {embedding_dim} dimensions)\n'
            '-- Using halfvec cast to support dimensions > 2000\n'
            'CREATE INDEX idx_chunks_embedding \n'
            f'ON award_chunks \n'
            f'USING hnsw ((embedding::halfvec({embedding_dim})) halfvec_cosine_ops) \n'
            'WITH (m = 16, ef_construction = 64);'
        )
        sql_content = sql_content.replace(index_pattern, index_replacement)
        logger.info(
            f"✅ Using HNSW index with halfvec casting for {embedding_dim} dimensions. "
            f"This enables efficient indexing for high-dimensional vectors."
        )
    else:
        # Use ivfflat for dimensions <= 2000 (faster for lower dimensions)
        sql_content = sql_content.replace(
            '-- Vector Index for Fast Similarity Search (ivfflat for 768 dimensions)',
            f'-- Vector Index for Fast Similarity Search (ivfflat for {embedding_dim} dimensions)'
        )
    
    # Replace table names in SQL (after index handling)
    sql_content = sql_content.replace('awards', awards_table)
    sql_content = sql_content.replace('award_chunks', chunks_table)
    
    return sql_content


def create_schema() -> bool:
    """
    Create database schema using configured table names
    
    Returns:
        bool: True if schema created successfully
    """
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except ImportError:
        logger.error(
            "psycopg2 not installed. Install with: pip install psycopg2-binary"
        )
        return False
    
    if not settings.DATABASE_URL:
        logger.error(
            "DATABASE_URL not configured. "
            "Please set DATABASE_URL in your .env file"
        )
        return False
    
    # Get SQL template path
    sql_template = Path(__file__).parent / "create_schema.sql"
    
    if not sql_template.exists():
        logger.error(f"SQL template not found: {sql_template}")
        return False
    
    # Generate SQL with configured table names
    logger.info("Generating schema SQL with configured table names...")
    logger.info(f"  Awards table: {settings.AWARDS_TABLE_NAME}")
    logger.info(f"  Chunks table: {settings.AWARD_CHUNKS_TABLE_NAME}")
    logger.info(f"  Embedding dimension: {settings.EMBEDDING_DIMENSION}")
    logger.info("  💡 TIP: Change AWARDS_TABLE_NAME and AWARD_CHUNKS_TABLE_NAME in .env for new schema versions")
    
    sql_content = create_schema_from_template(
        str(sql_template),
        settings.AWARDS_TABLE_NAME,
        settings.AWARD_CHUNKS_TABLE_NAME,
        settings.EMBEDDING_DIMENSION
    )
    
    # Connect to database
    try:
        logger.info(f"Connecting to database...")
        conn = psycopg2.connect(settings.DATABASE_URL)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Execute schema creation
        logger.info("Creating database schema...")
        logger.warning("⚠️  This will DROP existing tables if they exist!")
        
        cursor.execute(sql_content)
        
        # Fetch any notices
        notices = conn.notices
        for notice in notices:
            logger.info(f"Schema notice: {notice.strip()}")
        
        cursor.close()
        conn.close()
        
        logger.info("✅ Schema created successfully!")
        return True
        
    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        logger.error(f"Error code: {e.pgcode}")
        logger.error(f"Error message: {e.pgerror}")
        return False
    except Exception as e:
        logger.error(f"Schema creation failed: {e}", exc_info=True)
        return False


def verify_schema() -> dict:
    """
    Verify that the schema was created successfully
    
    Returns:
        dict: Verification results
    """
    try:
        import psycopg2
    except ImportError:
        return {"error": "psycopg2 not installed"}
    
    if not settings.DATABASE_URL:
        return {"error": "DATABASE_URL not configured"}
    
    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        cursor = conn.cursor()
        
        # Check awards table
        awards_table = settings.AWARDS_TABLE_NAME
        cursor.execute(f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = %s
            ORDER BY ordinal_position;
        """, (awards_table,))
        awards_columns = cursor.fetchall()
        
        # Check chunks table
        chunks_table = settings.AWARD_CHUNKS_TABLE_NAME
        cursor.execute(f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = %s
            ORDER BY ordinal_position;
        """, (chunks_table,))
        chunks_columns = cursor.fetchall()
        
        # Check indexes
        cursor.execute(f"""
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename IN (%s, %s)
            ORDER BY tablename, indexname;
        """, (awards_table, chunks_table))
        indexes = cursor.fetchall()
        
        # Check extensions
        cursor.execute("""
            SELECT extname 
            FROM pg_extension 
            WHERE extname IN ('vector', 'pg_trgm');
        """)
        extensions = [row[0] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        # Expected columns from CSV
        expected_columns = [
            'award_id', 'award_number', 'title', 'award_status', 'institution',
            'uei', 'duns', 'most_recent_award_date', 'num_support_periods',
            'pm', 'current_budget_period', 'current_project_period', 'pi',
            'supplement_budget_period', 'public_abstract', 'public_abstract_url',
            'agency', 'created_at', 'updated_at'
        ]
        
        actual_columns = [col[0] for col in awards_columns]
        missing_columns = [col for col in expected_columns if col not in actual_columns]
        
        return {
            "success": True,
            "awards_table": awards_table,
            "chunks_table": chunks_table,
            "awards_columns": len(awards_columns),
            "awards_column_names": actual_columns,
            "missing_columns": missing_columns,
            "chunks_columns": len(chunks_columns),
            "indexes_count": len(indexes),
            "extensions": extensions,
            "all_columns_present": len(missing_columns) == 0
        }
        
    except Exception as e:
        return {"error": str(e)}


def main():
    """Main schema creation runner"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Create database schema (first time setup)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create schema with default table names (awards, award_chunks)
  python scripts/create_schema.py
  
  # Create schema with custom table names
  AWARDS_TABLE_NAME=my_awards AWARD_CHUNKS_TABLE_NAME=my_chunks python scripts/create_schema.py
  
  # Verify schema only
  python scripts/create_schema.py --verify-only
  
  # Dry run (show what would be created)
  python scripts/create_schema.py --dry-run
        """
    )
    
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify schema, don't create"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without executing"
    )
    
    args = parser.parse_args()
    
    if args.verify_only:
        logger.info("Verifying schema...")
        result = verify_schema()
        
        if "error" in result:
            logger.error(f"Verification failed: {result['error']}")
            sys.exit(1)
        
        logger.info("Schema Verification Results:")
        logger.info(f"  Awards table: {result['awards_table']} ({result['awards_columns']} columns)")
        logger.info(f"  Chunks table: {result['chunks_table']} ({result['chunks_columns']} columns)")
        logger.info(f"  Indexes: {result['indexes_count']}")
        logger.info(f"  Extensions: {', '.join(result['extensions'])}")
        
        if result['missing_columns']:
            logger.warning(f"  Missing columns: {', '.join(result['missing_columns'])}")
        else:
            logger.info("  ✅ All expected columns present!")
        
        sys.exit(0 if result['all_columns_present'] else 1)
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
        logger.info(f"Awards table name: {settings.AWARDS_TABLE_NAME}")
        logger.info(f"Chunks table name: {settings.AWARD_CHUNKS_TABLE_NAME}")
        
        sql_template = Path(__file__).parent / "create_schema.sql"
        if sql_template.exists():
            sql_content = create_schema_from_template(str(sql_template))
            logger.info(f"\nSQL Preview (first 1000 chars):")
            print(sql_content[:1000])
            logger.info(f"\n... (total {len(sql_content)} characters)")
        else:
            logger.error(f"SQL template not found: {sql_template}")
        
        sys.exit(0)
    
    # Confirm before creating
    logger.warning("⚠️  WARNING: This will CREATE/DROP tables in your database!")
    logger.info(f"Awards table: {settings.AWARDS_TABLE_NAME}")
    logger.info(f"Chunks table: {settings.AWARD_CHUNKS_TABLE_NAME}")
    logger.info(f"Database: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'configured'}")
    
    response = input("\nDo you want to proceed? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        logger.info("Schema creation cancelled by user")
        sys.exit(0)
    
    # Create schema
    success = create_schema()
    
    if success:
        # Verify schema
        logger.info("\nVerifying schema...")
        result = verify_schema()
        
        if "error" not in result:
            logger.info("✅ Schema verification passed!")
            if result['missing_columns']:
                logger.warning(f"⚠️  Missing columns: {', '.join(result['missing_columns'])}")
            else:
                logger.info("✅ All expected columns are present!")
        else:
            logger.warning(f"⚠️  Could not verify schema: {result.get('error')}")
        
        logger.info("\n✅ Schema creation completed successfully!")
        logger.info("\nNext steps:")
        logger.info("  1. Verify the schema in Supabase dashboard")
        logger.info("  2. Run: python scripts/load_csv_to_supabase.py scripts/award_details.csv")
        logger.info("  3. Run: python scripts/index_data.py --async")
    else:
        logger.error("\n❌ Schema creation failed!")
        logger.error("Please check the error messages above")
        sys.exit(1)


if __name__ == "__main__":
    main()

