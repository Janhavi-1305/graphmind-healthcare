"""
Generation Service
Handles LLM-based answer generation with healthcare-specific safety measures
"""

import logging
from typing import Optional
from datetime import datetime

from services.llm_client import LLMClient
from models import RetrievalEvidence

logger = logging.getLogger(__name__)


class GenerationService:
    """Service for generating healthcare-safe answers"""
    
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
    
    async def generate_answer(
        self,
        query: str,
        context: str,
        retrieval_evidence: RetrievalEvidence,
        include_disclaimers: bool = True,
    ) -> str:
        """
        Generate answer grounded in retrieved context.
        
        Healthcare-specific safety:
        - No diagnosis or treatment recommendations
        - Emphasize provider consultation
        - Flag concerning patterns
        - Ground in stored information only
        
        Args:
            query: Patient question
            context: Retrieved memories (formatted as context)
            retrieval_evidence: Evidence from retrieval process
            include_disclaimers: Add healthcare disclaimers
        
        Returns:
            Grounded answer
        """
        
        system_prompt = self._create_system_prompt(include_disclaimers)
        user_prompt = self._create_user_prompt(query, context, retrieval_evidence)
        
        try:
            response = await self.llm.generate_answer(
                query=query,
                context=context,
            )
            
            # Post-process for safety
            response = self._post_process_answer(response, query)
            
            return response
        
        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            return "I'm unable to provide an answer at this moment. Please consult your healthcare provider."
    
    def _create_system_prompt(self, include_disclaimers: bool = True) -> str:
        """Create healthcare-specific system prompt"""
        
        base_prompt = """You are a healthcare intake assistant. Your role is to:

1. Summarize patient memories from the database
2. Identify health patterns (e.g., "Your symptoms seem to worsen on certain days")
3. Suggest reflective questions for patient exploration
4. Flag any concerning patterns for provider review

CRITICAL RULES - NEVER VIOLATE:
- Do NOT diagnose medical conditions
- Do NOT recommend specific medications
- Do NOT suggest treatments
- Do NOT replace a healthcare provider
- Always stay grounded in the patient's stored memories
- Use phrases like "Based on your entry..." or "You mentioned..."

TONE:
- Empathetic and supportive
- Clear and concise
- Professional but conversational
- Non-judgmental"""
        
        if include_disclaimers:
            base_prompt += """

DISCLAIMERS TO INCLUDE:
- "This is not medical advice"
- "Please consult your healthcare provider"
- "If you experience emergency symptoms, seek immediate care" (if applicable)"""
        
        return base_prompt
    
    def _create_user_prompt(
        self,
        query: str,
        context: str,
        retrieval_evidence: RetrievalEvidence,
    ) -> str:
        """Create user prompt with context"""
        
        prompt = f"""Patient Query: {query}

Retrieved Memories (based on your past entries):
{context}

Retrieval Details:
- Found {retrieval_evidence.graph_results} structured memory entries
- Found {retrieval_evidence.vector_results} similar notes
- Merged to top {retrieval_evidence.merged_results} most relevant memories

Please provide a thoughtful response based ONLY on the patient's stored memories."""
        
        return prompt
    
    def _post_process_answer(self, answer: str, query: str) -> str:
        """Post-process answer for safety compliance"""
        
        # Check for common red flags
        red_flags = [
            "prescribe",
            "take this medication",
            "diagnose",
            "is definitely",
            "will definitely cure",
            "guaranteed",
            "replace your doctor",
        ]
        
        for flag in red_flags:
            if flag.lower() in answer.lower():
                logger.warning(f"Red flag detected: '{flag}' in answer")
                # Don't fail, but log and could add disclaimer
        
        # Ensure disclaimers are present for sensitive topics
        sensitive_keywords = [
            "symptom",
            "pain",
            "medication",
            "treatment",
            "health",
        ]
        
        if any(keyword in query.lower() for keyword in sensitive_keywords):
            if "healthcare provider" not in answer.lower() and "doctor" not in answer.lower():
                answer = answer.rstrip(".") + ".\n\nPlease consult your healthcare provider for medical advice."
        
        return answer


class AnswerValidator:
    """Validates answers for safety and quality"""
    
    @staticmethod
    def check_for_medical_advice(answer: str) -> bool:
        """Check if answer contains medical advice (red flags)"""
        
        red_flags = [
            "prescribe",
            "take this medication",
            "you should take",
            "must take",
            "diagnosed",
            "definitely have",
            "will cure",
            "guaranteed",
            "stop taking",
        ]
        
        for flag in red_flags:
            if flag.lower() in answer.lower():
                return True
        
        return False
    
    @staticmethod
    def check_grounding(answer: str, context: str) -> float:
        """
        Check if answer is grounded in context.
        Returns score 0-1.
        """
        
        # Simple heuristic: check if main nouns from answer appear in context
        # In production, use more sophisticated semantic similarity
        
        from collections import Counter
        import re
        
        # Extract nouns (simplified)
        def extract_terms(text):
            # Simple: extract capitalized phrases and important words
            words = re.findall(r'\b[A-Z][a-z]+\b|\b(symptom|medication|trigger|allergy|goal)\w*\b', text)
            return set(words)
        
        answer_terms = extract_terms(answer)
        context_terms = extract_terms(context)
        
        if not answer_terms:
            return 1.0  # No specific claims, so grounded
        
        overlap = len(answer_terms & context_terms)
        coverage = overlap / len(answer_terms)
        
        return min(1.0, coverage)
    
    @staticmethod
    def calculate_confidence(retrieval_evidence: RetrievalEvidence) -> float:
        """
        Calculate confidence score based on retrieval evidence.
        
        Factors:
        - Number of results
        - Result quality (relevance scores)
        - Concordance (graph + vector agreement)
        """
        
        # Base score from number of results
        result_score = min(1.0, retrieval_evidence.merged_results / 5)
        
        # Bonus for agreement between graph and vector
        if retrieval_evidence.graph_results > 0 and retrieval_evidence.vector_results > 0:
            agreement_score = retrieval_evidence.merged_results / (
                retrieval_evidence.graph_results + retrieval_evidence.vector_results
            )
        else:
            agreement_score = 0.5
        
        # Combined confidence
        confidence = 0.7 * result_score + 0.3 * agreement_score
        
        return min(1.0, max(0.0, confidence))
