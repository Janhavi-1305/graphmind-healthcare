@"
  # System Architecture
  ## Graph Data Model
  - User → Symptom, Medication, Trigger, Allergy, Goal, Lifestyle
  ## Databases
  - **Neo4j**: Memory graph (relationships)
  - **PostgreSQL**: User auth, audit logs
  - **MongoDB**: Raw documents, metrics
  - **Milvus**: Vector embeddings
  ## Services
  - Ingestion: Entity extraction → Graph writing
  - Retrieval: Graph query + Vector search → Merge & rank
  - Generation: LLM answer generation
  ## API Endpoints
  - POST /memory/ingest
  - GET /memory/mindmap
  - POST /chat
  - GET /health
  "@ | Out-File -Encoding UTF8 docs\ARCHITECTURE.md