# GraphMind: Healthcare Intake Memory System
## Production-Grade User-Centric Long-Term Memory with Hybrid RAG

### Project Overview

GraphMind is an AI-powered healthcare intake assistant that learns and remembers each patient independently over time. It constructs a personalized knowledge graph, uses hybrid retrieval (graph traversal + vector search), and generates contextual insights grounded in stored memories.

**Key Innovation:** Patient memories are stored as structured graphs with relationships, enabling pattern detection, contradiction resolution, and personalized recommendations—all while maintaining strict privacy/isolation between patients.

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Graph DB** | Neo4j | Patient memory graph (symptoms, meds, triggers, events) |
| **Vector DB** | Milvus | Semantic search over medical notes, summaries |
| **SQL DB** | PostgreSQL | User auth, audit logs, metadata |
| **NoSQL DB** | MongoDB | Flexible document storage (raw notes, API responses) |
| **Backend API** | FastAPI + Python 3.10+ | RESTful APIs with async support |
| **Frontend** | React 18 + TypeScript | Interactive mindmap visualization + chat UI |
| **LLM** | OpenAI/Anthropic API | Answer generation (healthcare-safe prompts) |
| **Orchestration** | Docker Compose | Multi-container local development |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    React Frontend                            │
│  (Mindmap Viz + Chat UI + Medical History Timeline)         │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP/WebSocket
┌──────────────────────┴──────────────────────────────────────┐
│                   FastAPI Backend                            │
│  ┌─────────────────────────────────────────────────────────┤
│  │ /memory/ingest    → Extract entities & write to graph    │
│  │ /memory/mindmap   → Fetch user's memory subgraph        │
│  │ /chat             → Retrieve + Generate answer           │
│  │ /health           → Service status check                 │
│  └─────────────────────────────────────────────────────────┤
└──────────┬──────────────────┬──────────────────┬────────────┘
           │                  │                  │
    ┌──────▼────┐     ┌───────▼────────┐  ┌────▼──────────┐
    │   Neo4j    │     │   PostgreSQL   │  │   MongoDB     │
    │            │     │                │  │               │
    │ Memory     │     │ User Auth      │  │ Raw Docs      │
    │ Graph      │     │ Audit Logs     │  │ LLM Calls     │
    │ Queries    │     │ Sessions       │  │ Vectors       │
    └──────┬─────┘     └────────────────┘  └───────────────┘
           │
    ┌──────▼──────────────────┐
    │   Milvus Vector DB      │
    │                         │
    │  Medical Note Vectors   │
    │  Semantic Search Index  │
    └────────────────────────┘
```

### Data Flow

```
User Input (Chat/Upload)
    ↓
[FastAPI] Ingestion Handler
    ↓
[LLM] Extract Entities: symptoms, medications, triggers, goals
    ↓
[Neo4j] Write Nodes & Edges:
    - Patient → HAS_SYMPTOM → Symptom (with timestamp, severity)
    - Patient → TAKES_MEDICATION → Drug (dosage, frequency)
    - Symptom → TRIGGERED_BY → Trigger (confidence score)
    - Event → HAPPENED_AT → Timeline
    ↓
[MongoDB] Store Raw Input (audit trail)
    ↓
[Milvus] Embed & Index Summary for vector search
    ↓
✓ Memory ingestion complete

---

User Query
    ↓
[Neo4j] Graph Traversal:
    - Find patient node
    - Retrieve 2-3 hop neighborhood
    - Filter by date/recency
    ↓
[Milvus] Vector Search:
    - Embed query
    - Similarity search over notes
    ↓
[Merge] Combine graph results + vector results
    ↓
[FastAPI] Format context pack
    ↓
[LLM] Generate answer with grounding
    ↓
