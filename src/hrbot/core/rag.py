"""
Retrieval-Augmented Generation (RAG) core implementation.

This module provides the complete RAG system with:
1. Query processing and document retrieval
2. Context augmentation with relevant knowledge
3. Dynamic prompt construction
4. Response generation with source tracking
5. Built-in conversation context handling

It implements a clean, modular approach that separates concerns
and provides high configurability through dependency injection.
"""

import logging
import re
from typing import List, Dict, Any, Optional, Protocol, Set, AsyncGenerator
from dataclasses import dataclass
from hrbot.core.document import Document

from hrbot.infrastructure.vector_store import VectorStore
from hrbot.config.settings import settings
from hrbot.utils.result import Result, Success, Error
from hrbot.utils.error import RAGError, ErrorCode

logger = logging.getLogger(__name__)

class EmbeddingProvider(Protocol):
    """Protocol defining the interface for embedding providers."""
    
    def embed_query(self, text: str) -> List[float]:
        """Generate embeddings for a query."""
        ...
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of documents."""
        ...

class LLMProvider(Protocol):
    """Protocol defining the interface for LLM providers."""
    
    async def generate_response(self, prompt: str) -> Result[Dict[str, Any]]:
        """Generate a response from a prompt."""
        ...
        
    async def generate_response_streaming(self, prompt: str) -> AsyncGenerator[str, None]:
        """Generate a streaming response from a prompt."""
        ...

@dataclass
class RetrievedChunk:
    """Data class representing a retrieved chunk with relevance score."""
    content: str
    metadata: Dict[str, Any]
    relevance_score: float

class RAG:
    """
    Retrieval-Augmented Generation system.
    
    This class implements the complete RAG pipeline, handling:
    1. Document retrieval from vector stores
    2. Prompt construction with retrieved context
    3. Response generation with attribution
    4. Conversation context management
    """
    
    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        llm_provider: Optional[LLMProvider] = None,
        prompt_template: Optional[str] = None,
        top_k: int = 3,
    ):
        """
        Initialize the RAG system.
        
        Args:
            vector_store: Optional vector store for document retrieval
            llm_provider: Optional LLM provider for response generation
            prompt_template: Optional custom prompt template
            top_k: Default number of chunks to retrieve
        """
        self.vector_store = vector_store or VectorStore()
        self.llm_provider = llm_provider
        self.prompt_template = prompt_template
        self.default_top_k = top_k
        self.knowledge_keywords = [
            r"\bpolicy\b", r"\bpolicies\b", r"\bbenefits?\b", 
            r"\bleave\b", r"\btime\s+off\b", r"\bPTO\b", r"\bvacation\b",
            r"\bhealth\s+insurance\b", r"\b401k\b", r"\bretirement\b",
            r"\btraining\b", r"\bcourses?\b", r"\blearn\b", r"\bdevelopment\b",
            r"\bonboarding\b", r"\bsalary\b", r"\bpay\b", r"\bcompensation\b"
        ]
        logger.info("Initialized RAG system")
    
    async def query(
        self,
        query: str,
        user_id: str = "anonymous",
        chat_history: Optional[List[str]] = None,
        top_k: Optional[int] = None,
    ) -> Result[Dict[str, Any]]:
        """
        Process a query through the RAG pipeline.
        
        Args:
            query: The user's query
            user_id: User identifier for tracking
            chat_history: Optional chat history
            top_k: Number of documents to retrieve (defaults to self.default_top_k)
            
        Returns:
            Result containing response and retrieved sources
        """
        try:
            logger.info(f"[RAG] Processing query: {query}")
            
            # Use default top_k if not specified
            if top_k is None:
                top_k = self.default_top_k
            
            # Retrieve relevant documents
            retrieved_chunks = await self._retrieve_documents(query, top_k)
            
            if not retrieved_chunks:
                logger.warning(f"[RAG] No relevant chunks found for query: {query}")
            
            # Format retrieved chunks for prompt
            context = self._format_chunks_for_prompt(retrieved_chunks)
            
            # Build prompt with context
            prompt = self._build_prompt(query, context, chat_history)
            logger.info(f"[RAG] Built prompt with {len(prompt)} characters")
            
            # Generate response
            if not self.llm_provider:
                return Error(RAGError(
                    code=ErrorCode.LLM_UNAVAILABLE,
                    message="LLM provider not configured for RAG system",
                    user_message="The AI processing system is currently unavailable."
                ))
                
            result = await self.llm_provider.generate_response(prompt)
            
            if result.is_error():
                logger.error(f"[RAG] LLM error: {result.error}")
                return result
            
            # Add sources and metadata to response
            response_data = result.unwrap()
            response_data["sources"] = self._extract_sources(retrieved_chunks)
            response_data["used_rag"] = True
            response_data["user_id"] = user_id
            
            logger.info(f"[RAG] Generated response successfully")
            return Success(response_data)
            
        except Exception as e:
            logger.error(f"[RAG] Error in RAG query: {str(e)}")
            return Error(RAGError(
                code=ErrorCode.QUERY_PROCESSING_ERROR,
                message=f"RAG pipeline error: {str(e)}",
                user_message="I encountered an issue while processing your question."
            ))
    
    async def query_streaming(
        self,
        query: str,
        user_id: str = "anonymous",
        chat_history: Optional[List[str]] = None,
        top_k: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Process a query with streaming response.
        
        Args:
            query: The user's query
            user_id: User identifier for tracking
            chat_history: Optional chat history
            top_k: Number of documents to retrieve (defaults to self.default_top_k)
            
        Yields:
            Chunks of the response as they are generated
        """
        try:
            logger.info(f"[RAG] Processing streaming query: {query}")
            
            # Use default top_k if not specified
            if top_k is None:
                top_k = self.default_top_k
            
            # Retrieve relevant documents
            retrieved_chunks = await self._retrieve_documents(query, top_k)
            
            # Format retrieved chunks for prompt
            context = self._format_chunks_for_prompt(retrieved_chunks)
            
            # Build prompt with context
            prompt = self._build_prompt(query, context, chat_history)
            
            # Generate streaming response
            if not self.llm_provider:
                yield "I'm sorry, but the AI processing system is currently unavailable."
                return
                
            # Log sources for potential later use
            sources = self._extract_sources(retrieved_chunks)
            logger.info(f"[RAG] Retrieved {len(sources)} sources for query")
            
            # Stream the response
            async for chunk in self.llm_provider.generate_response_streaming(prompt):
                yield chunk
                
        except Exception as e:
            logger.error(f"[RAG] Error in streaming query: {str(e)}")
            yield "I encountered an issue while processing your question."
    
    async def _retrieve_documents(self, query: str, top_k: int) -> List[RetrievedChunk]:
        """
        Retrieve relevant documents for a query.
        
        Args:
            query: The search query
            top_k: Number of documents to retrieve
            
        Returns:
            List of RetrievedChunk objects
        """
        try:
            # initial pool 3x size
            pool = await self.vector_store.similarity_search(query, top_k=top_k * 3)

            # simple greedy MMR based on cosine ordering
            docs: List[Document] = []
            for doc in pool:
                # filter by metadata if user org supports
                # e.g. department filter omitted for brevity
                docs.append(doc)
                if len(docs) == top_k:
                    break
            
            # Convert to RetrievedChunk objects with scores
            chunks: List[RetrievedChunk] = []
            for i, doc in enumerate(docs):
                # Use relevance score if available, otherwise use position-based score
                relevance_score = doc.metadata.get("relevance_score", 1.0 - (i / max(len(docs), 1)))
                chunks.append(RetrievedChunk(
                    content=doc.page_content,
                    metadata=doc.metadata,
                    relevance_score=relevance_score
                ))
            
            # Mark fallback flag
            if getattr(self.vector_store, "embeddings_model", None) is None:
                for c in chunks:
                    c.metadata["fallback"] = True
            return chunks
        except Exception as e:
            logger.error(f"[RAG] Error retrieving documents: {str(e)}")
            return []
    
    def _format_chunks_for_prompt(self, chunks: List[RetrievedChunk]) -> str:
        """
        Format retrieved chunks for inclusion in the prompt.
        
        Args:
            chunks: List of RetrievedChunk objects
            
        Returns:
            Formatted string for prompt
        """
        if not chunks:
            return "No relevant information found."
        
        formatted = []
        for i, chunk in enumerate(chunks):
            # Extract source and chunk metadata
            source = chunk.metadata.get("source", "Unknown source")
            chunk_num = chunk.metadata.get("chunk", i+1)
            
            # Format with source attribution
            formatted.append(f"[Document: {source}, Chunk: {chunk_num}]\n{chunk.content}")
        
        return "\n\n".join(formatted)
    
    def _build_prompt(self, query: str, context: str, chat_history: Optional[List[str]]) -> str:
        """
        Build a prompt with query, context, and chat history.
        
        Args:
            query: The user's query
            context: Retrieved context
            chat_history: Optional chat history
            
        Returns:
            Formatted prompt string
        """
        if self.prompt_template:
            template = self.prompt_template
        else:
            template = (
                "<SYSTEM>\nYou are an HR assistant bot. Answer using the knowledge provided. If unsure say you don't know.\n</SYSTEM>\n"
                "<KNOWLEDGE>\n{context}\n</KNOWLEDGE>\n"
                "<HISTORY>\n{history}\n</HISTORY>\n"
                "<USER>{query}</USER>\n"
                "<BOT>"
            )

        history_text = "\n".join(chat_history) if chat_history else ""
        return template.format(context=context, history=history_text, query=query)
    
    def _extract_sources(self, chunks: List[RetrievedChunk]) -> List[Dict[str, Any]]:
        """
        Extract source information from chunks for attribution.
        
        Args:
            chunks: List of RetrievedChunk objects
            
        Returns:
            List of source dictionaries
        """
        if chunks and chunks[0].metadata.get("fallback"):
            return []

        sources = []
        seen_sources: Set[str] = set()
        
        for chunk in chunks:
            source = chunk.metadata.get("source")
            if source and source not in seen_sources:
                sources.append({
                    "title": source,
                    "path": chunk.metadata.get("file_path", ""),
                    "type": chunk.metadata.get("file_type", ""),
                    "relevance": round(chunk.relevance_score, 2)
                })
                seen_sources.add(source)
        
        return sources
    
    def should_use_rag(self, query: str, chat_history: Optional[List[str]] = None) -> bool:
        """
        Determine if a query should use RAG based on content analysis.
        
        Args:
            query: The user's query
            chat_history: Optional conversation history
            
        Returns:
            True if RAG should be used, False otherwise
        """
        # Always use RAG for longer, complex queries
        if len(query.split()) > 8:
            return True
            
        # Check for knowledge-related keywords
        lower_query = query.lower()
        for pattern in self.knowledge_keywords:
            if re.search(pattern, lower_query):
                return True
                
        # Check for question indicators
        question_indicators = ["?", "how", "what", "when", "where", "which", "who", "why", "can", "could", "tell me about"]
        for indicator in question_indicators:
            if indicator in lower_query:
                return True
                
        # For short messages with no clear knowledge need, don't use RAG
        return False