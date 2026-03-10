"""
LLM Client and Embedding Service
- LLMClient: Wrapper for Anthropic/OpenAI APIs with healthcare-safe prompting
- EmbeddingService: Sentence-transformers for semantic embeddings
"""

import logging
from typing import List, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor

from config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Wrapper for LLM API calls (Anthropic/OpenAI)"""
    
    def __init__(self, provider: str = None, api_key: str = None, model: str = None):
        self.provider = provider or settings.LLM_PROVIDER
        self.model = model or settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        
        if self.provider == "anthropic":
            try:
                import anthropic
                self.client = anthropic.Anthropic(
                    api_key=api_key or settings.ANTHROPIC_API_KEY
                )
            except ImportError:
                logger.error("anthropic package not installed. Install with: pip install anthropic")
                self.client = None
        
        elif self.provider == "openai":
            try:
                import openai
                openai.api_key = api_key or settings.OPENAI_API_KEY
                self.client = openai
            except ImportError:
                logger.error("openai package not installed. Install with: pip install openai")
                self.client = None
        
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate response from LLM.
        
        Args:
            prompt: User prompt
            system_prompt: System message (optional)
            temperature: Override default temperature
            max_tokens: Override default max_tokens
        
        Returns:
            Generated text response
        """
        
        if not self.client:
            logger.error("LLM client not initialized")
            return "Error: LLM service unavailable"
        
        temperature = temperature or self.temperature
        max_tokens = max_tokens or self.max_tokens
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            self._generate_sync,
            prompt,
            system_prompt,
            temperature,
            max_tokens,
        )
        
        return response
    
    def _generate_sync(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Synchronous LLM generation (for executor)"""
        
        try:
            if self.provider == "anthropic":
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_prompt or "You are a helpful healthcare assistant.",
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                )
                return message.content[0].text
            
            elif self.provider == "openai":
                response = self.client.ChatCompletion.create(
                    model=self.model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system=system_prompt or "You are a helpful healthcare assistant.",
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                )
                return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return f"Error generating response: {str(e)}"
    
    async def generate_answer(
        self,
        query: str,
        context: str,
        citation_format: str = "inline",
    ) -> str:
        """
        Generate healthcare-safe answer grounded in context.
        
        Args:
            query: Patient question
            context: Retrieved memories to ground response
            citation_format: How to format citations
        
        Returns:
            Grounded answer
        """
        
        system_prompt = """You are a healthcare intake assistant. Your role is to:

1. Summarize patient memories retrieved from the database
2. Identify patterns (e.g., "Your headaches seem to spike on certain days")
3. Suggest next steps for their healthcare provider
4. NEVER diagnose or prescribe—only reflect stored information

STRICT RULES:
- Do NOT provide medical diagnosis
- Do NOT recommend specific medications
- Do NOT replace a healthcare provider
- Flag any concerning patterns for provider review
- Be empathetic and conversational
- Always cite sources: "Based on your entry on {date}..."

Be concise and focused on the patient's health journey."""
        
        user_prompt = f"""Question: {query}

Retrieved patient memories:
{context}

Please answer the question based ONLY on the patient's stored memories."""
        
        response = await self.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.6,  # Lower temperature for healthcare
            max_tokens=500,
        )
        
        return response


class EmbeddingService:
    """Service for generating embeddings using sentence-transformers"""
    
    def __init__(self, model_name: str = None, dimension: int = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.dimension = dimension or settings.EMBEDDING_DIMENSION
        
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"Loaded embedding model: {self.model_name}")
        except ImportError:
            logger.error(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
            self.model = None
        
        # Embedding cache (optional)
        self.cache = {} if settings.CACHE_EMBEDDINGS else None
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
        
        Returns:
            List of embedding vectors (one per text)
        """
        
        if not self.model:
            logger.error("Embedding model not initialized")
            return [[0.0] * self.dimension for _ in texts]
        
        # Check cache
        embeddings = []
        texts_to_embed = []
        cache_indices = []
        
        for i, text in enumerate(texts):
            if self.cache and text in self.cache:
                embeddings.append(None)  # Placeholder
                cache_indices.append((i, self.cache[text]))
            else:
                embeddings.append(None)
                texts_to_embed.append(text)
        
        # Generate embeddings for non-cached texts
        if texts_to_embed:
            try:
                generated = self.model.encode(
                    texts_to_embed,
                    convert_to_list=True,
                )
                
                # Cache results
                if self.cache:
                    for text, embedding in zip(texts_to_embed, generated):
                        self.cache[text] = embedding
                
                # Fill in embeddings
                j = 0
                for i in range(len(texts)):
                    if embeddings[i] is None:
                        embeddings[i] = generated[j]
                        j += 1
            
            except Exception as e:
                logger.error(f"Embedding generation failed: {e}")
                embeddings = [[0.0] * self.dimension for _ in texts]
        
        # Fill cached embeddings
        for i, embedding in cache_indices:
            embeddings[i] = embedding
        
        return embeddings
    
    async def embed_async(self, texts: List[str]) -> List[List[float]]:
        """Async wrapper for embed"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed, texts)
    
    def get_dimension(self) -> int:
        """Get embedding dimension"""
        return self.dimension
    
    def clear_cache(self):
        """Clear embedding cache"""
        if self.cache:
            self.cache.clear()
            logger.info("Embedding cache cleared")
