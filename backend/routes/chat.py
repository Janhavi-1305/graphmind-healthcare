"""
Chat routes
Handles patient queries with hybrid retrieval and grounded answer generation
"""

import logging
import time
from fastapi import APIRouter, Depends, HTTPException

from database import DatabaseManager
from models import ChatRequest, ChatResponse
from services.retrieval import RetrievalService
from services.generation import GenerationService
from services.llm_client import EmbeddingService, LLMClient
from utils.embeddings import AuditLogger, PerformanceMonitor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])


def get_db() -> DatabaseManager:
    """Get database manager"""
    return __import__('main').db_manager


def get_retrieval_service(db: DatabaseManager = Depends(get_db)) -> RetrievalService:
    """Get retrieval service"""
    embeddings = EmbeddingService()
    return RetrievalService(db, embeddings)


def get_generation_service() -> GenerationService:
    """Get generation service"""
    llm = LLMClient()
    return GenerationService(llm)


def get_audit_logger(db: DatabaseManager = Depends(get_db)) -> AuditLogger:
    """Get audit logger"""
    return AuditLogger(db)


def get_performance_monitor(db: DatabaseManager = Depends(get_db)) -> PerformanceMonitor:
    """Get performance monitor"""
    return PerformanceMonitor(db)


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    generation_service: GenerationService = Depends(get_generation_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
    perf_monitor: PerformanceMonitor = Depends(get_performance_monitor),
):
    """
    Handle patient query with hybrid retrieval and grounded answer generation.
    
    Flow:
    1. Retrieve relevant memories (graph + vector search)
    2. Pack context from retrieved memories
    3. Generate answer grounded in context using LLM
    4. Return answer with citations and retrieval evidence
    """
    
    total_start = time.time()
    
    try:
        logger.info(f"Chat query from user {request.user_id}: {request.query[:60]}...")
        
        # Step 1: Hybrid retrieval
        retrieval_start = time.time()
        citations, retrieval_evidence, retrieval_time_ms = await retrieval_service.retrieve(
            user_id=request.user_id,
            query=request.query,
            top_k=request.context_window,
        )
        retrieval_duration = (time.time() - retrieval_start) * 1000
        
        logger.info(f"Retrieved {len(citations)} citations in {retrieval_time_ms:.2f}ms")
        
        # Step 2: Pack context
        context = _pack_context(citations)
        
        # Step 3: Generate answer
        gen_start = time.time()
        answer = await generation_service.generate_answer(
            query=request.query,
            context=context,
            retrieval_evidence=retrieval_evidence,
        )
        gen_duration = (time.time() - gen_start) * 1000
        
        logger.info(f"Generated answer in {gen_duration:.2f}ms")
        
        # Total time (excluding LLM call from RAG retrieval time)
        total_duration = (time.time() - total_start) * 1000
        
        # Build response
        response = ChatResponse(
            user_id=request.user_id,
            query=request.query,
            answer=answer,
            retrieval_time_ms=retrieval_time_ms,  # RAG retrieval only
            llm_generation_time_ms=gen_duration,
            total_time_ms=total_duration,
            memory_citations=citations,
            retrieval_evidence=retrieval_evidence,
            confidence_score=_calculate_confidence(citations),
        )
        
        # Log to audit trail
        await audit_logger.log_event(
            user_id=request.user_id,
            event_type="chat_query",
            action="read",
            resource="memory",
            status="success",
            details={
                "query": request.query,
                "citations": len(citations),
                "context_window": request.context_window,
            },
            duration_ms=total_duration,
        )
        
        # Log performance metric
        await perf_monitor.log_metric(
            endpoint="/chat",
            method="POST",
            status_code=200,
            total_time_ms=total_duration,
            retrieval_time_ms=retrieval_time_ms,
            llm_time_ms=gen_duration,
        )
        
        return response
    
    except Exception as e:
        logger.error(f"Chat query failed: {e}", exc_info=True)
        
        await audit_logger.log_event(
            user_id=request.user_id,
            event_type="chat_query",
            action="read",
            resource="memory",
            status="failure",
            error=str(e),
        )
        
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.post("/debug")
async def debug_chat(
    request: ChatRequest,
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
):
    """
    Debug endpoint that returns raw retrieval results without generation.
    Useful for testing and debugging the retrieval pipeline.
    """
    try:
        citations, evidence, retrieval_time = await retrieval_service.retrieve(
            user_id=request.user_id,
            query=request.query,
            top_k=request.context_window,
        )
        
        return {
            "query": request.query,
            "user_id": request.user_id,
            "retrieval_time_ms": retrieval_time,
            "evidence": evidence.dict(),
            "citations": [c.dict() for c in citations],
            "context": _pack_context(citations),
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _pack_context(citations) -> str:
    """Pack citations into readable context for LLM"""
    context_lines = []
    
    for i, citation in enumerate(citations, 1):
        context_lines.append(
            f"[{i}] {citation.node_type}: {citation.title}\n"
            f"    {citation.snippet}\n"
            f"    (Relevance: {citation.relevance_score:.0%})"
        )
    
    return "\n\n".join(context_lines)


def _calculate_confidence(citations) -> float:
    """Calculate overall confidence based on citations"""
    if not citations:
        return 0.0
    
    # Average relevance score of top 3 citations
    top_scores = [c.relevance_score for c in citations[:3]]
    return sum(top_scores) / len(top_scores) if top_scores else 0.0
