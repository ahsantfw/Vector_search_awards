"""
Configuration Management
Application settings loaded from environment variables

This module provides type-safe configuration using Pydantic Settings.
All configuration values can be set via environment variables or .env file.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional
import os
from pathlib import Path


class Settings(BaseSettings):
    """Application settings with type validation and defaults"""
    
    # ==================== Environment ====================
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # ==================== Database (Supabase) ====================
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    
    # ==================== Table Names (Configurable) ====================
    AWARDS_TABLE_NAME: str = os.getenv("AWARDS_TABLE_NAME", "awards")
    AWARD_CHUNKS_TABLE_NAME: str = os.getenv("AWARD_CHUNKS_TABLE_NAME", "award_chunks")
    
    # ==================== Default Values ====================
    DEFAULT_AGENCY: str = os.getenv("DEFAULT_AGENCY", "PAMS")
    
    # ==================== Batch Processing ====================
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "100"))  # Batch size for database operations
    
    # ==================== Vector Store ====================
    # Choice: "pgvector" (Supabase extension) or "qdrant" (separate service)
    VECTOR_STORE: str = os.getenv("VECTOR_STORE", "pgvector")
    
    # Qdrant settings (if using Qdrant)
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    
    # ==================== Embeddings ====================
    # Choose: "openai" or "sentence-transformers" (default: sentence-transformers for free/fast)
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "sentence-transformers")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2")
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "768"))  # 768 for Sentence Transformers, 3072 for OpenAI
    
    # ==================== LLM for Query Generation ====================
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")  # Latest Groq model
    
    # ==================== Search Configuration ====================
    DEFAULT_TOP_K: int = int(os.getenv("DEFAULT_TOP_K", "10"))
    MAX_TOP_K: int = int(os.getenv("MAX_TOP_K", "100"))
    LEXICAL_BOOST: float = float(os.getenv("LEXICAL_BOOST", "10.0"))
    SEMANTIC_WEIGHT: float = float(os.getenv("SEMANTIC_WEIGHT", "0.5"))
    
    # ==================== Chunking Configuration ====================
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "400"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "40"))
    
    # ==================== Indexing Configuration ====================
    INDEXING_BATCH_SIZE: int = int(os.getenv("INDEXING_BATCH_SIZE", "100"))  # Awards per batch (increased for better throughput)
    INDEXING_MAX_CONCURRENT: int = int(os.getenv("INDEXING_MAX_CONCURRENT", "1"))  # Max concurrent async calls (keep at 1 to avoid resource exhaustion)
    INDEXING_EMBEDDING_BATCH_SIZE: int = int(os.getenv("INDEXING_EMBEDDING_BATCH_SIZE", "64"))  # Chunks per embedding batch (increased for better throughput)
    INDEXING_CHUNKING_WORKERS: int = int(os.getenv("INDEXING_CHUNKING_WORKERS", "4"))  # Parallel chunking workers (increased for better throughput)
    
    # ==================== Logging ====================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/app.log")
    
    # ==================== API Configuration ====================
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    
    # ==================== Validation ====================
    def validate_vector_store(self) -> str:
        """Validate vector store choice"""
        if self.VECTOR_STORE not in ["pgvector", "qdrant"]:
            raise ValueError(f"VECTOR_STORE must be 'pgvector' or 'qdrant', got: {self.VECTOR_STORE}")
        return self.VECTOR_STORE
    
    def validate_chunking(self) -> tuple[int, int]:
        """Validate chunking parameters"""
        if self.CHUNK_OVERLAP >= self.CHUNK_SIZE:
            raise ValueError(f"CHUNK_OVERLAP ({self.CHUNK_OVERLAP}) must be less than CHUNK_SIZE ({self.CHUNK_SIZE})")
        if self.CHUNK_SIZE < 100:
            raise ValueError(f"CHUNK_SIZE ({self.CHUNK_SIZE}) should be at least 100 tokens")
        return self.CHUNK_SIZE, self.CHUNK_OVERLAP
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # Look for .env file in Search_Engine root (3 levels up from src/core/config.py)
        # src/core/config.py -> src/core -> src -> Search_Engine
        env_file_path = Path(__file__).parent.parent.parent / ".env"
        if env_file_path.exists():
            env_file = str(env_file_path)
        else:
            # Also check current directory
            current_dir_env = Path.cwd() / ".env"
            if current_dir_env.exists():
                env_file = str(current_dir_env)


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance (singleton pattern)
    
    Returns:
        Settings: Application settings instance
    """
    settings = Settings()
    # Validate on first load
    settings.validate_vector_store()
    settings.validate_chunking()
    return settings


# Global settings instance for easy import
settings = get_settings()
