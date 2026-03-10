"""
Pydantic models for request/response validation and serialization
"""

from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator


# ============================================================================
# Enums
# ============================================================================

class SourceType(str, Enum):
    """Types of information sources"""
    INTAKE_FORM = "intake_form"
    CHAT = "chat"
    DOCUMENT = "document"
    MEDICAL_RECORD = "medical_record"
    USER_REPORTED = "user_reported"
    API = "api"


class SeverityLevel(str, Enum):
    """Severity levels for symptoms"""
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    CRITICAL = "critical"


class HealthStatus(str, Enum):
    """Service health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


# ============================================================================
# User & Authentication
# ============================================================================

class UserRegisterRequest(BaseModel):
    """User registration request"""
    email: str = Field(..., description="User email")
    password: str = Field(..., min_length=8, description="Password (min 8 chars)")
    full_name: str = Field(..., description="Full name")
    date_of_birth: Optional[str] = Field(None, description="Date of birth (YYYY-MM-DD)")

    @validator("email")
    def validate_email(cls, v):
        if "@" not in v:
            raise ValueError("Invalid email format")
        return v.lower()


class UserLoginRequest(BaseModel):
    """User login request"""
    email: str
    password: str


class UserResponse(BaseModel):
    """User data response"""
    user_id: str
    email: str
    full_name: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """JWT token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ============================================================================
# Memory Management
# ============================================================================

class SymptomData(BaseModel):
    """Symptom information"""
    name: str
    severity: Optional[SeverityLevel] = None
    duration: Optional[str] = None
    onset_date: Optional[str] = None
    notes: Optional[str] = None


class MedicationData(BaseModel):
    """Medication information"""
    name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    start_date: Optional[str] = None
    reason: Optional[str] = None


class TriggerData(BaseModel):
    """Trigger information"""
    name: str
    description: Optional[str] = None
    related_symptom: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)


class AllergyData(BaseModel):
    """Allergy information"""
    name: str
    reaction: str
    severity: SeverityLevel
    reaction_type: Optional[str] = None


class LifestyleData(BaseModel):
    """Lifestyle information"""
    category: str  # e.g., "exercise", "diet", "sleep", "stress"
    detail: str
    frequency: Optional[str] = None
    impact: Optional[str] = None


class GoalData(BaseModel):
    """Health goal"""
    description: str
    target_date: Optional[str] = None
    status: str = "active"
    priority: int = 3  # 1=highest, 5=lowest


class MemoryIngestionRequest(BaseModel):
    """Request to ingest new memory"""
    user_id: str = Field(..., description="User ID (owner of memory)")
    text: str = Field(..., min_length=10, description="Raw input text")
    source_type: SourceType = SourceType.USER_REPORTED
    metadata: Optional[Dict[str, Any]] = None
    
    # Optional structured data (if pre-extracted)
    symptoms: Optional[List[SymptomData]] = None
    medications: Optional[List[MedicationData]] = None
    triggers: Optional[List[TriggerData]] = None
    allergies: Optional[List[AllergyData]] = None
    lifestyle: Optional[List[LifestyleData]] = None
    goals: Optional[List[GoalData]] = None


class NodeData(BaseModel):
    """Graph node representation"""
    node_id: str
    node_type: str  # e.g., "Symptom", "Medication"
    label: str
    properties: Dict[str, Any]
    created_at: datetime
    last_updated: datetime


class EdgeData(BaseModel):
    """Graph edge representation"""
    source_id: str
    target_id: str
    relationship_type: str
    properties: Dict[str, Any]
    created_at: datetime


class MemoryIngestionResponse(BaseModel):
    """Response from memory ingestion"""
    success: bool
    user_id: str
    nodes_created: int
    edges_created: int
    nodes: List[NodeData] = []
    edges: List[EdgeData] = []
    timestamp: datetime = Field(default_factory=datetime.now)
    message: str = "Memory ingested successfully"


# ============================================================================
# Mindmap / Graph Visualization
# ============================================================================

