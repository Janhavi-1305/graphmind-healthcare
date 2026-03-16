"""
GraphMind Healthcare Intake Memory System
Main FastAPI Application Entry Point

Features:
- User-isolated memory graph (Neo4j)
- Hybrid retrieval (graph traversal + vector search)
- LLM-grounded answer generation
- Healthcare-safe prompt engineering
- Performance monitoring & audit logging
"""

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

# Internal imports (we'll create these)
from config import settings
from database import DatabaseManager
from models import (
    HealthStatus, MemoryIngestionRequest, MemoryIngestionResponse,
    ChatRequest, ChatResponse, MindmapResponse
)
from routes import memory, chat, health, auth
from utils.embeddings import AuditLogger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
db_manager: Optional[DatabaseManager] = None
audit_logger: Optional[AuditLogger] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    Manages database connections and service initialization.
    """
    global db_manager, audit_logger
    
    logger.info("=" * 60)
    logger.info("GraphMind Healthcare Intake Memory System - Startup")
    logger.info("=" * 60)
    
    # Initialize database manager
    try:
        logger.info("Initializing database connections...")
        db_manager = DatabaseManager(
            neo4j_uri=settings.NEO4J_URI,
            neo4j_user=settings.NEO4J_USER,
            neo4j_password=settings.NEO4J_PASSWORD,
            postgres_url=settings.DATABASE_URL,
            mongo_url=settings.MONGODB_URL,
            milvus_host=settings.MILVUS_HOST,
            milvus_port=settings.MILVUS_PORT,
        )
        await db_manager.initialize()
        logger.info("✓ Database connections established")
        
        # Initialize audit logger
        audit_logger = AuditLogger(db_manager)
        logger.info("✓ Audit logger initialized")
        
        # Create schema if needed
        logger.info("Initializing graph schema...")
        await db_manager.create_schema()
        logger.info("✓ Graph schema ready")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    logger.info("✓ All services initialized successfully")
    logger.info("=" * 60)
    
    yield  # Application runs here
    
    # Shutdown
    logger.info("Shutting down services...")
    if db_manager:
        await db_manager.close()
    logger.info("✓ Services shut down gracefully")


# Create FastAPI app
app = FastAPI(
    title="GraphMind Healthcare API",
    description="User-centric long-term memory system with hybrid RAG for healthcare intake",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Add CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Dependency Injection
# ============================================================================

def get_db() -> DatabaseManager:
    """Dependency for getting database manager"""
    if db_manager is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return db_manager


def get_audit_logger() -> AuditLogger:
    """Dependency for getting audit logger"""
    if audit_logger is None:
        raise HTTPException(status_code=503, detail="Audit logger not initialized")
    return audit_logger


# ============================================================================
# Root Routes
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Health check and API info"""
    return {
        "name": "GraphMind Healthcare Intake Memory",
        "version": "1.0.0",
        "status": "running",
        "docs": "http://localhost:8000/docs",
        "endpoints": {
            "health": "GET /health",
            "auth": "POST /auth/register, POST /auth/login",
            "memory": "POST /memory/ingest, GET /memory/mindmap",
            "chat": "POST /chat",
        }
    }


# ============================================================================
# Service Routes
# ============================================================================

# Include routers
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(memory.router, prefix="/memory", tags=["Memory"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "timestamp": datetime.now().isoformat(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Catch-all exception handler for unhandled errors"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.DEBUG else "An error occurred",
            "timestamp": datetime.now().isoformat(),
        },
    )


# ============================================================================
# Request/Response Logging Middleware
# ============================================================================

@app.middleware("http")
async def log_requests(request, call_next):
    """Log all HTTP requests and responses"""
    import time
    
    # Skip logging for health checks to reduce noise
    if request.url.path == "/health":
        return await call_next(request)
    
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.3f}s"
    )
    
    return response


# ============================================================================
# Startup Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info("FastAPI application started")
    if settings.DEBUG:
        logger.info("DEBUG mode enabled")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("FastAPI application shutting down")


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    # Determine port from environment or use default
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting server on {host}:{port}")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=settings.DEBUG,
        log_level="info",
    )
