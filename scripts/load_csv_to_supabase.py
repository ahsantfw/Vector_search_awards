"""
Load CSV Data to Supabase
Loads SBIR awards from CSV file into Supabase awards table
"""
import csv
import sys
import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings
from src.core.logging import get_logger
from src.database.supabase import get_supabase_client

logger = get_logger(__name__)


def read_csv_file(file_path: str) -> List[Dict]:
    """
    Read CSV file and return list of dictionaries
    Deduplicates by award_number to ensure no duplicate records
    
    Args:
        file_path: Path to CSV file
    
    Returns:
        List of dictionaries with award data (deduplicated by award_number)
    """
    awards = []
    seen_award_numbers = {}  # Track award_numbers to prevent duplicates
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # Try to detect delimiter
            sample = f.read(1024)
            f.seek(0)
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
            
            reader = csv.DictReader(f, delimiter=delimiter)
            
            for row_num, row in enumerate(reader, start=2):
                # Get award_number (required field - UNIQUE NOT NULL)
                award_number = (
                    row.get('award_number') or 
                    row.get('award_id') or 
                    row.get('id') or 
                    ''
                ).strip()
                
                # award_id is derived from award_number (they should be the same)
                award_id = award_number if award_number else f'AWARD-{row_num}'
                
                # Validate required fields first
                if not award_number:
                    logger.warning(f"Row {row_num}: Missing award_number (required), skipping")
                    continue
                
                # Get title (required field - NOT NULL)
                title = (
                    row.get('title') or 
                    row.get('Title') or 
                    ''
                ).strip()
                
                if not title:
                    logger.warning(f"Row {row_num}: Missing title (required), skipping")
                    continue
                
                # Get public_abstract (schema expects 'public_abstract', not 'abstract')
                public_abstract = (
                    row.get('public_abstract') or 
                    row.get('abstract') or 
                    row.get('Abstract') or 
                    row.get('description') or 
                    ''
                ).strip()
                
                # Extract agency from award_number prefix (DE-SC = DOE, etc.)
                agency = (
                    row.get('agency') or 
                    row.get('Agency') or 
                    row.get('agency_name') or 
                    ''
                ).strip()
                
                # If no agency, try to infer from award_number
                if not agency and award_number:
                    if award_number.startswith('DE-'):
                        agency = 'DOE'
                    elif award_number.startswith('R01') or award_number.startswith('R43') or award_number.startswith('R44'):
                        agency = 'NIH'
                    elif award_number.startswith('NSF'):
                        agency = 'NSF'
                    elif award_number.startswith('N00014') or award_number.startswith('N68335'):
                        agency = 'DOD'
                
                # If still no agency, use default from config
                if not agency:
                    agency = settings.DEFAULT_AGENCY
                
                # Get all CSV columns according to schema
                award_status = (
                    row.get('award_status') or 
                    row.get('Award Status') or 
                    row.get('status') or 
                    ''
                ).strip()
                
                institution = (
                    row.get('institution') or 
                    row.get('Institution') or 
                    ''
                ).strip()
                
                uei = (
                    row.get('uei') or 
                    row.get('UEI') or 
                    ''
                ).strip()
                
                duns = (
                    row.get('duns') or 
                    row.get('DUNS') or 
                    row.get('duns_number') or 
                    ''
                ).strip()
                
                # Parse date (handle MM/DD/YYYY format)
                most_recent_award_date = None
                date_str = (
                    row.get('most_recent_award_date') or 
                    row.get('Most Recent Award Date') or 
                    row.get('award_date') or 
                    ''
                ).strip()
                if date_str and date_str.upper() != 'N/A':
                    try:
                        # Try MM/DD/YYYY format
                        most_recent_award_date = datetime.strptime(date_str, '%m/%d/%Y').date().isoformat()
                    except ValueError:
                        try:
                            # Try YYYY-MM-DD format
                            most_recent_award_date = datetime.strptime(date_str, '%Y-%m-%d').date().isoformat()
                        except ValueError:
                            logger.warning(f"Row {row_num}: Could not parse date '{date_str}', leaving as NULL")
                
                # Parse integer
                num_support_periods = None
                periods_str = (
                    row.get('num_support_periods') or 
                    row.get('Num Support Periods') or 
                    row.get('support_periods') or 
                    ''
                ).strip()
                if periods_str and periods_str.upper() != 'N/A':
                    try:
                        num_support_periods = int(periods_str)
                    except ValueError:
                        logger.warning(f"Row {row_num}: Could not parse num_support_periods '{periods_str}', leaving as NULL")
                
                pm = (
                    row.get('pm') or 
                    row.get('PM') or 
                    row.get('program_manager') or 
                    ''
                ).strip()
                
                current_budget_period = (
                    row.get('current_budget_period') or 
                    row.get('Current Budget Period') or 
                    row.get('budget_period') or 
                    ''
                ).strip()
                
                current_project_period = (
                    row.get('current_project_period') or 
                    row.get('Current Project Period') or 
                    row.get('project_period') or 
                    ''
                ).strip()
                
                pi = (
                    row.get('pi') or 
                    row.get('PI') or 
                    row.get('principal_investigator') or 
                    ''
                ).strip()
                
                supplement_budget_period = (
                    row.get('supplement_budget_period') or 
                    row.get('Supplement Budget Period') or 
                    row.get('supplement') or 
                    ''
                ).strip()
                
                # Get URL from CSV
                public_abstract_url = (
                    row.get('public_abstract_url') or 
                    row.get('url') or 
                    row.get('abstract_url') or 
                    ''
                ).strip()
                
                # Build award dictionary with all schema columns
                award = {
                    'award_id': award_id,
                    'award_number': award_number,  # Required: UNIQUE NOT NULL
                    'title': title,  # Required: NOT NULL
                    'award_status': award_status if award_status else None,
                    'institution': institution if institution else None,
                    'uei': uei if uei else None,
                    'duns': duns if duns else None,
                    'most_recent_award_date': most_recent_award_date,
                    'num_support_periods': num_support_periods,
                    'pm': pm if pm else None,
                    'current_budget_period': current_budget_period if current_budget_period else None,
                    'current_project_period': current_project_period if current_project_period else None,
                    'pi': pi if pi else None,
                    'supplement_budget_period': supplement_budget_period if supplement_budget_period else None,
                    'public_abstract': public_abstract if public_abstract else None,
                    'public_abstract_url': public_abstract_url if public_abstract_url else None,
                    'agency': agency,  # Default from config if not provided
                }
                
                # Remove None values (but keep empty strings for required fields)
                # PostgreSQL will handle NULL vs empty string appropriately
                award = {k: v for k, v in award.items() if v is not None}
                
                # Deduplicate by award_number (keep last occurrence)
                if award_number in seen_award_numbers:
                    logger.warning(
                        f"Row {row_num}: Duplicate award_number '{award_number}' found. "
                        f"Previous occurrence at row {seen_award_numbers[award_number]}. "
                        f"Keeping this one (last occurrence)."
                    )
                    # Remove the previous occurrence
                    awards = [a for a in awards if a.get('award_number') != award_number]
                
                seen_award_numbers[award_number] = row_num
                awards.append(award)
        
        duplicates_removed = len(seen_award_numbers) - len(awards)
        if duplicates_removed > 0:
            logger.warning(
                f"Found {duplicates_removed} duplicate award_number(s) in CSV. "
                f"Removed duplicates, keeping last occurrence for each."
            )
        
        logger.info(f"Read {len(awards)} unique awards from CSV file")
        return awards
        
    except Exception as e:
        logger.error(f"Failed to read CSV file: {e}")
        raise


