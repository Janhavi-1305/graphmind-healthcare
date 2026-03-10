"""
Ingestion Service
Handles:
1. Entity extraction from user input (LLM-based)
2. Graph writing (Neo4j)
3. Vector embedding and indexing (Milvus)
4. Audit logging
"""

import json
import logging
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime
import uuid
import asyncio

from config import settings
from database import DatabaseManager
from models import (
    MemoryIngestionRequest,
    SymptomData,
    MedicationData,
    TriggerData,
    AllergyData,
    LifestyleData,
    GoalData,
)
from services.llm_client import LLMClient
from utils.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class IngestionService:
    """Service for ingesting and processing user health data"""
    
    def __init__(self, db: DatabaseManager, llm_client: LLMClient, embedding_service: EmbeddingService):
        self.db = db
        self.llm = llm_client
        self.embeddings = embedding_service
        
        # Extraction prompt template
        self.extraction_prompt = """
You are a healthcare data extraction assistant. Extract structured health information from the user's text.

Return a JSON object with the following fields (omit if not mentioned):
{
    "symptoms": [
        {
            "name": "symptom name",
            "severity": "mild/moderate/severe/critical",
            "duration": "e.g. 2 weeks",
            "onset_date": "YYYY-MM-DD or approximate",
            "notes": "additional details"
        }
    ],
    "medications": [
        {
            "name": "drug name",
            "dosage": "e.g. 500mg",
            "frequency": "e.g. twice daily",
            "start_date": "YYYY-MM-DD or approximate",
            "reason": "why taking this"
        }
    ],
    "triggers": [
        {
            "name": "trigger name",
            "description": "what triggers symptoms",
            "related_symptom": "which symptom",
            "confidence": 0.0-1.0
        }
    ],
    "allergies": [
        {
            "name": "allergen",
            "reaction": "what happens",
            "severity": "mild/moderate/severe/critical",
            "reaction_type": "e.g. skin reaction"
        }
    ],
    "lifestyle": [
        {
            "category": "exercise/diet/sleep/stress/other",
            "detail": "specific detail",
            "frequency": "how often",
            "impact": "positive/negative/neutral"
        }
    ],
    "goals": [
        {
            "description": "health goal",
            "target_date": "YYYY-MM-DD or approximate",
            "status": "active/on_hold/completed",
            "priority": 1-5
        }
    ]
}

User text:
{user_text}

Return ONLY valid JSON, no markdown or explanation.
"""
    
    async def ingest(self, request: MemoryIngestionRequest) -> Tuple[int, int, List, List]:
        """
        Ingest new memory from user input.
        
        Returns:
            (nodes_created, edges_created, nodes_list, edges_list)
        """
        logger.info(f"Ingesting memory for user {request.user_id}")
        
        # Extract entities if not provided
        if not any([request.symptoms, request.medications, request.triggers]):
            logger.info("Extracting entities from text using LLM...")
            extracted_data = await self._extract_entities(request.text)
        else:
            extracted_data = {
                "symptoms": request.symptoms or [],
                "medications": request.medications or [],
                "triggers": request.triggers or [],
                "allergies": request.allergies or [],
                "lifestyle": request.lifestyle or [],
                "goals": request.goals or [],
            }
        
        # Write to graph
        nodes_created, edges_created, nodes_data, edges_data = await self._write_to_graph(
            user_id=request.user_id,
            extracted_data=extracted_data,
            source_type=request.source_type,
        )
        
        # Store raw input in MongoDB
        await self._store_raw_input(request, extracted_data)
        
        # Generate embedding and store in Milvus
        await self._embed_and_index(request.user_id, request.text, extracted_data)
        
        # Audit log
        await self._audit_ingestion(
            user_id=request.user_id,
            source_type=request.source_type,
            nodes_created=nodes_created,
            edges_created=edges_created,
        )
        
        logger.info(f"Ingestion complete: {nodes_created} nodes, {edges_created} edges")
        return nodes_created, edges_created, nodes_data, edges_data
    
    async def _extract_entities(self, text: str) -> Dict[str, Any]:
        """Extract entities from text using LLM"""
        try:
            prompt = self.extraction_prompt.format(user_text=text)
            response = await self.llm.generate(prompt)
            
            # Parse JSON response
            extracted = json.loads(response)
            return extracted
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            # Return empty structure
            return {
                "symptoms": [],
                "medications": [],
                "triggers": [],
                "allergies": [],
                "lifestyle": [],
                "goals": [],
            }
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return {}
    
    async def _write_to_graph(
        self,
        user_id: str,
        extracted_data: Dict[str, Any],
        source_type: str,
    ) -> Tuple[int, int, List, List]:
        """Write extracted entities to Neo4j graph"""
        
        nodes_created = 0
        edges_created = 0
        nodes_data = []
        edges_data = []
        
        try:
            # Ensure user node exists
            user_node_id = f"user_{user_id}"
            await self._create_or_update_node(
                node_id=user_node_id,
                node_type="User",
                properties={"user_id": user_id, "created_at": datetime.now().isoformat()},
            )
            nodes_created += 1
            
            # Process symptoms
            for symptom in extracted_data.get("symptoms", []):
                symptom_id = f"symptom_{uuid.uuid4().hex[:8]}"
                
                # Create symptom node
                await self._create_or_update_node(
                    node_id=symptom_id,
                    node_type="Symptom",
                    properties={
                        "name": symptom.get("name", ""),
                        "severity": symptom.get("severity", "moderate"),
                        "duration": symptom.get("duration"),
                        "onset_date": symptom.get("onset_date"),
                        "notes": symptom.get("notes"),
                        "created_at": datetime.now().isoformat(),
                    },
                )
                nodes_created += 1
                nodes_data.append({"id": symptom_id, "type": "Symptom", "name": symptom.get("name")})
                
                # Create relationship
                rel_id = f"rel_{uuid.uuid4().hex[:8]}"
                await self._create_relationship(
                    source_id=user_node_id,
                    target_id=symptom_id,
                    relationship_type="HAS_SYMPTOM",
                    properties={
                        "timestamp": datetime.now().isoformat(),
                        "severity": symptom.get("severity", "moderate"),
                        "source": source_type,
                    },
                )
                edges_created += 1
                edges_data.append({
                    "id": rel_id,
                    "source": user_node_id,
                    "target": symptom_id,
                    "type": "HAS_SYMPTOM",
                })
                
                # Process triggers for this symptom
                for trigger in extracted_data.get("triggers", []):
                    if trigger.get("related_symptom", "").lower() == symptom.get("name", "").lower():
                        trigger_id = f"trigger_{uuid.uuid4().hex[:8]}"
                        
                        # Create trigger node
                        await self._create_or_update_node(
                            node_id=trigger_id,
                            node_type="Trigger",
                            properties={
                                "name": trigger.get("name", ""),
                                "description": trigger.get("description"),
                                "confidence": trigger.get("confidence", 0.5),
                                "created_at": datetime.now().isoformat(),
                            },
                        )
                        nodes_created += 1
                        nodes_data.append({"id": trigger_id, "type": "Trigger", "name": trigger.get("name")})
                        
                        # Create TRIGGERED_BY relationship
                        await self._create_relationship(
                            source_id=symptom_id,
                            target_id=trigger_id,
                            relationship_type="TRIGGERED_BY",
                            properties={
                                "confidence": trigger.get("confidence", 0.5),
                                "observed": 1,
                                "timestamp": datetime.now().isoformat(),
                            },
                        )
                        edges_created += 1
            
            # Process medications
            for medication in extracted_data.get("medications", []):
                med_id = f"medication_{uuid.uuid4().hex[:8]}"
                
                # Create medication node
                await self._create_or_update_node(
                    node_id=med_id,
                    node_type="Medication",
                    properties={
                        "name": medication.get("name", ""),
                        "dosage": medication.get("dosage"),
                        "frequency": medication.get("frequency"),
                        "start_date": medication.get("start_date"),
                        "reason": medication.get("reason"),
                        "created_at": datetime.now().isoformat(),
                    },
                )
                nodes_created += 1
                nodes_data.append({"id": med_id, "type": "Medication", "name": medication.get("name")})
                
                # Create relationship
                await self._create_relationship(
                    source_id=user_node_id,
                    target_id=med_id,
                    relationship_type="TAKES_MEDICATION",
                    properties={
                        "dosage": medication.get("dosage"),
                        "frequency": medication.get("frequency"),
                        "start_date": medication.get("start_date"),
                        "timestamp": datetime.now().isoformat(),
                    },
                )
                edges_created += 1
            
            # Process allergies
            for allergy in extracted_data.get("allergies", []):
                allergy_id = f"allergy_{uuid.uuid4().hex[:8]}"
                
                await self._create_or_update_node(
                    node_id=allergy_id,
                    node_type="Allergy",
                    properties={
                        "name": allergy.get("name", ""),
                        "reaction": allergy.get("reaction"),
                        "severity": allergy.get("severity"),
                        "reaction_type": allergy.get("reaction_type"),
                        "created_at": datetime.now().isoformat(),
                    },
                )
                nodes_created += 1
                
                await self._create_relationship(
                    source_id=user_node_id,
                    target_id=allergy_id,
                    relationship_type="HAS_ALLERGY",
                    properties={
                        "severity": allergy.get("severity"),
                        "timestamp": datetime.now().isoformat(),
                    },
                )
                edges_created += 1
            
            # Process lifestyle
            for lifestyle_item in extracted_data.get("lifestyle", []):
                lifestyle_id = f"lifestyle_{uuid.uuid4().hex[:8]}"
                
                await self._create_or_update_node(
                    node_id=lifestyle_id,
                    node_type="Lifestyle",
                    properties={
                        "category": lifestyle_item.get("category", ""),
                        "detail": lifestyle_item.get("detail"),
                        "frequency": lifestyle_item.get("frequency"),
                        "impact": lifestyle_item.get("impact"),
                        "created_at": datetime.now().isoformat(),
                    },
                )
                nodes_created += 1
                
                await self._create_relationship(
                    source_id=user_node_id,
                    target_id=lifestyle_id,
                    relationship_type="HAS_LIFESTYLE",
                    properties={
                        "impact": lifestyle_item.get("impact"),
                        "timestamp": datetime.now().isoformat(),
                    },
                )
                edges_created += 1
            
            # Process goals
            for goal in extracted_data.get("goals", []):
                goal_id = f"goal_{uuid.uuid4().hex[:8]}"
                
                await self._create_or_update_node(
                    node_id=goal_id,
                    node_type="Goal",
                    properties={
                        "description": goal.get("description", ""),
                        "target_date": goal.get("target_date"),
                        "status": goal.get("status", "active"),
                        "priority": goal.get("priority", 3),
                        "created_at": datetime.now().isoformat(),
                    },
                )
                nodes_created += 1
                
                await self._create_relationship(
                    source_id=user_node_id,
                    target_id=goal_id,
                    relationship_type="WORKS_ON",
                    properties={
                        "status": goal.get("status", "active"),
                        "priority": goal.get("priority", 3),
                        "timestamp": datetime.now().isoformat(),
                    },
                )
                edges_created += 1
            
        except Exception as e:
            logger.error(f"Failed to write to graph: {e}")
            raise
        
        return nodes_created, edges_created, nodes_data, edges_data
    
    async def _create_or_update_node(self, node_id: str, node_type: str, properties: Dict):
        """Create or update a node in Neo4j"""
        cypher_query = f"""
        MERGE (n:{node_type} {{node_id: $node_id}})
        SET n += $properties
        RETURN n
        """
        
        await self.db.execute_cypher(
            cypher_query,
            {"node_id": node_id, "properties": properties},
        )
    
    async def _create_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        properties: Dict,
    ):
        """Create a relationship between two nodes"""
        cypher_query = f"""
        MATCH (source {{node_id: $source_id}})
        MATCH (target {{node_id: $target_id}})
        MERGE (source)-[r:{relationship_type}]->(target)
        SET r += $properties
        RETURN r
        """
        
        await self.db.execute_cypher(
            cypher_query,
            {
                "source_id": source_id,
                "target_id": target_id,
                "properties": properties,
            },
        )
    
    async def _store_raw_input(self, request: MemoryIngestionRequest, extracted_data: Dict):
        """Store raw input in MongoDB for audit trail"""
        try:
            collection = await self.db.get_mongo_collection("ingestion_records")
            doc = {
                "user_id": request.user_id,
                "raw_text": request.text,
                "source_type": request.source_type,
                "extracted_data": extracted_data,
                "metadata": request.metadata or {},
                "timestamp": datetime.now(),
            }
            await collection.insert_one(doc)
        except Exception as e:
            logger.error(f"Failed to store raw input in MongoDB: {e}")
    
    async def _embed_and_index(self, user_id: str, text: str, extracted_data: Dict):
        """Generate embeddings and store in Milvus"""
        try:
            # Generate embedding
            embedding = self.embeddings.embed([text])[0]
            
            # Prepare metadata
            metadata_str = json.dumps({
                "symptoms": [s.get("name") for s in extracted_data.get("symptoms", [])],
                "medications": [m.get("name") for m in extracted_data.get("medications", [])],
            })
            
            # Insert into Milvus
            self.db.insert_embeddings(
                collection_name="medical_notes",
                embeddings=[embedding],
                user_ids=[user_id],
                texts=[text[:500]],  # Truncate for storage
                metadata=[metadata_str],
            )
            
        except Exception as e:
            logger.error(f"Failed to embed and index: {e}")
            # Don't fail ingestion if embedding fails
    
    async def _audit_ingestion(
        self,
        user_id: str,
        source_type: str,
        nodes_created: int,
        edges_created: int,
    ):
        """Log ingestion event"""
        try:
            collection = await self.db.get_mongo_collection("audit_logs")
            log_entry = {
                "user_id": user_id,
                "event_type": "memory_ingest",
                "action": "create",
                "status": "success",
                "details": {
                    "source_type": source_type,
                    "nodes_created": nodes_created,
                    "edges_created": edges_created,
                },
                "timestamp": datetime.now(),
            }
            await collection.insert_one(log_entry)
        except Exception as e:
            logger.error(f"Failed to log ingestion: {e}")