Response with retrieval_time_ms + citations
```

---

## Directory Structure

```
graphmind-healthcare/
├── docker-compose.yml                 # Multi-container orchestration
├── requirements.txt                   # Python dependencies
├── .env.example                       # Environment variables template
├── README.md                          # Quick start guide
│
├── backend/
│   ├── main.py                       # FastAPI app entry point
│   ├── config.py                     # Configuration & secrets
│   ├── models.py                     # Pydantic schemas
│   ├── database.py                   # DB connections (Neo4j, Postgres, Mongo, Milvus)
│   │
│   ├── routes/
│   │   ├── memory.py                 # POST /memory/ingest, GET /memory/mindmap
│   │   ├── chat.py                   # POST /chat
│   │   ├── health.py                 # GET /health
│   │   └── auth.py                   # User registration/login
│   │
│   ├── services/
│   │   ├── ingestion.py              # Entity extraction & graph writing
│   │   ├── retrieval.py              # Hybrid retrieval (graph + vector)
│   │   ├── generation.py             # LLM answer generation
│   │   └── llm_client.py             # Anthropic/OpenAI client
│   │
│   ├── graph/
│   │   ├── schema.py                 # Neo4j graph data model
│   │   ├── queries.py                # Reusable Cypher queries
│   │   └── traversal.py              # Advanced graph traversal logic
│   │
│   └── utils/
│       ├── embeddings.py             # Vector embedding helpers
│       ├── time_utils.py             # Timestamp & recency logic
│       └── audit.py                  # Audit logging
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   │
│   ├── src/
│   │   ├── App.tsx                   # Main app
│   │   ├── index.css                 # Global styles
│   │   │
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx         # Home page
│   │   │   ├── PatientIntake.tsx     # Input form
│   │   │   └── ChatInterface.tsx     # Q&A interface
│   │   │
│   │   ├── components/
│   │   │   ├── Mindmap.tsx           # Graph visualization
│   │   │   ├── ChatBox.tsx           # Chat messages
│   │   │   ├── Timeline.tsx          # Medical history timeline
│   │   │   ├── RetrievalPanel.tsx    # Show retrieval evidence
│   │   │   └── PatientSelector.tsx   # Multi-patient support
│   │   │
│   │   ├── hooks/
│   │   │   ├── useAPI.ts             # API client hook
│   │   │   ├── useMindmap.ts         # Graph data fetching
│   │   │   └── useChat.ts            # Chat state management
│   │   │
│   │   └── utils/
│   │       ├── api.ts                # API client
│   │       ├── formatting.ts         # UI helpers
│   │       └── d3-graph.ts           # D3.js graph rendering
│
├── tests/
│   ├── test_ingestion.py
│   ├── test_retrieval.py
│   ├── test_generation.py
│   ├── test_isolation.py             # User isolation tests
│   └── test_performance.py           # Retrieval time benchmarks
│
└── docs/
    ├── API.md                        # OpenAPI documentation
    ├── SCHEMA.md                     # Graph & DB schema
    ├── EXAMPLES.md                   # Usage examples
    └── ARCHITECTURE.md               # Detailed design decisions
```

---

## Core Concepts

### 1. Graph Data Model (Neo4j)

**Nodes:**
- `User`: { user_id, name, email, created_at }
- `Symptom`: { name, severity, duration, onset_date }
- `Medication`: { name, dosage, frequency, start_date }
- `Trigger`: { name, description, confidence_score }
- `Event`: { description, date, type, source }
- `Goal`: { description, status, target_date }
- `Allergy`: { name, reaction, severity }
- `Lifestyle`: { category, detail, frequency }

**Relationships:**
- `(User) -[HAS_SYMPTOM {timestamp, severity, status}]-> (Symptom)`
- `(User) -[TAKES_MEDICATION {dosage, frequency, start_date}]-> (Medication)`
- `(Symptom) -[TRIGGERED_BY {confidence, times_observed}]-> (Trigger)`
- `(Event) -[HAPPENED_AT {date}]-> (Timeline)`
- `(User) -[HAS_ALLERGY {severity}]-> (Allergy)`
- `(User) -[WORKS_ON {status, priority}]-> (Goal)`
- `(User) -[HAS_LIFESTYLE {frequency}]-> (Lifestyle)`

### 2. Ingestion Pipeline

**Input:** "I've been having headaches 3x/week for 2 months, usually triggered by stress. Also started metformin last month."

**Processing:**
1. **Entity Extraction (LLM)** → Identify: Symptom(headache), Trigger(stress), Medication(metformin)
2. **Relationship Inference** → Build edges with confidence scores
3. **Temporal Tracking** → Add timestamps, recency
4. **Graph Writing** → Create nodes/edges in Neo4j
5. **Vector Indexing** → Embed summary in Milvus
6. **Audit Logging** → Store in MongoDB + PostgreSQL

### 3. Hybrid Retrieval Strategy

**User asks:** "What were my recent symptoms and what caused them?"

**Graph Query (Fast):**
```cypher
MATCH (user:User {user_id: $user_id})
OPTIONAL MATCH (user)-[r:HAS_SYMPTOM {timestamp: $recent}]->(symptom)
OPTIONAL MATCH (symptom)-[tr:TRIGGERED_BY]->(trigger)
RETURN symptom, trigger, r.timestamp, tr.confidence
LIMIT 10
```

**Vector Search (Semantic):**
```
Embed: "What were my recent symptoms and what caused them?"
Search Milvus for similar notes
Return top-5 similar medical summaries
```

**Merge & Rank:**
- Graph results: high precision, structured
- Vector results: catch nuances, paraphrasing
- Combine with recency boost
- Return top-3 unique pieces of evidence

### 4. Answer Generation

**System Prompt (Healthcare-Safe):**
```
You are a healthcare intake assistant. Your role is to:
1. Summarize patient memories retrieved from the database
2. Identify patterns (e.g., "Your headaches seem to spike on Mondays")
3. Suggest next steps (e.g., "Consider tracking caffeine intake vs. headaches")
4. NEVER diagnose or prescribe—only reflect stored information
5. Always cite sources: "Based on your entry on {date}..."

