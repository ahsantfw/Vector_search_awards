"""
Delete Database Schema
Deletes schema components (tables, indexes, triggers, functions) with safety checks
"""
import sys
import os
import argparse
from pathlib import Path
from typing import List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def get_database_connection():
    """Get database connection"""
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except ImportError:
        logger.error(
            "psycopg2 not installed. Install with: pip install psycopg2-binary"
        )
        return None, None
    
    if not settings.DATABASE_URL:
        logger.error(
            "DATABASE_URL not configured. "
            "Please set DATABASE_URL in your .env file"
        )
        return None, None
    
    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        return conn, cursor
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return None, None


def list_schema_components() -> dict:
    """List all schema components that can be deleted"""
    conn, cursor = get_database_connection()
    if not cursor:
        return {"error": "Could not connect to database"}
    
    try:
        awards_table = settings.AWARDS_TABLE_NAME
        chunks_table = settings.AWARD_CHUNKS_TABLE_NAME
        
        components = {
            "tables": [],
            "indexes": [],
            "triggers": [],
            "functions": [],
            "extensions": []
        }
        
        # Check if tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN (%s, %s)
        """, (awards_table, chunks_table))
        
        for row in cursor.fetchall():
            components["tables"].append(row[0])
        
        # Check indexes
        cursor.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND (tablename = %s OR tablename = %s)
        """, (awards_table, chunks_table))
        
        for row in cursor.fetchall():
            components["indexes"].append(row[0])
        
        # Check triggers
        cursor.execute("""
            SELECT trigger_name 
            FROM information_schema.triggers 
            WHERE trigger_schema = 'public' 
            AND event_object_table IN (%s, %s)
        """, (awards_table, chunks_table))
        
        for row in cursor.fetchall():
            components["triggers"].append(row[0])
        
        # Check functions
        cursor.execute("""
            SELECT routine_name 
            FROM information_schema.routines 
            WHERE routine_schema = 'public' 
            AND routine_name = 'update_updated_at_column'
        """)
        
        for row in cursor.fetchall():
            components["functions"].append(row[0])
        
        # Check extensions
        cursor.execute("""
            SELECT extname 
            FROM pg_extension 
            WHERE extname IN ('vector', 'pg_trgm')
        """)
        
        for row in cursor.fetchall():
            components["extensions"].append(row[0])
        
        cursor.close()
        conn.close()
        
        return components
        
    except Exception as e:
        logger.error(f"Failed to list schema components: {e}")
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        return {"error": str(e)}


def delete_table(table_name: str, cascade: bool = False) -> bool:
    """Delete a specific table"""
    conn, cursor = get_database_connection()
    if not cursor:
        return False
    
    try:
        cascade_clause = " CASCADE" if cascade else ""
        sql = f"DROP TABLE IF EXISTS {table_name}{cascade_clause};"
        
        logger.info(f"Dropping table: {table_name}")
        cursor.execute(sql)
        logger.info(f"✅ Successfully dropped table: {table_name}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to drop table {table_name}: {e}")
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        return False


def delete_index(index_name: str) -> bool:
    """Delete a specific index"""
    conn, cursor = get_database_connection()
    if not cursor:
        return False
    
    try:
        sql = f"DROP INDEX IF EXISTS {index_name};"
        
        logger.info(f"Dropping index: {index_name}")
        cursor.execute(sql)
        logger.info(f"✅ Successfully dropped index: {index_name}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to drop index {index_name}: {e}")
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        return False


def delete_trigger(trigger_name: str, table_name: str) -> bool:
    """Delete a specific trigger"""
    conn, cursor = get_database_connection()
    if not cursor:
        return False
    
    try:
        sql = f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name};"
        
        logger.info(f"Dropping trigger: {trigger_name} on {table_name}")
        cursor.execute(sql)
        logger.info(f"✅ Successfully dropped trigger: {trigger_name}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to drop trigger {trigger_name}: {e}")
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        return False


def delete_function(function_name: str) -> bool:
    """Delete a specific function"""
    conn, cursor = get_database_connection()
    if not cursor:
        return False
    
    try:
        sql = f"DROP FUNCTION IF EXISTS {function_name}() CASCADE;"
        
        logger.info(f"Dropping function: {function_name}")
        cursor.execute(sql)
        logger.info(f"✅ Successfully dropped function: {function_name}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to drop function {function_name}: {e}")
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        return False


