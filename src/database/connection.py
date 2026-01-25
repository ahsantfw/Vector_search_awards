"""
Database Connection Management
General database connection utilities and health checks
"""
from typing import Optional
from functools import lru_cache

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class DatabaseConnection:
    """Base class for database connections"""
    
    def __init__(self):
        self._connection: Optional[object] = None
        self._is_connected: bool = False
    
    def connect(self) -> bool:
        """Establish database connection"""
        raise NotImplementedError("Subclasses must implement connect()")
    
    def disconnect(self) -> None:
        """Close database connection"""
        raise NotImplementedError("Subclasses must implement disconnect()")
    
    def health_check(self) -> bool:
        """Check if database connection is healthy"""
        raise NotImplementedError("Subclasses must implement health_check()")
    
    def is_connected(self) -> bool:
        """Check if currently connected"""
        return self._is_connected
    
    def get_connection(self):
        """Get the underlying connection object"""
        if not self._is_connected:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection


def validate_database_config() -> bool:
    """
    Validate that required database configuration is present
    
    Returns:
        bool: True if configuration is valid
    
    Raises:
        ValueError: If required configuration is missing
    """
    if not settings.SUPABASE_URL:
        raise ValueError("SUPABASE_URL is required but not set in configuration")
    
    if not settings.SUPABASE_KEY:
        raise ValueError("SUPABASE_KEY is required but not set in configuration")
    
    logger.debug("Database configuration validated successfully")
    return True