def create_awards_table_if_not_exists(supabase_client):
    """
    Create awards table if it doesn't exist
    
    Args:
        supabase_client: Supabase client instance
    """
    # Use configured table name
    awards_table = settings.AWARDS_TABLE_NAME
    
    try:
        # Try to query the table to see if it exists
        supabase_client.table(awards_table).select("award_id").limit(1).execute()
        logger.info(f"Awards table '{awards_table}' already exists")
    except Exception:
        # Table doesn't exist, create it
        logger.info("Creating awards table...")
        
        # Note: In Supabase, you typically create tables via SQL migrations
        # This is a simplified version - you may need to run SQL directly
        logger.warning(
            f"Table creation via Python client is limited. "
            f"Please ensure the '{awards_table}' table exists in Supabase with columns: "
            f"award_id (text, primary key), title (text), abstract (text), agency (text)"
        )


def upload_awards_to_supabase(awards: List[Dict], batch_size: Optional[int] = None) -> int:
    """
    Upload awards to Supabase in batches
    
    Args:
        awards: List of award dictionaries
        batch_size: Number of awards to upload per batch (defaults to settings.BATCH_SIZE)
    
    Returns:
        Number of awards successfully uploaded
    """
    # Use config value if not provided
    if batch_size is None:
        batch_size = settings.BATCH_SIZE
    
    try:
        supabase_client_wrapper = get_supabase_client()
        supabase_client = supabase_client_wrapper.get_client()
        
        # Ensure table exists
        create_awards_table_if_not_exists(supabase_client)
        
        uploaded_count = 0
        total_batches = (len(awards) + batch_size - 1) // batch_size
        
        logger.info(f"Uploading {len(awards)} awards in {total_batches} batches...")
        
        for i in range(0, len(awards), batch_size):
            batch = awards[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            
            # Deduplicate batch by award_number (keep last occurrence)
            # This prevents "ON CONFLICT DO UPDATE cannot affect row a second time" error
            # We use award_number because it's the UNIQUE field in the database
            seen_numbers = {}
            deduplicated_batch = []
            duplicates_found = 0
            
            for award in batch:
                award_number = award.get('award_number')
                if not award_number:
                    logger.warning(f"Batch {batch_num}: Award missing award_number, skipping")
                    continue
                
                if award_number in seen_numbers:
                    duplicates_found += 1
                    # Replace the previous occurrence with this one (keep last)
                    # Remove the old one and add the new one
                    deduplicated_batch = [a for a in deduplicated_batch if a.get('award_number') != award_number]
                seen_numbers[award_number] = True
                deduplicated_batch.append(award)
            
            if duplicates_found > 0:
                logger.warning(
                    f"Batch {batch_num}: Found {duplicates_found} duplicate award_number(s), "
                    f"deduplicated to {len(deduplicated_batch)} records"
                )
            
            try:
                # Use configured table name
                awards_table = settings.AWARDS_TABLE_NAME
                
                # Use upsert to update existing records or insert new ones
                # This will update existing awards with new data (including URLs)
                # Use award_number as conflict key since it's UNIQUE NOT NULL
                response = supabase_client.table(awards_table).upsert(
                    deduplicated_batch,
                    on_conflict="award_number"  # Use award_number as the conflict key (UNIQUE field)
                ).execute()
                
                uploaded_count += len(deduplicated_batch)
                logger.info(
                    f"Batch {batch_num}/{total_batches}: Upserted {len(deduplicated_batch)} awards "
                    f"({uploaded_count}/{len(awards)} total)"
                )
                
            except Exception as e:
                error_msg = str(e).lower()
                # If error is about missing column, try without URL
                if 'public_abstract_url' in error_msg or 'column' in error_msg:
                    logger.warning(f"URL column may not exist. Retrying batch without URLs...")
                    # Remove URL from batch and retry (deduplicate again)
                    batch_without_url = []
                    seen_numbers = {}
                    for award in deduplicated_batch:
                        award_number = award.get('award_number')
                        if award_number and award_number not in seen_numbers:
                            seen_numbers[award_number] = True
                            award_copy = award.copy()
                            award_copy.pop('public_abstract_url', None)
                            batch_without_url.append(award_copy)
                    
                    try:
                        awards_table = settings.AWARDS_TABLE_NAME
                        response = supabase_client.table(awards_table).upsert(
                            batch_without_url,
                            on_conflict="award_number"  # Use award_number as conflict key
                        ).execute()
                        uploaded_count += len(batch_without_url)
                        logger.info(
                            f"Batch {batch_num}/{total_batches}: Upserted {len(batch_without_url)} awards "
                            f"(without URLs - column may not exist) ({uploaded_count}/{len(awards)} total)"
                        )
                    except Exception as e2:
                        logger.error(f"Failed to upsert batch {batch_num} even without URLs: {e2}")
                        # Try individual upserts for this batch
                        awards_table = settings.AWARDS_TABLE_NAME
                        for award in batch_without_url:
                            try:
                                supabase_client.table(awards_table).upsert(
                                    award,
                                    on_conflict="award_number"  # Use award_number as conflict key
                                ).execute()
                                uploaded_count += 1
                            except Exception as e3:
                                logger.error(f"Failed to upsert award {award.get('award_number')}: {e3}")
                else:
                    logger.error(f"Failed to upsert batch {batch_num}: {e}")
                    # Try individual upserts for this batch
                    awards_table = settings.AWARDS_TABLE_NAME
                    for award in deduplicated_batch:
                        try:
                            # Remove URL if column doesn't exist
                            award_copy = award.copy()
                            award_copy.pop('public_abstract_url', None)
                            supabase_client.table(awards_table).upsert(
                                award_copy,
                                on_conflict="award_number"  # Use award_number as conflict key
                            ).execute()
                            uploaded_count += 1
                        except Exception as e2:
                            logger.error(f"Failed to upsert award {award.get('award_number')}: {e2}")
        
        logger.info(f"Successfully uploaded {uploaded_count}/{len(awards)} awards")
        return uploaded_count
        
    except Exception as e:
        logger.error(f"Failed to upload awards: {e}")
        raise


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Load CSV data into Supabase")
    parser.add_argument(
        "csv_file",
        help="Path to CSV file containing SBIR awards"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help=f"Number of records to upload per batch (default: {settings.BATCH_SIZE} from config)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of records to load (for testing)"
    )
    
    args = parser.parse_args()
    
    # Check if file exists
    if not os.path.exists(args.csv_file):
        logger.error(f"CSV file not found: {args.csv_file}")
        sys.exit(1)
    
    # Check Supabase configuration
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        logger.error(
            "Supabase credentials not configured. "
            "Please set SUPABASE_URL and SUPABASE_KEY in your .env file"
        )
        sys.exit(1)
    
    # Read CSV
    logger.info(f"Reading CSV file: {args.csv_file}")
    awards = read_csv_file(args.csv_file)
    
    # Limit if specified
    if args.limit:
        awards = awards[:args.limit]
        logger.info(f"Limited to {len(awards)} awards for testing")
    
    # Upload to Supabase
    logger.info("Starting upload to Supabase...")
    batch_size = args.batch_size if args.batch_size is not None else settings.BATCH_SIZE
    logger.info(f"Using batch size: {batch_size} (from {'command-line' if args.batch_size else 'config'})")
    uploaded_count = upload_awards_to_supabase(awards, batch_size=batch_size)
    
    logger.info(f"✅ Upload complete! {uploaded_count} awards uploaded to Supabase")
    
    return uploaded_count


if __name__ == "__main__":
    main()

