"""
Database Manager
Handles connections to all databases:
- Neo4j (graph database for memory)
- PostgreSQL (user data, audit logs)
- MongoDB (raw documents, flexible storage)
- Milvus (vector embeddings for semantic search)
"""

import asyncio
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime
import uuid

# Neo4j
from neo4j import AsyncDriver, AsyncSession
from neo4j import asyncio as neo4j_asyncio

# PostgreSQL
import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession as SQLSession
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

# MongoDB
from motor.motor_asyncio import AsyncClient, AsyncDatabase
import pymongo

# Milvus
from pymilvus import (
    connections,
    Collection,
    FieldSchema,
    CollectionSchema,
    DataType,
)

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Unified database manager for all storage systems"""
    
    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        postgres_url: str,
        mongo_url: str,
        milvus_host: str,
        milvus_port: int,
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.postgres_url = postgres_url
        self.mongo_url = mongo_url
        self.milvus_host = milvus_host
        self.milvus_port = milvus_port
        
        # Drivers (will be initialized in initialize())
        self.neo4j_driver: Optional[AsyncDriver] = None
        self.postgres_engine: Optional[AsyncEngine] = None
        self.postgres_pool: Optional[asyncpg.Pool] = None
        self.mongo_client: Optional[AsyncClient] = None
        self.mongo_db: Optional[AsyncDatabase] = None
        self.milvus_collection: Optional[Collection] = None
        
        # Connection pools
        self._connections_initialized = False
    
    async def initialize(self):
        """Initialize all database connections"""
        try:
            logger.info("Initializing database connections...")
            
            # Initialize Neo4j
            await self._init_neo4j()
            logger.info("✓ Neo4j connected")
            
            # Initialize PostgreSQL
            await self._init_postgres()
            logger.info("✓ PostgreSQL connected")
            
            # Initialize MongoDB
            await self._init_mongodb()
            logger.info("✓ MongoDB connected")
            
            # Initialize Milvus
            self._init_milvus()
            logger.info("✓ Milvus connected")
            
            self._connections_initialized = True
            logger.info("✓ All database connections initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize databases: {e}")
            raise
    
    # ========================================================================
    # Neo4j (Graph Database)
    # ========================================================================
    
    async def _init_neo4j(self):
        """Initialize Neo4j connection"""
        self.neo4j_driver = neo4j_asyncio.AsyncGraphDatabase.driver(
            self.neo4j_uri,
            auth=(self.neo4j_user, self.neo4j_password),
            max_connection_pool_size=50,
        )
        # Test connection
        async with self.neo4j_driver.session() as session:
            await session.run("RETURN 1")
    
    async def get_neo4j_session(self) -> AsyncSession:
        """Get Neo4j session"""
        if self.neo4j_driver is None:
            raise RuntimeError("Neo4j not initialized")
        return self.neo4j_driver.session()
    
    async def execute_cypher(self, query: str, params: Dict = None) -> List[Dict]:
        """Execute a Cypher query and return results"""
        if params is None:
            params = {}
        
        async with self.neo4j_driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()
            return records
    
    # ========================================================================
    # PostgreSQL (Relational Database)
    # ========================================================================
    
    async def _init_postgres(self):
        """Initialize PostgreSQL connection"""
        # Use asyncpg for direct connection pool
        self.postgres_pool = await asyncpg.create_pool(
            self.postgres_url,
            min_size=5,
            max_size=20,
            command_timeout=60,
        )
    
    async def get_postgres_connection(self):
        """Get PostgreSQL connection from pool"""
        if self.postgres_pool is None:
            raise RuntimeError("PostgreSQL not initialized")
        return await self.postgres_pool.acquire()
    
    async def execute_sql(self, query: str, *args) -> List[Dict]:
        """Execute SQL query"""
        async with self.postgres_pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]
    
    # ========================================================================
    # MongoDB (Document Database)
    # ========================================================================
    
    async def _init_mongodb(self):
        """Initialize MongoDB connection"""
        self.mongo_client = AsyncClient(self.mongo_url)
        self.mongo_db = self.mongo_client.graphmind
        
        # Test connection
        await self.mongo_client.admin.command("ping")
    
    async def get_mongo_collection(self, collection_name: str):
        """Get MongoDB collection"""
        if self.mongo_db is None:
            raise RuntimeError("MongoDB not initialized")
        return self.mongo_db[collection_name]
    
    async def insert_document(self, collection_name: str, document: Dict):
        """Insert document into MongoDB"""
        collection = await self.get_mongo_collection(collection_name)
        result = await collection.insert_one(document)
        return str(result.inserted_id)
    
    async def find_documents(self, collection_name: str, query: Dict) -> List[Dict]:
        """Find documents in MongoDB"""
        collection = await self.get_mongo_collection(collection_name)
        cursor = collection.find(query)
        documents = await cursor.to_list(length=None)
        return documents
    
    # ========================================================================
    # Milvus (Vector Database)
    # ========================================================================
    
    def _init_milvus(self):
        """Initialize Milvus connection"""
        connections.connect(
            "default",
            host=self.milvus_host,
            port=self.milvus_port,
        )
        logger.info(f"Connected to Milvus at {self.milvus_host}:{self.milvus_port}")
    
    def create_milvus_collection(
        self,
        collection_name: str,
        dimension: int = 384,
    ):
        """Create a Milvus collection for embeddings"""
        try:
            # Check if collection exists
            from pymilvus import utility
            if utility.has_collection(collection_name):
                logger.info(f"Collection {collection_name} already exists")
                return Collection(collection_name)
            
            # Define schema
            fields = [
                FieldSchema(
                    name="id",
                    dtype=DataType.VARCHAR,
                    is_primary=True,
                    max_length=100,
                ),
                FieldSchema(
                    name="user_id",
                    dtype=DataType.VARCHAR,
                    max_length=100,
                ),
                FieldSchema(
                    name="embedding",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=dimension,
                ),
                FieldSchema(
                    name="text",
                    dtype=DataType.VARCHAR,
                    max_length=1000,
                ),
                FieldSchema(
                    name="metadata",
                    dtype=DataType.VARCHAR,
                    max_length=500,
                ),
                FieldSchema(
                    name="timestamp",
                    dtype=DataType.INT64,
                ),
            ]
            
            schema = CollectionSchema(fields=fields, description="Medical notes embeddings")
            
            # Create collection
            collection = Collection(collection_name, schema=schema)
            
            # Create index
            collection.create_index(
                field_name="embedding",
                index_params={"index_type": "IVF_FLAT", "metric_type": "L2", "params": {"nlist": 128}},
            )
            
            logger.info(f"Created Milvus collection: {collection_name}")
            return collection
            
        except Exception as e:
            logger.error(f"Failed to create Milvus collection: {e}")
            raise
    
    def insert_embeddings(
        self,
        collection_name: str,
        embeddings: List[List[float]],
        user_ids: List[str],
        texts: List[str],
        metadata: List[str],
    ) -> List[str]:
        """Insert embeddings into Milvus"""
        try:
            collection = Collection(collection_name)
            
            ids = [str(uuid.uuid4()) for _ in embeddings]
            timestamps = [int(datetime.now().timestamp() * 1000) for _ in embeddings]
            
            data = [
                ids,
                user_ids,
                embeddings,
                texts,
                metadata,
                timestamps,
            ]
            
            mr = collection.insert(data)
            collection.flush()
            
            logger.info(f"Inserted {len(embeddings)} embeddings into {collection_name}")
            return ids
            
        except Exception as e:
            logger.error(f"Failed to insert embeddings: {e}")
            raise
    
    def search_embeddings(
        self,
        collection_name: str,
        query_embedding: List[float],
        user_id: str,
        top_k: int = 5,
    ) -> List[Dict]:
        """Search for similar embeddings in Milvus"""
        try:
            collection = Collection(collection_name)
            collection.load()
            
            # Filter by user_id for isolation
            search_params = {
                "metric_type": "L2",
                "params": {"nprobe": 10},
            }
            
            results = collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=f"user_id == '{user_id}'",  # User isolation
                output_fields=["user_id", "text", "metadata", "timestamp"],
            )
            
            search_results = []
            for hits in results:
                for hit in hits:
                    search_results.append({
                        "id": hit.id,
                        "distance": hit.distance,
                        "user_id": hit.entity.get("user_id"),
                        "text": hit.entity.get("text"),
                        "metadata": hit.entity.get("metadata"),
                        "timestamp": hit.entity.get("timestamp"),
                    })
            
            collection.release()
            return search_results
            
        except Exception as e:
            logger.error(f"Failed to search embeddings: {e}")
            raise
    
    # ========================================================================
    # Schema Initialization
    # ========================================================================
    
    async def create_schema(self):
        """Create necessary schema in all databases"""
        await self._create_postgres_schema()
        await self._create_neo4j_schema()
        await self._create_mongodb_schema()
        self._create_milvus_schema()
    
    async def _create_postgres_schema(self):
        """Create PostgreSQL tables"""
        schema_sql = """
        -- Users table
        CREATE TABLE IF NOT EXISTS users (
            user_id VARCHAR(100) PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(255),
            date_of_birth DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        );
        
        -- Audit logs
        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id VARCHAR(100) PRIMARY KEY,
            user_id VARCHAR(100) REFERENCES users(user_id),
            event_type VARCHAR(100),
            resource VARCHAR(100),
            action VARCHAR(50),
            status VARCHAR(20),
            details JSONB,
            error TEXT,
            duration_ms FLOAT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Performance metrics
        CREATE TABLE IF NOT EXISTS performance_metrics (
            metric_id VARCHAR(100) PRIMARY KEY,
            endpoint VARCHAR(255),
            method VARCHAR(10),
            status_code INT,
            total_time_ms FLOAT,
            db_time_ms FLOAT,
            llm_time_ms FLOAT,
            retrieval_time_ms FLOAT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Create indexes
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON performance_metrics(timestamp);
        """
        
        async with self.postgres_pool.acquire() as conn:
            await conn.execute(schema_sql)
        logger.info("PostgreSQL schema initialized")
    
    async def _create_neo4j_schema(self):
        """Create Neo4j indexes and constraints"""
        schema_queries = [
            # User node constraints
            "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
            
            # Symptom nodes
            "CREATE INDEX symptom_name IF NOT EXISTS FOR (s:Symptom) ON (s.name)",
            
            # Medication nodes
            "CREATE INDEX medication_name IF NOT EXISTS FOR (m:Medication) ON (m.name)",
            
            # Create full-text indexes
            "CREATE INDEX symptom_fulltext IF NOT EXISTS FOR (s:Symptom) ON (s.name, s.description)",
        ]
        
        async with self.neo4j_driver.session() as session:
            for query in schema_queries:
                try:
                    await session.run(query)
                except Exception as e:
                    logger.debug(f"Index creation query failed (might already exist): {e}")
        
        logger.info("Neo4j schema initialized")
    
    async def _create_mongodb_schema(self):
        """Create MongoDB collections and indexes"""
        # Collections are created on first use
        # But we can pre-create with indexes
        try:
            collections_config = {
                "ingestion_records": [
                    ("user_id", pymongo.ASCENDING),
                    ("timestamp", pymongo.DESCENDING),
                ],
                "chat_history": [
                    ("user_id", pymongo.ASCENDING),
                    ("timestamp", pymongo.DESCENDING),
                ],
                "raw_documents": [
                    ("user_id", pymongo.ASCENDING),
                    ("created_at", pymongo.DESCENDING),
                ],
            }
            
            for collection_name, indexes in collections_config.items():
                col = self.mongo_db[collection_name]
                for index_fields in indexes:
                    col.create_index([index_fields])
            
            logger.info("MongoDB schema initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB schema: {e}")
    
    def _create_milvus_schema(self):
        """Create Milvus collections"""
        try:
            self.milvus_collection = self.create_milvus_collection(
                collection_name="medical_notes",
                dimension=384,
            )
            logger.info("Milvus schema initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Milvus schema: {e}")
    
    # ========================================================================
    # Cleanup
    # ========================================================================
    
    async def close(self):
        """Close all database connections"""
        logger.info("Closing database connections...")
        
        if self.neo4j_driver:
            await self.neo4j_driver.close()
            logger.info("✓ Neo4j closed")
        
        if self.postgres_pool:
            await self.postgres_pool.close()
            logger.info("✓ PostgreSQL closed")
        
        if self.mongo_client:
            self.mongo_client.close()
            logger.info("✓ MongoDB closed")
        
        # Milvus connections are global, just log
        logger.info("✓ Milvus connections closed")
    
    async def health_check(self) -> Dict[str, str]:
        """Check health of all database connections"""
        health_status = {}
        
        # Neo4j
        try:
            async with self.neo4j_driver.session() as session:
                await session.run("RETURN 1")
            health_status["neo4j"] = "connected"
        except Exception as e:
            health_status["neo4j"] = f"error: {str(e)}"
        
        # PostgreSQL
        try:
            async with self.postgres_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            health_status["postgres"] = "connected"
        except Exception as e:
            health_status["postgres"] = f"error: {str(e)}"
        
        # MongoDB
        try:
            await self.mongo_client.admin.command("ping")
            health_status["mongodb"] = "connected"
        except Exception as e:
            health_status["mongodb"] = f"error: {str(e)}"
        
        # Milvus
        try:
            from pymilvus import utility
            has_collection = utility.has_collection("medical_notes")
            health_status["milvus"] = "connected"
        except Exception as e:
            health_status["milvus"] = f"error: {str(e)}"
        
        return health_status