STRICT RULES:
- Do NOT provide medical diagnosis
- Do NOT recommend specific medications
- Do NOT replace a healthcare provider
- Flag any concerning patterns for provider review
- Be empathetic and conversational
```

---

## Setup Instructions (Local Development)

### Prerequisites
- Docker & Docker Compose (for easy multi-container setup)
- OR manually install:
  - Python 3.10+
  - Node.js 18+
  - Neo4j Community Edition
  - PostgreSQL 14+
  - MongoDB 5+
  - Milvus 2.2+

### Option A: Docker Compose (Recommended)

```bash
# 1. Clone repo
git clone https://github.com/yourusername/graphmind-healthcare.git
cd graphmind-healthcare

# 2. Create .env file
cp .env.example .env
# Edit .env with your LLM API keys

# 3. Start all services
docker-compose up -d

# 4. Wait for services to be ready (~30 seconds)
docker-compose logs -f backend

# 5. Backend ready at http://localhost:8000
# 6. Frontend ready at http://localhost:3000
```

### Option B: Local Installation

```bash
# Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r ../requirements.txt

# Start backend
python main.py
# Runs on http://localhost:8000

# Frontend setup (new terminal)
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
```

### Services Status

Check all services are running:
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "services": {
    "neo4j": "connected",
    "postgres": "connected",
    "mongodb": "connected",
    "milvus": "connected",
    "llm": "available"
  }
}
```

---

## API Quick Reference

### 1. Ingest Memory
```bash
curl -X POST http://localhost:8000/memory/ingest \
  -H "Content-Type: application/json" \
  -d {
    "user_id": "patient_001",
    "text": "I've been having headaches 3x/week, triggered by stress",
    "source_type": "intake_form"
  }
```

### 2. Fetch Mindmap
```bash
curl http://localhost:8000/memory/mindmap?user_id=patient_001
```

### 3. Chat Query
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d {
    "user_id": "patient_001",
    "query": "What patterns do you see in my symptoms?"
  }
```

### 4. Health Check
```bash
curl http://localhost:8000/health
```

---

## Performance Benchmarks (Goals)

| Operation | Target | Notes |
|-----------|--------|-------|
| Memory Ingestion | <500ms | Extract, write to Neo4j, vector embed, audit log |
| Graph Retrieval | <50ms | 2-3 hop traversal, top-10 results |
| Vector Search | <100ms | Milvus similarity search over 10k+ docs |
| Hybrid Merge | <20ms | Combine, deduplicate, rank results |
| **Total RAG Time** | **<200ms** | Retrieval only (excludes LLM generation) |
| Answer Generation | 2-3s | LLM API call |

**Optimization tactics:**
- Connection pooling for DB clients
- Cypher query caching
- Vector index optimization
- Pagination for large result sets

---

## Deliverables Checklist

- [ ] GitHub repo with clean code & documentation
- [ ] Docker Compose for one-command setup
- [ ] Neo4j graph schema & sample Cypher queries
- [ ] API documentation (Swagger at `/docs`)
- [ ] React frontend with mindmap visualization
- [ ] Performance monitoring dashboard
- [ ] Comprehensive test suite (unit + integration)
- [ ] Demo video (3-5 min) showing:
  - [ ] Memory ingestion from patient input
  - [ ] Interactive mindmap visualization
  - [ ] Hybrid retrieval with timing
  - [ ] Chat interface with grounded answers
- [ ] Architecture & design decision docs
- [ ] Stretch goals (optional):
  - [ ] Sub-100ms retrieval time
  - [ ] Memory decay/forgetting
  - [ ] Contradiction detection
  - [ ] Multi-modal memory (documents, images)
  - [ ] Streaming responses

---

## Next Steps

1. **Start with backend core:**
   - `backend/main.py` → FastAPI app
   - `backend/database.py` → DB connections
   - `backend/graph/schema.py` → Neo4j model

2. **Build ingestion pipeline:**
   - `backend/services/ingestion.py` → Extract entities
   - LLM prompt engineering for healthcare domain

3. **Implement retrieval:**
   - `backend/services/retrieval.py` → Hybrid retrieval
   - Performance profiling & optimization

4. **Create frontend:**
   - React components for chat, mindmap, timeline
   - Real-time connection to backend

5. **Add production features:**
   - User authentication & isolation
   - Audit logging & compliance
   - Error handling & monitoring

---

**Estimated Timeline:**
- Week 1-2: Backend core + ingestion
- Week 2-3: Retrieval + answer generation
- Week 3-4: Frontend UI + visualization
- Week 4-5: Testing + optimization
- Week 5-6: Documentation + demo prep
- Week 6-8: Refinement + stretch goals

Good luck! This is a genuinely impressive project. 🚀

