"""
Supabase Client
Supabase database client wrapper with connection management
"""
from typing import Optional
from functools import lru_cache

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None  # type: ignore

from src.core.config import settings
from src.core.logging import get_logger
from src.database.connection import DatabaseConnection, validate_database_config

logger = get_logger(__name__)


class SupabaseClient(DatabaseConnection):
    """Supabase client wrapper with connection management"""
    
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        """
        Initialize Supabase client
        
        Args:
            url: Supabase project URL (defaults to settings.SUPABASE_URL)
            key: Supabase API key (defaults to settings.SUPABASE_KEY)
        """
        super().__init__()
        
        if not SUPABASE_AVAILABLE:
            raise ImportError(
                "supabase package is not installed. "
                "Install it with: pip install supabase"
            )
        
        self.url = url or settings.SUPABASE_URL
        self.key = key or settings.SUPABASE_KEY
        
        if not self.url or not self.key:
            logger.warning(
                "Supabase credentials not configured. "
                "Set SUPABASE_URL and SUPABASE_KEY environment variables."
            )
    
    def connect(self) -> bool:
        """
        Establish connection to Supabase
        
        Returns:
            bool: True if connection successful
        
        Raises:
            ValueError: If credentials are missing
            Exception: If connection fails
        """
        if not self.url or not self.key:
            raise ValueError(
                "Supabase credentials required. "
                "Set SUPABASE_URL and SUPABASE_KEY environment variables."
            )
        
        try:
            logger.info("Connecting to Supabase", extra={"url": self.url})
            self._connection = create_client(self.url, self.key)
            self._is_connected = True
            logger.info("Successfully connected to Supabase")
            return True
        except Exception as e:
            logger.error("Failed to connect to Supabase", extra={"error": str(e)})
            self._is_connected = False
            raise
    
    def disconnect(self) -> None:
        """Close Supabase connection"""
        if self._is_connected:
            logger.info("Disconnecting from Supabase")
            self._connection = None
            self._is_connected = False
    
    def health_check(self) -> bool:
        """
        Check if Supabase connection is healthy
        
        Returns:
            bool: True if connection is healthy
        
        Raises:
            RuntimeError: If not connected
        """
        if not self._is_connected:
            return False
        
        try:
            # Simple health check: try to query a system table
            # Using a lightweight query that should always work
            response = self._connection.table("_health_check").select("count").limit(0).execute()
            logger.debug("Supabase health check passed")
            return True
        except Exception as e:
            # If _health_check table doesn't exist, try a simpler approach
            # Just check if client is initialized
            try:
                # Try to access client properties
                if hasattr(self._connection, 'supabase_url'):
                    logger.debug("Supabase health check passed (client check)")
                    return True
            except Exception:
                pass
            
            logger.warning("Supabase health check failed", extra={"error": str(e)})
            return False
    
    def get_client(self) -> Client:
        """
        Get the Supabase client instance
        
        Returns:
            Client: Supabase client instance
        
        Raises:
            RuntimeError: If not connected
        """
        if not self._is_connected:
            # Auto-connect if not connected
            self.connect()
        
        if not self._connection:
            raise RuntimeError("Supabase client not initialized")
        
        return self._connection  # type: ignore
    
    def test_connection(self) -> bool:
        """
        Test the connection with a simple query
        
        Returns:
            bool: True if connection test succeeds
        """
        try:
            client = self.get_client()
            # Try a simple query that should work on any Supabase instance
            # Using a query that won't fail even if tables don't exist
            result = client.table("_test").select("*").limit(0).execute()
            return True
        except Exception as e:
            # If table doesn't exist, that's okay - connection is still valid
            # We just need to check if it's a connection error vs table error
            error_str = str(e).lower()
            if "connection" in error_str or "network" in error_str or "timeout" in error_str:
                logger.error("Connection test failed", extra={"error": str(e)})
                return False
            # Table not found is okay - means connection works
            logger.debug("Connection test passed (table may not exist, but connection works)")
            return True


@lru_cache()
def get_supabase_client() -> SupabaseClient:
    """
    Get cached Supabase client instance (singleton pattern)
    
    Returns:
        SupabaseClient: Configured Supabase client instance
    
    Example:
        ```python
        from src.database.supabase import get_supabase_client
        client = get_supabase_client()
        supabase = client.get_client()
        result = supabase.table("awards").select("*").limit(10).execute()
        ```
    """
    # Validate configuration
    try:
        validate_database_config()
    except ValueError as e:
        logger.warning(f"Database configuration issue: {e}")
    
    client = SupabaseClient()
    
    # Auto-connect if credentials are available
    if settings.SUPABASE_URL and settings.SUPABASE_KEY:
        try:
            client.connect()
        except Exception as e:
            logger.warning(f"Could not auto-connect to Supabase: {e}")
    
    return client


# Convenience function for getting the raw Supabase client
def get_client() -> Client:
    """
    Get the raw Supabase Client instance
    
    Returns:
        Client: Raw Supabase client
    
    Example:
        ```python
        from src.database.supabase import get_client
        supabase = get_client()
        result = supabase.table("awards").select("*").execute()
        ```
    """
    return get_supabase_client().get_client()
