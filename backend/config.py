"""
Configuration module for GraphMind Healthcare System
Loads settings from environment variables with sensible defaults
"""

import os
from typing import List, Optional
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    DEBUG: bool = Field(default=False, env="DEBUG")
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    
    # API Configuration
    API_TITLE: str = "GraphMind Healthcare"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = "User-centric long-term memory with hybrid RAG"
    
    # Server
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8000, env="PORT")
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    
    # Database: Neo4j (Graph DB)
    NEO4J_URI: str = Field(
        default="neo4j://localhost:7687",
        env="NEO4J_URI",
        description="Neo4j connection URI"
    )
    NEO4J_USER: str = Field(default="neo4j", env="NEO4J_USER")
    NEO4J_PASSWORD: str = Field(default="password", env="NEO4J_PASSWORD")
    
    # Database: PostgreSQL (SQL)
    DATABASE_URL: str = Field(
        default="postgresql://user:password@localhost:5432/graphmind",
        env="DATABASE_URL",
        description="PostgreSQL connection string"
    )
    
    # Database: MongoDB (NoSQL)
    MONGODB_URL: str = Field(
        default="mongodb://localhost:27017",
        env="MONGODB_URL",
        description="MongoDB connection string"
    )
    MONGODB_DB: str = Field(default="graphmind", env="MONGODB_DB")
    
    # Database: Milvus (Vector DB)
    MILVUS_HOST: str = Field(default="localhost", env="MILVUS_HOST")
    MILVUS_PORT: int = Field(default=19530, env="MILVUS_PORT")
    MILVUS_ALIAS: str = "default"
    
    # LLM Configuration
    LLM_PROVIDER: str = Field(default="anthropic", env="LLM_PROVIDER")
    ANTHROPIC_API_KEY: str = Field(default="", env="ANTHROPIC_API_KEY")
    OPENAI_API_KEY: str = Field(default="", env="OPENAI_API_KEY")
    LLM_MODEL: str = Field(default="claude-3-5-sonnet-20241022", env="LLM_MODEL")
    LLM_TEMPERATURE: float = Field(default=0.7, env="LLM_TEMPERATURE")
    LLM_MAX_TOKENS: int = Field(default=500, env="LLM_MAX_TOKENS")
    
    # Embeddings Configuration
    EMBEDDING_MODEL: str = Field(
        default="all-MiniLM-L6-v2",
        env="EMBEDDING_MODEL",
        description="Sentence-transformers model name"
    )
    EMBEDDING_DIMENSION: int = Field(default=384, env="EMBEDDING_DIMENSION")
    
    # Retrieval Configuration
    RETRIEVAL_TOP_K: int = Field(default=5, env="RETRIEVAL_TOP_K")
    GRAPH_HOP_LIMIT: int = Field(default=3, env="GRAPH_HOP_LIMIT")
    VECTOR_SEARCH_TOP_K: int = Field(default=5, env="VECTOR_SEARCH_TOP_K")
    HYBRID_RETRIEVAL_ALPHA: float = Field(
        default=0.5,
        env="HYBRID_RETRIEVAL_ALPHA",
        description="Weight for vector score in hybrid retrieval"
    )
    
    # Performance & Monitoring
    ENABLE_PERFORMANCE_MONITORING: bool = Field(
        default=True,
        env="ENABLE_PERFORMANCE_MONITORING"
    )
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    CACHE_EMBEDDINGS: bool = Field(default=True, env="CACHE_EMBEDDINGS")
    
    # Security
    JWT_SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        env="JWT_SECRET_KEY"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    
    # Memory Management
    MEMORY_DECAY_ENABLED: bool = Field(default=False, env="MEMORY_DECAY_ENABLED")
    MEMORY_DECAY_DAYS: int = Field(default=90, env="MEMORY_DECAY_DAYS")
    MAX_INGEST_PER_USER_PER_DAY: int = Field(default=100, env="MAX_INGEST_PER_USER_PER_DAY")
    
    # Healthcare-Specific
    REQUIRE_HIPAA_COMPLIANCE: bool = Field(default=True, env="REQUIRE_HIPAA_COMPLIANCE")
    HEALTHCARE_SAFETY_CHECKS: bool = Field(default=True, env="HEALTHCARE_SAFETY_CHECKS")
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Load settings
settings = Settings()


# ============================================================================
# Settings Validation
# ============================================================================

def validate_settings() -> bool:
    """Validate critical settings are configured"""
    errors = []
    
    # Check LLM configuration
    if settings.LLM_PROVIDER == "anthropic" and not settings.ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY not set")
    elif settings.LLM_PROVIDER == "openai" and not settings.OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY not set")
    
    # Check database URLs
    if "localhost" in settings.DATABASE_URL and settings.ENVIRONMENT == "production":
        errors.append("Using localhost database in production - consider using cloud database")
    
    if errors:
        print("⚠️  Configuration Warnings:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    return True


# Print loaded settings on startup (if DEBUG)
if settings.DEBUG:
    print("\n" + "=" * 60)
    print("Loaded Configuration:")
    print("=" * 60)
    print(f"Environment: {settings.ENVIRONMENT}")
    print(f"LLM Provider: {settings.LLM_PROVIDER}")
    print(f"Neo4j: {settings.NEO4J_URI}")
    print(f"PostgreSQL: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'configured'}")
    print(f"MongoDB: {settings.MONGODB_URL}")
    print(f"Milvus: {settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
    print("=" * 60 + "\n")
