"""
Memory routes
Handles memory ingestion and mindmap retrieval
"""

import logging
import time
from fastapi import APIRouter, Depends, HTTPException

from database import DatabaseManager
from models import (
    MemoryIngestionRequest,
    MemoryIngestionResponse,
    MindmapResponse,
    NodeData,
    EdgeData,
)
from services.ingestion import IngestionService
from services.retrieval import RetrievalService
from services.llm_client import LLMClient, EmbeddingService
from utils.embeddings import AuditLogger

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Memory"])


def get_db() -> DatabaseManager:
    """Get database manager"""
    return __import__('main').db_manager


def get_ingestion_service(db: DatabaseManager = Depends(get_db)) -> IngestionService:
    """Get ingestion service"""
    llm = LLMClient()
    embeddings = EmbeddingService()
    return IngestionService(db, llm, embeddings)


def get_retrieval_service(db: DatabaseManager = Depends(get_db)) -> RetrievalService:
    """Get retrieval service"""
    embeddings = EmbeddingService()
    return RetrievalService(db, embeddings)


def get_audit_logger(db: DatabaseManager = Depends(get_db)) -> AuditLogger:
    """Get audit logger"""
    return AuditLogger(db)


@router.post("/ingest", response_model=MemoryIngestionResponse)
async def ingest_memory(
    request: MemoryIngestionRequest,
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
):
    """
    Ingest new patient memory from intake form or chat.
    
    - Extracts entities (symptoms, medications, triggers, etc.)
    - Creates/updates graph nodes and relationships
    - Embeds and indexes text for semantic search
    - Logs to audit trail
    """
    
    ingest_start = time.time()
    
    try:
        logger.info(f"Ingesting memory for user {request.user_id}")
        
        # Validate user exists (would check auth in production)
        # For now, allow any user_id
        
        # Perform ingestion
        nodes_created, edges_created, nodes_data, edges_data = await ingestion_service.ingest(
            request
        )
        
        ingest_time = (time.time() - ingest_start) * 1000
        
        # Log to audit trail
        await audit_logger.log_event(
            user_id=request.user_id,
            event_type="memory_ingest",
            action="create",
            resource="memory",
            status="success",
            details={
                "source_type": request.source_type,
                "nodes_created": nodes_created,
                "edges_created": edges_created,
            },
            duration_ms=ingest_time,
        )
        
        return MemoryIngestionResponse(
            success=True,
            user_id=request.user_id,
            nodes_created=nodes_created,
            edges_created=edges_created,
            nodes=nodes_data,
            edges=edges_data,
            message=f"Successfully ingested memory: {nodes_created} entities created",
        )
    
    except Exception as e:
        logger.error(f"Memory ingestion failed: {e}", exc_info=True)
        
        await audit_logger.log_event(
            user_id=request.user_id,
            event_type="memory_ingest",
            action="create",
            resource="memory",
            status="failure",
            error=str(e),
        )
        
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.get("/mindmap", response_model=MindmapResponse)
async def get_mindmap(
    user_id: str,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
):
    """
    Retrieve user's memory mindmap for visualization.
    
    Returns graph structure with nodes and edges representing:
    - Patient's symptoms, medications, triggers
    - Relationships and patterns
    - Timeline and recency information
    """
    
    try:
        logger.info(f"Retrieving mindmap for user {user_id}")
        
        # Get user's memory graph
        mindmap_data = await retrieval_service.get_user_mindmap(user_id)
        
        # Convert to response format
        nodes = []
        for node_data in mindmap_data.get("nodes", []):
            nodes.append({
                "id": node_data["id"],
                "label": node_data["label"],
                "type": node_data["type"],
                "properties": node_data.get("properties", {}),
                "size": 15 if node_data["type"] == "User" else 10,
            })
        
        edges = []
        for edge_data in mindmap_data.get("edges", []):
            edges.append({
                "source": edge_data["source"],
                "target": edge_data["target"],
                "label": edge_data["label"],
                "relationship_type": edge_data["label"],
                "weight": 1.0,
            })
        
        # Log access
        await audit_logger.log_event(
            user_id=user_id,
            event_type="mindmap_retrieval",
            action="read",
            resource="mindmap",
            status="success",
        )
        
        return MindmapResponse(
            user_id=user_id,
            nodes=nodes,
            edges=edges,
            stats=mindmap_data.get("stats", {}),
        )
    
    except Exception as e:
        logger.error(f"Mindmap retrieval failed: {e}", exc_info=True)
        
        raise HTTPException(status_code=500, detail=f"Failed to retrieve mindmap: {str(e)}")


@router.get("/mindmap/{user_id}/stats")
async def get_mindmap_stats(
    user_id: str,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
):
    """Get statistics about user's memory graph"""
    try:
        mindmap_data = await retrieval_service.get_user_mindmap(user_id)
        return {
            "user_id": user_id,
            "total_nodes": len(mindmap_data.get("nodes", [])),
            "total_edges": len(mindmap_data.get("edges", [])),
            "node_types": _count_node_types(mindmap_data.get("nodes", [])),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _count_node_types(nodes: list) -> dict:
    """Count nodes by type"""
    counts = {}
    for node in nodes:
        node_type = node.get("type", "Unknown")
        counts[node_type] = counts.get(node_type, 0) + 1
    return counts