def delete_extension(extension_name: str) -> bool:
    """Delete a specific extension"""
    conn, cursor = get_database_connection()
    if not cursor:
        return False
    
    try:
        sql = f"DROP EXTENSION IF EXISTS {extension_name} CASCADE;"
        
        logger.info(f"Dropping extension: {extension_name}")
        cursor.execute(sql)
        logger.info(f"✅ Successfully dropped extension: {extension_name}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to drop extension {extension_name}: {e}")
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        return False


def delete_all_schema() -> bool:
    """Delete entire schema (both tables with CASCADE)"""
    conn, cursor = get_database_connection()
    if not cursor:
        return False
    
    try:
        awards_table = settings.AWARDS_TABLE_NAME
        chunks_table = settings.AWARD_CHUNKS_TABLE_NAME
        
        logger.warning("⚠️  Deleting entire schema...")
        logger.info(f"  Awards table: {awards_table}")
        logger.info(f"  Chunks table: {chunks_table}")
        
        # Drop chunks table first (has foreign key to awards)
        logger.info(f"Dropping table: {chunks_table}")
        cursor.execute(f"DROP TABLE IF EXISTS {chunks_table} CASCADE;")
        
        # Drop awards table
        logger.info(f"Dropping table: {awards_table}")
        cursor.execute(f"DROP TABLE IF EXISTS {awards_table} CASCADE;")
        
        # Drop function (if exists)
        logger.info("Dropping function: update_updated_at_column")
        cursor.execute("DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;")
        
        logger.info("✅ Successfully deleted entire schema")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete schema: {e}")
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        return False


