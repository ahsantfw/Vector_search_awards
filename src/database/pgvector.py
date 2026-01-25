"""
pgvector Operations
PostgreSQL pgvector extension operations for vector storage and search
"""
from typing import List, Optional, Dict, Any
from functools import lru_cache
import threading

try:
    import psycopg2
    from psycopg2.extras import execute_values
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    from psycopg2.pool import ThreadedConnectionPool
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    psycopg2 = None  # type: ignore
    ThreadedConnectionPool = None  # type: ignore

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None  # type: ignore

from src.core.config import settings
from src.core.logging import get_logger
from src.database.supabase import get_supabase_client

logger = get_logger(__name__)


class PgVectorManager:
    """Manager for pgvector operations in PostgreSQL"""
    
    def __init__(self, database_url: Optional[str] = None, pool_size: int = 5):
        """
        Initialize pgvector manager with connection pooling
        
        Args:
            database_url: PostgreSQL connection URL (defaults to settings.DATABASE_URL)
            pool_size: Number of connections in pool (default: 5)
        """
        self.database_url = database_url or settings.DATABASE_URL
        self.pool_size = pool_size
        self._connection_pool: Optional[Any] = None
        self._lock = threading.Lock()
        
        if not self.database_url:
            logger.warning(
                "DATABASE_URL not configured. "
                "Set DATABASE_URL environment variable for pgvector operations."
            )
        else:
            self._init_connection_pool()
    
    def _init_connection_pool(self):
        """Initialize connection pool"""
        if not PSYCOPG2_AVAILABLE or not ThreadedConnectionPool:
            return
        
        try:
            self._connection_pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=self.pool_size,
                dsn=self.database_url
            )
            logger.info(f"Connection pool initialized (size: {self.pool_size})")
        except Exception as e:
            logger.warning(f"Failed to create connection pool: {e}. Using single connections.")
            self._connection_pool = None
    
    def _get_connection(self):
        """Get connection from pool or create new one"""
        if self._connection_pool:
            try:
                return self._connection_pool.getconn()
            except Exception as e:
                logger.warning(f"Failed to get connection from pool: {e}")
                return psycopg2.connect(self.database_url)
        else:
            return psycopg2.connect(self.database_url)
    
    def _put_connection(self, conn):
        """Return connection to pool"""
        if self._connection_pool:
            try:
                self._connection_pool.putconn(conn)
            except Exception as e:
                logger.warning(f"Failed to return connection to pool: {e}")
                try:
                    conn.close()
                except:
                    pass
        else:
            try:
                conn.close()
            except:
                pass
    
    def enable_extension(self) -> bool:
        """
        Enable pgvector extension in PostgreSQL
        
        Returns:
            bool: True if extension enabled successfully
        
        Raises:
            RuntimeError: If database connection fails
            Exception: If extension enable fails
        """
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2 package is not installed. "
                "Install it with: pip install psycopg2-binary"
            )
        
        if not self.database_url:
            raise ValueError("DATABASE_URL is required for pgvector operations")
        
        try:
            logger.info("Enabling pgvector extension")
            
            # Connect to database
            conn = psycopg2.connect(self.database_url)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            
            # Enable extension
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # Verify extension
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector');"
            )
            enabled = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            if enabled:
                logger.info("pgvector extension enabled successfully")
                return True
            else:
                logger.error("pgvector extension not found after creation")
                return False
                
        except Exception as e:
            logger.error("Failed to enable pgvector extension", extra={"error": str(e)})
            raise
    
    def check_extension(self) -> bool:
        """
        Check if pgvector extension is enabled
        
        Returns:
            bool: True if extension is enabled
        """
        if not PSYCOPG2_AVAILABLE or not self.database_url:
            return False
        
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector');"
            )
            enabled = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            return enabled
        except Exception as e:
            logger.warning("Failed to check pgvector extension", extra={"error": str(e)})
            return False
    
    def create_vector_table(
        self,
        table_name: Optional[str] = None,
        dimension: int = 768
    ) -> bool:
        """
        Create a table with vector column for storing embeddings
        
        Args:
            table_name: Name of the table to create (defaults to settings.AWARD_CHUNKS_TABLE_NAME)
            dimension: Dimension of the vector (default: 768 for Sentence Transformers)
        
        Returns:
            bool: True if table created successfully
        """
        if not PSYCOPG2_AVAILABLE or not self.database_url:
            raise RuntimeError("Database connection not available")
        
        # Use configured table name if not provided
        if table_name is None:
            table_name = settings.AWARD_CHUNKS_TABLE_NAME
        
        try:
            logger.info(f"Creating vector table: {table_name}", extra={"dimension": dimension})
            
            conn = psycopg2.connect(self.database_url)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            
            # Create table with vector column
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                chunk_id SERIAL PRIMARY KEY,
                award_id VARCHAR(255) NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                embedding vector({dimension}),
                field_name VARCHAR(100),
                text_hash VARCHAR(64),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(award_id, chunk_index, field_name)
            );
            """
            
            cursor.execute(create_table_sql)
            
            # Create indexes
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_award_id 
                ON {table_name}(award_id);
            """)
            
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_text_hash 
                ON {table_name}(text_hash);
            """)
            
            # Create vector similarity index
            # Note: Both HNSW and IVFFlat have a 2000 dimension limit
            # For 3072 dimensions, we skip the index (searches will be slower)
            # Options: Use 256-dim embeddings or Qdrant for better performance
            if dimension <= 2000:
                # Use HNSW for dimensions <= 2000 (faster)
                logger.info(f"Creating HNSW index for {dimension} dimensions")
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{table_name}_embedding 
                    ON {table_name} 
                    USING hnsw (embedding vector_cosine_ops);
                """)
            else:
                # Skip index for dimensions > 2000 (3072 not supported)
                logger.warning(
                    f"Skipping vector index for {dimension} dimensions "
                    "(HNSW/IVFFlat limit is 2000). "
                    "Consider using 256-dim embeddings or Qdrant for better performance."
                )
            
            cursor.close()
            conn.close()
            
            logger.info(f"Vector table '{table_name}' created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create vector table: {table_name}", extra={"error": str(e)})
            raise
    
    def insert_vectors(
        self,
        vectors: List[Dict[str, Any]],
        table_name: Optional[str] = None
    ) -> int:
        """
        Insert vectors into the database (optimized with connection pooling and numpy)
        
        Args:
            vectors: List of dictionaries with vector data
                Each dict should have: award_id, chunk_index, chunk_text, 
                embedding (list), field_name, text_hash
            table_name: Name of the table to insert into (defaults to settings.AWARD_CHUNKS_TABLE_NAME)
        
        Returns:
            int: Number of rows inserted
        """
        if not PSYCOPG2_AVAILABLE or not self.database_url:
            raise RuntimeError("Database connection not available")
        
        if not vectors:
            return 0
        
        # Use configured table name if not provided
        if table_name is None:
            table_name = settings.AWARD_CHUNKS_TABLE_NAME
        
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Optimize embedding string conversion using numpy if available
            if NUMPY_AVAILABLE:
                # Convert all embeddings to numpy arrays for faster processing
                values = []
                for vec in vectors:
                    embedding = vec["embedding"]
                    if isinstance(embedding, list):
                        # Use numpy for faster string conversion
                        embedding_array = np.array(embedding, dtype=np.float32)
                        embedding_str = "[" + ",".join(embedding_array.astype(str)) + "]"
                    else:
                        embedding_str = "[" + ",".join(map(str, embedding)) + "]"
                    
                    values.append((
                        vec["award_id"],
                        vec["chunk_index"],
                        vec["chunk_text"],
                        embedding_str,
                        vec.get("field_name"),
                        vec.get("text_hash")
                    ))
            else:
                # Fallback: optimized string conversion
                values = []
                for vec in vectors:
                    embedding = vec["embedding"]
                    # Use join with generator for memory efficiency
                    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                    
                    values.append((
                        vec["award_id"],
                        vec["chunk_index"],
                        vec["chunk_text"],
                        embedding_str,
                        vec.get("field_name"),
                        vec.get("text_hash")
                    ))
            
            # Insert using execute_values for efficiency
            # Handle conflicts: text_hash is UNIQUE, so we need to handle duplicate text_hash
            # Strategy: 
            # 1. Deduplicate within the batch first (same text_hash in same batch)
            # 2. Check which text_hashes already exist in database
            # 3. Filter out both types of duplicates
            # 4. Use ON CONFLICT DO NOTHING for text_hash to handle race conditions
            
            # Step 1: Deduplicate within the batch (keep first occurrence of each text_hash)
            seen_in_batch = set()
            deduplicated_values = []
            for v in values:
                text_hash = v[5]  # text_hash is at index 5
                if text_hash and text_hash in seen_in_batch:
                    # Skip duplicate within batch
                    continue
                if text_hash:
                    seen_in_batch.add(text_hash)
                deduplicated_values.append(v)
            
            if len(deduplicated_values) < len(values):
                logger.info(
                    f"Deduplicated {len(values) - len(deduplicated_values)} duplicate chunks within batch",
                    extra={"original": len(values), "deduplicated": len(deduplicated_values)}
                )
            
            # Step 2: Skip database check - let ON CONFLICT handle it (MUCH FASTER!)
            # The database check was a major bottleneck. ON CONFLICT DO NOTHING is fast enough.
            # We already deduplicated within batch, so most conflicts are handled.
            # PostgreSQL handles ON CONFLICT efficiently internally.
            filtered_values = deduplicated_values
            
            # Step 3: Insert chunks - ON CONFLICT will handle duplicates efficiently
            # This is much faster than querying database first (removes extra round-trip)
            insert_sql = f"""
                INSERT INTO {table_name} 
                (award_id, chunk_index, chunk_text, embedding, field_name, text_hash)
                VALUES %s
                ON CONFLICT (text_hash)
                DO NOTHING
            """
            
            execute_values(cursor, insert_sql, filtered_values, page_size=1000)
            rows_inserted = cursor.rowcount
            
            conn.commit()
            cursor.close()
            
            logger.info(f"Inserted {rows_inserted} vectors into {table_name}")
            return rows_inserted
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to insert vectors", extra={"error": str(e)})
            raise
        finally:
            if conn:
                self._put_connection(conn)
    
    def search_vectors(
        self,
        query_vector: List[float],
        top_k: int = 10,
        table_name: Optional[str] = None,
        filter_agency: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors using cosine similarity (optimized with connection pooling)
        
        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            table_name: Name of the table to search (defaults to settings.AWARD_CHUNKS_TABLE_NAME)
            filter_agency: Optional agency filter
        
        Returns:
            List of dictionaries with search results
        """
        if not PSYCOPG2_AVAILABLE or not self.database_url:
            raise RuntimeError("Database connection not available")
        
        # Use configured table name if not provided
        if table_name is None:
            table_name = settings.AWARD_CHUNKS_TABLE_NAME
        
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Optimize query vector string conversion
            if NUMPY_AVAILABLE:
                query_array = np.array(query_vector, dtype=np.float32)
                query_vector_str = "[" + ",".join(query_array.astype(str)) + "]"
            else:
                query_vector_str = "[" + ",".join(str(x) for x in query_vector) + "]"
            
            # Build query with optional filter
            filter_clause = ""
            if filter_agency:
                filter_clause = f"WHERE field_name = '{filter_agency}'"
            
            # Use halfvec casting for dimensions > 2000 to leverage HNSW index
            embedding_dim = settings.EMBEDDING_DIMENSION
            if embedding_dim > 2000:
                # Cast both query and column to halfvec for index usage
                similarity_expr = f"1 - (embedding::halfvec({embedding_dim}) <=> '{query_vector_str}'::halfvec({embedding_dim}))"
                order_expr = f"embedding::halfvec({embedding_dim}) <=> '{query_vector_str}'::halfvec({embedding_dim})"
            else:
                # Standard vector operations for dimensions <= 2000
                similarity_expr = f"1 - (embedding <=> '{query_vector_str}'::vector)"
                order_expr = f"embedding <=> '{query_vector_str}'::vector"
            
            search_sql = f"""
                SELECT 
                    chunk_id,
                    award_id,
                    chunk_index,
                    chunk_text,
                    field_name,
                    {similarity_expr} as similarity
                FROM {table_name}
                {filter_clause}
                ORDER BY {order_expr}
                LIMIT {top_k}
            """
            
            cursor.execute(search_sql)
            results = cursor.fetchall()
            
            # Convert to list of dicts
            search_results = []
            for row in results:
                search_results.append({
                    "chunk_id": row[0],
                    "award_id": row[1],
                    "chunk_index": row[2],
                    "chunk_text": row[3],
                    "field_name": row[4],
                    "similarity": float(row[5])
                })
            
            cursor.close()
            
            logger.debug(f"Found {len(search_results)} similar vectors")
            return search_results
            
        except Exception as e:
            logger.error("Failed to search vectors", extra={"error": str(e)})
            raise
        finally:
            if conn:
                self._put_connection(conn)


@lru_cache()
def get_pgvector_manager() -> PgVectorManager:
    """
    Get cached pgvector manager instance (singleton pattern)
    
    Returns:
        PgVectorManager: Configured pgvector manager instance
    """
    return PgVectorManager()


def setup_pgvector() -> bool:
    """
    Set up pgvector extension and create necessary tables
    
    Returns:
        bool: True if setup successful
    """
    manager = get_pgvector_manager()
    
    # Enable extension
    if not manager.check_extension():
        manager.enable_extension()
    
    # Create vector table
    dimension = settings.EMBEDDING_DIMENSION
    manager.create_vector_table(dimension=dimension)
    
    logger.info("pgvector setup completed successfully")
    return True
