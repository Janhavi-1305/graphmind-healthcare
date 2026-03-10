"""
Retrieval Service
Hybrid retrieval combining:
1. Neo4j graph traversal (structured, high-precision)
2. Milvus vector search (semantic, catch paraphrasing)
3. Smart merging and ranking with recency boost

Features:
- User isolation (graph and vector)
- Performance monitoring
- Duplicate detection
- Result deduplication
"""

import logging
import time
import json
from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime, timedelta

from config import settings
from database import DatabaseManager
from models import Citation, RetrievalEvidence, SeverityLevel
from utils.embeddings import EmbeddingService
from utils.time_utils import TimeUtils

logger = logging.getLogger(__name__)


class RetrievalService:
    """Service for hybrid retrieval of patient memories"""
    
    def __init__(self, db: DatabaseManager, embedding_service: EmbeddingService):
        self.db = db
        self.embeddings = embedding_service
        self.alpha = settings.HYBRID_RETRIEVAL_ALPHA  # Weight for vector score
    
    async def retrieve(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        include_graph: bool = True,
        include_vector: bool = True,
    ) -> Tuple[List[Citation], RetrievalEvidence, float]:
        """
        Retrieve relevant memories using hybrid approach.
        
        Args:
            user_id: Patient ID (for isolation)
            query: Query text
            top_k: Number of results to return
            include_graph: Use graph retrieval
            include_vector: Use vector retrieval
        
        Returns:
            (citations, evidence, total_time_ms)
        """
        retrieval_start = time.time()
        
        all_results = {}  # {node_id: {score, data, source}}
        
        # Graph retrieval
        graph_results = []
        if include_graph:
            try:
                graph_start = time.time()
                graph_results = await self._retrieve_from_graph(user_id, query, top_k)
                graph_time = (time.time() - graph_start) * 1000
                logger.info(f"Graph retrieval: {len(graph_results)} results in {graph_time:.2f}ms")
                
                # Add graph results
                for result in graph_results:
                    node_id = result["node_id"]
                    if node_id not in all_results:
                        all_results[node_id] = {
                            "score": result["score"],
                            "data": result,
                            "source": "graph",
                            "graph_score": result["score"],
                            "vector_score": 0.0,
                        }
                    else:
                        all_results[node_id]["graph_score"] = result["score"]
            except Exception as e:
                logger.error(f"Graph retrieval failed: {e}")
        
        # Vector retrieval
        vector_results = []
        if include_vector:
            try:
                vector_start = time.time()
                vector_results = await self._retrieve_from_vector(user_id, query, top_k)
                vector_time = (time.time() - vector_start) * 1000
                logger.info(f"Vector retrieval: {len(vector_results)} results in {vector_time:.2f}ms")
                
                # Add vector results
                for result in vector_results:
                    node_id = result["node_id"]
                    if node_id not in all_results:
                        all_results[node_id] = {
                            "score": result["score"],
                            "data": result,
                            "source": "vector",
                            "graph_score": 0.0,
                            "vector_score": result["score"],
                        }
                    else:
                        all_results[node_id]["vector_score"] = result["score"]
            except Exception as e:
                logger.error(f"Vector retrieval failed: {e}")
        
        # Merge and rank results
        merged_results = self._merge_and_rank(all_results, top_k)
        
        # Convert to citations
        citations = self._results_to_citations(merged_results)
        
        # Create evidence
        retrieval_time_ms = (time.time() - retrieval_start) * 1000
        evidence = RetrievalEvidence(
            graph_results=len(graph_results),
            vector_results=len(vector_results),
            merged_results=len(merged_results),
            retrieval_time_ms=retrieval_time_ms,
            top_results=citations[:3],  # Top 3 for display
        )
        
        logger.info(
            f"Hybrid retrieval complete: "
            f"{len(graph_results)} graph + {len(vector_results)} vector → "
            f"{len(merged_results)} merged in {retrieval_time_ms:.2f}ms"
        )
        
        return citations, evidence, retrieval_time_ms
    
    async def _retrieve_from_graph(self, user_id: str, query: str, top_k: int) -> List[Dict]:
        """Graph-based retrieval using Neo4j"""
        results = []
        
        try:
            # Strategy 1: Direct keyword match in symptoms/medications
            cypher_query = """
            MATCH (user:User {user_id: $user_id})
            OPTIONAL MATCH (user)-[r:HAS_SYMPTOM]->(symptom:Symptom)
            WHERE toLower(symptom.name) CONTAINS toLower($query_term)
            OPTIONAL MATCH (user)-[r2:TAKES_MEDICATION]->(med:Medication)
            WHERE toLower(med.name) CONTAINS toLower($query_term)
            WITH user, symptom, med, r, r2
            WHERE symptom IS NOT NULL OR med IS NOT NULL
            RETURN
                CASE
                    WHEN symptom IS NOT NULL THEN symptom
                    ELSE med
                END as node,
                CASE
                    WHEN symptom IS NOT NULL THEN 'HAS_SYMPTOM'
                    ELSE 'TAKES_MEDICATION'
                END as relationship_type,
                CASE
                    WHEN symptom IS NOT NULL THEN r.timestamp
                    ELSE r2.timestamp
                END as timestamp
            LIMIT $limit
            """
            
            # Try multi-word matching
            query_terms = query.split()
            for term in query_terms[:3]:  # Limit terms to try
                records = await self.db.execute_cypher(
                    cypher_query,
                    {
                        "user_id": user_id,
                        "query_term": term,
                        "limit": top_k,
                    },
                )
                
                for record in records:
                    node = record.get("node")
                    if node:
                        # Recency boost
                        timestamp = record.get("timestamp")
                        recency_score = self._calculate_recency_score(timestamp)
                        
                        results.append({
                            "node_id": node["node_id"],
                            "node_type": node.get("__typename", "Unknown"),
                            "title": node.get("name", node.get("description", "")),
                            "snippet": node.get("notes", ""),
                            "properties": dict(node),
                            "score": recency_score * 0.8,  # Keyword matches get 80% weight
                            "relationship_type": record.get("relationship_type"),
                        })
            
            # Strategy 2: Symptom-trigger relationships
            trigger_query = """
            MATCH (user:User {user_id: $user_id})
            OPTIONAL MATCH (user)-[r:HAS_SYMPTOM]->(symptom:Symptom)-[tr:TRIGGERED_BY]->(trigger:Trigger)
            WHERE toLower(trigger.name) CONTAINS toLower($query_term)
            RETURN symptom, trigger, r.timestamp, tr.confidence
            LIMIT $limit
            """
            
            for term in query_terms[:2]:
                records = await self.db.execute_cypher(
                    trigger_query,
                    {
                        "user_id": user_id,
                        "query_term": term,
                        "limit": top_k,
                    },
                )
                
                for record in records:
                    trigger = record.get("trigger")
                    if trigger:
                        results.append({
                            "node_id": trigger["node_id"],
                            "node_type": "Trigger",
                            "title": trigger.get("name", ""),
                            "snippet": trigger.get("description", ""),
                            "properties": dict(trigger),
                            "score": record.get("confidence", 0.5),
                            "relationship_type": "TRIGGERED_BY",
                        })
            
        except Exception as e:
            logger.error(f"Graph retrieval error: {e}")
        
        # Remove duplicates and sort
        unique_results = {}
        for result in results:
            node_id = result["node_id"]
            if node_id not in unique_results or result["score"] > unique_results[node_id]["score"]:
                unique_results[node_id] = result
        
        sorted_results = sorted(unique_results.values(), key=lambda x: x["score"], reverse=True)
        return sorted_results[:top_k]
    
    async def _retrieve_from_vector(self, user_id: str, query: str, top_k: int) -> List[Dict]:
        """Vector-based retrieval using Milvus"""
        results = []
        
        try:
            # Embed query
            query_embedding = self.embeddings.embed([query])[0]
            
            # Search in Milvus
            milvus_results = self.db.search_embeddings(
                collection_name="medical_notes",
                query_embedding=query_embedding,
                user_id=user_id,
                top_k=top_k,
            )
            
            for hit in milvus_results:
                # Convert distance to similarity (closer = higher similarity)
                similarity = 1 / (1 + hit.get("distance", 1))
                
                results.append({
                    "node_id": hit.get("id", f"vector_{len(results)}"),
                    "node_type": "MedicalNote",
                    "title": "Medical Note",
                    "snippet": hit.get("text", "")[:200],
                    "properties": {
                        "text": hit.get("text"),
                        "metadata": hit.get("metadata"),
                        "timestamp": hit.get("timestamp"),
                    },
                    "score": similarity,
                    "relationship_type": "VECTOR_MATCH",
                })
        
        except Exception as e:
            logger.error(f"Vector retrieval error: {e}")
        
        return results[:top_k]
    
    def _merge_and_rank(self, all_results: Dict, top_k: int) -> List[Dict]:
        """Merge graph and vector results with hybrid scoring"""
        merged = []
        
        for node_id, result_data in all_results.items():
            # Hybrid scoring: alpha * vector_score + (1-alpha) * graph_score
            graph_score = result_data.get("graph_score", 0.0)
            vector_score = result_data.get("vector_score", 0.0)
            
            combined_score = (
                self.alpha * vector_score +
                (1 - self.alpha) * graph_score
            )
            
            merged.append({
                **result_data["data"],
                "combined_score": combined_score,
                "graph_score": graph_score,
                "vector_score": vector_score,
            })
        
        # Sort by combined score
        merged.sort(key=lambda x: x["combined_score"], reverse=True)
        
        return merged[:top_k]
    
    def _calculate_recency_score(self, timestamp_str: Optional[str]) -> float:
        """Calculate recency score (newer = higher)"""
        if not timestamp_str:
            return 0.5
        
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            now = datetime.now(timestamp.tzinfo) if timestamp.tzinfo else datetime.now()
            
            days_ago = (now - timestamp).days
            
            # Exponential decay: -0.05 per day, min 0.1
            score = max(0.1, 1.0 * (0.95 ** days_ago))
            
            return score
        except Exception as e:
            logger.debug(f"Could not calculate recency: {e}")
            return 0.5
    
    def _results_to_citations(self, results: List[Dict]) -> List[Citation]:
        """Convert results to Citation objects"""
        citations = []
        
        for result in results:
            citation = Citation(
                node_id=result.get("node_id", ""),
                node_type=result.get("node_type", "Unknown"),
                title=result.get("title", ""),
                snippet=result.get("snippet", "")[:200],
                relevance_score=result.get("combined_score", 0.0),
                source_type="medical_record",  # Could be more specific
                created_at=datetime.now(),
            )
            citations.append(citation)
        
        return citations
    
    async def get_user_mindmap(self, user_id: str) -> Dict:
        """Retrieve user's entire memory graph for visualization"""
        try:
            cypher_query = """
            MATCH (user:User {user_id: $user_id})
            OPTIONAL MATCH (user)-[r]->(node)
            RETURN user, collect({node: node, relationship: r}) as neighbors
            """
            
            records = await self.db.execute_cypher(
                cypher_query,
                {"user_id": user_id},
            )
            
            if not records:
                return {"nodes": [], "edges": [], "stats": {"total_nodes": 0, "total_edges": 0}}
            
            nodes = []
            edges = []
            node_ids = set()
            
            user_node = records[0].get("user")
            if user_node:
                nodes.append({
                    "id": user_node["node_id"],
                    "label": f"Patient: {user_id}",
                    "type": "User",
                    "properties": dict(user_node),
                })
                node_ids.add(user_node["node_id"])
            
            neighbors = records[0].get("neighbors", [])
            for neighbor in neighbors:
                node = neighbor.get("node")
                rel = neighbor.get("relationship")
                
                if node:
                    node_id = node.get("node_id")
                    if node_id and node_id not in node_ids:
                        nodes.append({
                            "id": node_id,
                            "label": node.get("name", node.get("description", "")),
                            "type": node.get("__typename", "Unknown"),
                            "properties": dict(node),
                        })
                        node_ids.add(node_id)
                    
                    if rel and user_node:
                        edges.append({
                            "source": user_node["node_id"],
                            "target": node_id,
                            "label": rel.type if hasattr(rel, "type") else "RELATED",
                            "properties": dict(rel) if rel else {},
                        })
            
            return {
                "nodes": nodes,
                "edges": edges,
                "stats": {
                    "total_nodes": len(nodes),
                    "total_edges": len(edges),
                    "node_types": {},
                },
            }
        
        except Exception as e:
            logger.error(f"Failed to get user mindmap: {e}")
            return {"nodes": [], "edges": [], "stats": {"total_nodes": 0, "total_edges": 0}}