def delete_all_indexes() -> bool:
    """Delete all indexes for configured tables"""
    conn, cursor = get_database_connection()
    if not cursor:
        return False
    
    try:
        awards_table = settings.AWARDS_TABLE_NAME
        chunks_table = settings.AWARD_CHUNKS_TABLE_NAME
        
        # Get all indexes
        cursor.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND (tablename = %s OR tablename = %s)
        """, (awards_table, chunks_table))
        
        indexes = [row[0] for row in cursor.fetchall()]
        
        if not indexes:
            logger.info("No indexes found to delete")
            cursor.close()
            conn.close()
            return True
        
        logger.info(f"Deleting {len(indexes)} indexes...")
        for index_name in indexes:
            cursor.execute(f"DROP INDEX IF EXISTS {index_name};")
            logger.info(f"  ✅ Deleted index: {index_name}")
        
        logger.info(f"✅ Successfully deleted {len(indexes)} indexes")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete indexes: {e}")
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        return False


def delete_all_triggers() -> bool:
    """Delete all triggers for configured tables"""
    conn, cursor = get_database_connection()
    if not cursor:
        return False
    
    try:
        awards_table = settings.AWARDS_TABLE_NAME
        chunks_table = settings.AWARD_CHUNKS_TABLE_NAME
        
        # Get all triggers
        cursor.execute("""
            SELECT trigger_name, event_object_table 
            FROM information_schema.triggers 
            WHERE trigger_schema = 'public' 
            AND event_object_table IN (%s, %s)
        """, (awards_table, chunks_table))
        
        triggers = cursor.fetchall()
        
        if not triggers:
            logger.info("No triggers found to delete")
            cursor.close()
            conn.close()
            return True
        
        logger.info(f"Deleting {len(triggers)} triggers...")
        for trigger_name, table_name in triggers:
            cursor.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name};")
            logger.info(f"  ✅ Deleted trigger: {trigger_name} on {table_name}")
        
        logger.info(f"✅ Successfully deleted {len(triggers)} triggers")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to delete triggers: {e}")
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Delete database schema components for SBIR awards"
    )
    
    parser.add_argument(
        "--all",
        action="store_true",
        help="Delete entire schema (both tables, indexes, triggers, functions)"
    )
    
    parser.add_argument(
        "--table",
        type=str,
        help="Delete specific table (use 'awards' or 'chunks' or full table name)"
    )
    
    parser.add_argument(
        "--index",
        type=str,
        help="Delete specific index by name"
    )
    
    parser.add_argument(
        "--trigger",
        type=str,
        help="Delete specific trigger by name (requires --table)"
    )
    
    parser.add_argument(
        "--function",
        type=str,
        help="Delete specific function by name"
    )
    
    parser.add_argument(
        "--extension",
        type=str,
        help="Delete specific extension by name (e.g., 'vector', 'pg_trgm')"
    )
    
    parser.add_argument(
        "--all-indexes",
        action="store_true",
        help="Delete all indexes for configured tables"
    )
    
    parser.add_argument(
        "--all-triggers",
        action="store_true",
        help="Delete all triggers for configured tables"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all schema components that can be deleted"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    
    parser.add_argument(
        "--cascade",
        action="store_true",
        help="Use CASCADE when deleting tables (drops dependent objects)"
    )
    
    args = parser.parse_args()
    
    # List mode
    if args.list:
        logger.info("Listing schema components...")
        components = list_schema_components()
        
        if "error" in components:
            logger.error(f"Failed to list components: {components['error']}")
            sys.exit(1)
        
        logger.info("\n📋 Schema Components:")
        logger.info(f"  Tables: {len(components['tables'])}")
        for table in components['tables']:
            logger.info(f"    - {table}")
        
        logger.info(f"\n  Indexes: {len(components['indexes'])}")
        for index in components['indexes']:
            logger.info(f"    - {index}")
        
        logger.info(f"\n  Triggers: {len(components['triggers'])}")
        for trigger in components['triggers']:
            logger.info(f"    - {trigger}")
        
        logger.info(f"\n  Functions: {len(components['functions'])}")
        for func in components['functions']:
            logger.info(f"    - {func}")
        
        logger.info(f"\n  Extensions: {len(components['extensions'])}")
        for ext in components['extensions']:
            logger.info(f"    - {ext}")
        
        sys.exit(0)
    
    # Dry-run mode
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
        logger.info(f"Awards table: {settings.AWARDS_TABLE_NAME}")
        logger.info(f"Chunks table: {settings.AWARD_CHUNKS_TABLE_NAME}")
        
        components = list_schema_components()
        if "error" not in components:
            logger.info("\nWould delete:")
            if args.all:
                logger.info("  - Entire schema (both tables, indexes, triggers, functions)")
            if args.table:
                table_name = args.table
                if table_name == "awards":
                    table_name = settings.AWARDS_TABLE_NAME
                elif table_name == "chunks":
                    table_name = settings.AWARD_CHUNKS_TABLE_NAME
                logger.info(f"  - Table: {table_name}")
            if args.index:
                logger.info(f"  - Index: {args.index}")
            if args.trigger:
                logger.info(f"  - Trigger: {args.trigger}")
            if args.function:
                logger.info(f"  - Function: {args.function}")
            if args.extension:
                logger.info(f"  - Extension: {args.extension}")
            if args.all_indexes:
                logger.info(f"  - All indexes ({len(components['indexes'])} indexes)")
            if args.all_triggers:
                logger.info(f"  - All triggers ({len(components['triggers'])} triggers)")
        
        sys.exit(0)
    
    # Confirm before deleting
    if args.all or args.table or args.index or args.trigger or args.function or args.extension or args.all_indexes or args.all_triggers:
        logger.warning("⚠️  WARNING: This will DELETE data from your database!")
        logger.info(f"Database: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'configured'}")
        
        response = input("\nDo you want to proceed? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            logger.info("Deletion cancelled by user")
            sys.exit(0)
    
    # Execute deletions
    success = True
    
    if args.all:
        success = delete_all_schema() and success
    
    if args.table:
        table_name = args.table
        # Map shorthand names to actual table names
        if table_name == "awards":
            table_name = settings.AWARDS_TABLE_NAME
        elif table_name == "chunks":
            table_name = settings.AWARD_CHUNKS_TABLE_NAME
        
        success = delete_table(table_name, cascade=args.cascade) and success
    
    if args.index:
        success = delete_index(args.index) and success
    
    if args.trigger:
        if not args.table:
            logger.error("--trigger requires --table to specify which table")
            sys.exit(1)
        table_name = args.table
        if table_name == "awards":
            table_name = settings.AWARDS_TABLE_NAME
        elif table_name == "chunks":
            table_name = settings.AWARD_CHUNKS_TABLE_NAME
        success = delete_trigger(args.trigger, table_name) and success
    
    if args.function:
        success = delete_function(args.function) and success
    
    if args.extension:
        success = delete_extension(args.extension) and success
    
    if args.all_indexes:
        success = delete_all_indexes() and success
    
    if args.all_triggers:
        success = delete_all_triggers() and success
    
    if not (args.all or args.table or args.index or args.trigger or args.function or args.extension or args.all_indexes or args.all_triggers):
        logger.error("No deletion action specified. Use --help for usage.")
        sys.exit(1)
    
    if success:
        logger.info("\n✅ Deletion completed successfully!")
    else:
        logger.error("\n❌ Some deletions failed. Check error messages above.")
        sys.exit(1)


if __name__ == "__main__":
    main()