class MindmapNode(BaseModel):
    """Node for mindmap visualization"""
    id: str
    label: str
    type: str
    properties: Dict[str, Any]
    size: int = 10


class MindmapEdge(BaseModel):
    """Edge for mindmap visualization"""
    source: str
    target: str
    label: str
    relationship_type: str
    weight: float = 1.0


class MindmapResponse(BaseModel):
    """Mindmap data for frontend visualization"""
    user_id: str
    nodes: List[MindmapNode]
    edges: List[MindmapEdge]
    stats: Dict[str, Any]
    generated_at: datetime = Field(default_factory=datetime.now)


# ============================================================================
# Chat & Retrieval
# ============================================================================

class Citation(BaseModel):
    """Citation for retrieved memory"""
    node_id: str
    node_type: str
    title: str
    snippet: str
    relevance_score: float = Field(ge=0, le=1)
    source_type: SourceType
    created_at: datetime


class RetrievalEvidence(BaseModel):
    """Evidence from retrieval process"""
    graph_results: int
    vector_results: int
    merged_results: int
    retrieval_time_ms: float
    top_results: List[Citation]


class ChatRequest(BaseModel):
    """Chat/query request"""
    user_id: str = Field(..., description="User ID (patient)")
    query: str = Field(..., min_length=5, description="Question or query")
    context_window: int = Field(default=5, ge=1, le=20, description="Number of memory items to retrieve")
    include_retrieval_evidence: bool = True


class ChatResponse(BaseModel):
    """Chat response with memory citations"""
    user_id: str
    query: str
    answer: str
    retrieval_time_ms: float = Field(..., description="RAG retrieval time (graph + vector + merge)")
    llm_generation_time_ms: float
    total_time_ms: float
    memory_citations: List[Citation]
    retrieval_evidence: RetrievalEvidence
    confidence_score: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "patient_001",
                "query": "What are my recent symptoms?",
                "answer": "Based on your recent intake, you reported headaches 3x per week...",
                "retrieval_time_ms": 145.3,
                "llm_generation_time_ms": 2340.5,
                "total_time_ms": 2485.8,
                "memory_citations": [
                    {
                        "node_id": "symptom_123",
                        "node_type": "Symptom",
                        "title": "Headaches",
                        "snippet": "Experiencing headaches 3x per week for 2 months...",
                        "relevance_score": 0.95,
                        "source_type": "intake_form",
                        "created_at": "2024-01-15T10:30:00Z"
                    }
                ],
                "retrieval_evidence": {
                    "graph_results": 3,
                    "vector_results": 2,
                    "merged_results": 5,
                    "retrieval_time_ms": 145.3,
                    "top_results": []
                }
            }
        }


# ============================================================================
# Health & Monitoring
# ============================================================================

class ServiceStatus(BaseModel):
    """Status of a service"""
    name: str
    status: HealthStatus
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: HealthStatus
    timestamp: datetime = Field(default_factory=datetime.now)
    services: Dict[str, ServiceStatus]
    uptime_seconds: float
    version: str


# ============================================================================
# Audit & Logging
# ============================================================================

class AuditLogEntry(BaseModel):
    """Audit log entry"""
    event_id: str
    user_id: str
    event_type: str  # e.g., "memory_ingest", "query", "deletion"
    resource: str  # e.g., "memory", "chat"
    action: str  # e.g., "create", "read", "update", "delete"
    status: str  # "success", "failure"
    timestamp: datetime
    details: Dict[str, Any] = {}
    error: Optional[str] = None
    duration_ms: Optional[float] = None


# ============================================================================
# Performance Monitoring
# ============================================================================

class PerformanceMetrics(BaseModel):
    """Performance metrics for a request"""
    request_id: str
    endpoint: str
    method: str
    status_code: int
    total_time_ms: float
    db_time_ms: float
    llm_time_ms: float
    retrieval_time_ms: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class PerformanceSummary(BaseModel):
    """Summary of performance metrics"""
    total_requests: int
    avg_time_ms: float
    p50_time_ms: float
    p95_time_ms: float
    p99_time_ms: float
    slow_requests: int
    errors: int
