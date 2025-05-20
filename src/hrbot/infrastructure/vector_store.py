"""
Vector store implementation for document embeddings and semantic search.

This module provides a vector store implementation that can be used to:
1. Generate and store embeddings for document chunks
2. Perform semantic similarity search to find relevant context
3. Work with numpy for vector operations (no FAISS dependency)

It implements a production-ready vector database with both in-memory and persistent storage options.
"""

import os
import logging
import pickle
import numpy as np
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime
from hrbot.core.document import Document

# Custom embeddings implementation using Vertex AI directly
from hrbot.infrastructure.embeddings import VertexDirectEmbeddings
from hrbot.config.settings import settings

logger = logging.getLogger(__name__)

class VectorStore:
    """
    Simple vector store for semantic search using numpy and Google Vertex AI embeddings.
    
    This class handles:
    1. Document storage and embedding with Google Vertex AI
    2. Similarity search for finding relevant documents
    3. Persistence to disk for document embedding cache
    """
    
    def __init__(self, collection_name: str = "hr_documents"):
        """
        Initialize the vector store.
        
        Args:
            collection_name: Name to identify this collection of documents
        """
        self.collection_name = collection_name
        self.data_dir = Path("data/embeddings")
        self.embedding_path = self.data_dir / f"{collection_name}_embeddings.npy"
        self.docstore_path = self.data_dir / f"{collection_name}_docs.pkl"
        self.embeddings_model = None
        self.document_embeddings = None  # numpy array of embeddings
        self.documents = []  # list of Document objects
        self.initialized = False
        self._initialize()
        
    def _initialize(self):
        """Initialize the embedding model and vector store."""
        try:
            # Initialize embedding model
            logger.info(f"[VECTOR DEBUG] Initializing embedding model for {self.collection_name}")
            
            # Use our custom direct embedding implementation
            try:
                self.embeddings_model = VertexDirectEmbeddings(
                    model_name=settings.embeddings.model_name,
                    project=settings.google_cloud.project_id,
                    location=settings.google_cloud.location
                )
                logger.info(f"[VECTOR DEBUG] Successfully initialized embeddings with model: {self.embeddings_model.model_name}")
            except Exception as e:
                logger.error(f"[VECTOR DEBUG] Error initializing embeddings: {str(e)}")
                raise
            
            # Try to load existing embeddings and documents
            logger.info(f"[VECTOR DEBUG] Checking for existing embeddings at {self.embedding_path}")
            if self._load_from_disk():
                logger.info(f"[VECTOR DEBUG] Loaded existing vector store with {len(self.documents)} documents")
            else:
                # Initialize empty arrays
                logger.info(f"[VECTOR DEBUG] Creating new empty vector store")
                # Handle case where embeddings_model might be None in fallback scenario
                dim = getattr(self.embeddings_model, 'dimension', 768)
                self.document_embeddings = np.array([], dtype=np.float32).reshape(0, dim)
                self.documents = []
                self._save_to_disk()
                
            self.initialized = True
            
        except Exception as e:
            logger.error(f"[VECTOR DEBUG] Error initializing vector store: {str(e)}")
            # Use fallback in-memory storage without embeddings
            logger.warning("Using fallback in-memory vector store without embeddings")
            self.document_embeddings = None
            self.documents = []
            self.initialized = True  # Set to true so we can still operate in fallback mode

    async def warmup(self) -> None:
        """
        Pre-load any resources needed at runtime.

        By default this just ensures the store is initialised and, if
        embeddings are on disk, reads them once so the first real query
        is fast.  Override in subclasses if you need heavier logic.
        """
        if not self.initialized:
            self._initialize()

        # Force a tiny cosine-similarity pass to pull the entire NumPy
        # array into memory (OS cache → RAM).
        if (
            self.document_embeddings is not None
            and len(self.document_embeddings) > 0
        ):
            _ = float(np.dot(self.document_embeddings[0], self.document_embeddings[0]))
    
    def _load_from_disk(self) -> bool:
        """
        Load vector store from disk.
        
        Returns:
            bool: True if loaded successfully
        """
        try:
            if self.embedding_path.exists() and self.docstore_path.exists():
                # Load document embeddings & pre-normalise (unit vectors)
                raw = np.load(self.embedding_path)
                norm = np.linalg.norm(raw, axis=1, keepdims=True)
                norm[norm == 0] = 1.0
                self.document_embeddings = raw / norm
                
                # Load document list
                with open(self.docstore_path, 'rb') as f:
                    self.documents = pickle.load(f)
                    
                logger.info(f"[VECTOR DEBUG] Loaded {len(self.documents)} documents from disk")
                return True
            return False
        except Exception as e:
            logger.error(f"[VECTOR DEBUG] Error loading vector store from disk: {str(e)}")
            return False
    
    def _save_to_disk(self):
        """Save vector store to disk."""
        try:
            if self.initialized and self.documents:
                logger.info(f"[VECTOR DEBUG] Saving vector store to disk")
                
                # Create directory if it doesn't exist
                self.data_dir.mkdir(parents=True, exist_ok=True)
                
                # Save embeddings if we have them
                if self.document_embeddings is not None and len(self.document_embeddings) > 0:
                    np.save(self.embedding_path, self.document_embeddings)
                
                # Save document list
                with open(self.docstore_path, 'wb') as f:
                    pickle.dump(self.documents, f)
                
                logger.info(f"[VECTOR DEBUG] Successfully saved vector store with {len(self.documents)} documents")
        except Exception as e:
            logger.error(f"[VECTOR DEBUG] Error saving vector store to disk: {str(e)}")
    
    async def add_documents(self, documents: List[Document]) -> bool:
        """
        Add documents to the vector store.
        
        Args:
            documents: List of Document objects to add
            
        Returns:
            bool: True if successful
        """
        try:
            if not documents:
                logger.warning("[VECTOR DEBUG] No documents to add")
                return False
                
            if not self.initialized:
                logger.error("[VECTOR DEBUG] Vector store not initialized")
                return False
                
            if self.embeddings_model:
                # Generate embeddings for documents (offloaded)
                logger.info(f"[VECTOR DEBUG] Generating embeddings for {len(documents)} documents")
                texts = [doc.page_content for doc in documents]
                new_embeddings = await asyncio.to_thread(self.embeddings_model.embed_documents, texts)
                
                # Convert & normalise
                new_embeddings_array = np.array(new_embeddings, dtype=np.float32)
                norms = np.linalg.norm(new_embeddings_array, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                new_embeddings_array = new_embeddings_array / norms
                
                # Add to existing embeddings
                if self.document_embeddings is not None and len(self.document_embeddings) > 0:
                    self.document_embeddings = np.vstack([self.document_embeddings, new_embeddings_array])
                else:
                    self.document_embeddings = new_embeddings_array
                
                # Add to document list
                self.documents.extend(documents)
                
                # Save to disk
                self._save_to_disk()
                
                logger.info(f"[VECTOR DEBUG] Successfully added {len(documents)} documents")
                return True
            else:
                # Fallback to just storing documents in memory without embeddings
                logger.warning("[VECTOR DEBUG] Using fallback storage (no embeddings)")
                self.documents.extend(documents)
                return True
                
        except Exception as e:
            logger.error(f"[VECTOR DEBUG] Error adding documents: {str(e)}")
            return False
    
    async def similarity_search(self, query: str, top_k: int = 5) -> List[Document]:
        """
        Perform similarity search for a query using cosine similarity.
        
        Args:
            query: The query string
            top_k: Number of results to return
            
        Returns:
            List of Document objects
        """
        try:
            if not self.initialized:
                logger.error("[VECTOR DEBUG] Vector store not initialized")
                return []
                
            if (self.embeddings_model and 
                self.document_embeddings is not None and 
                len(self.document_embeddings) > 0 and 
                len(self.documents) > 0):
                
                # Generate & normalise embedding for query
                logger.info(f"[VECTOR DEBUG] Generating embedding for query: {query[:50]}...")
                query_emb = await asyncio.to_thread(self.embeddings_model.embed_query, query)
                query_emb = np.array(query_emb, dtype=np.float32)
                query_emb = query_emb / (np.linalg.norm(query_emb) or 1.0)
                similarities = np.dot(self.document_embeddings, query_emb)
                
                # Get top-k indices
                top_indices = np.argsort(similarities)[-top_k:][::-1]
                
                # Get documents for top indices
                results = [self.documents[i] for i in top_indices]
                
                logger.info(f"[VECTOR DEBUG] Found {len(results)} results")
                return results
            else:
                # Fallback to basic keyword search
                logger.warning("Using fallback keyword search instead of semantic search")
                return self._fallback_keyword_search(query, top_k)
                
        except Exception as e:
            logger.error(f"[VECTOR DEBUG] Error in similarity search: {str(e)}")
            # Fallback to keyword search
            return self._fallback_keyword_search(query, top_k)
    
    def _fallback_keyword_search(self, query: str, top_k: int = 5) -> List[Document]:
        """
        Fallback keyword search when vector search is unavailable.
        
        Args:
            query: The query string
            top_k: Number of results to return
            
        Returns:
            List of Document objects
        """
        try:
            if not self.documents:
                return []
                
            # Simple keyword matching
            query_terms = query.lower().split()
            results = []
            
            for doc in self.documents:
                content = doc.page_content.lower()
                # Count how many query terms appear in the document
                matches = sum(1 for term in query_terms if term in content)
                if matches > 0:
                    results.append((doc, matches))
            
            # Sort by number of matches (descending)
            results.sort(key=lambda x: x[1], reverse=True)
            
            # Return top_k documents
            return [doc for doc, _ in results[:top_k]]
            
        except Exception as e:
            logger.error(f"[VECTOR DEBUG] Error in fallback search: {str(e)}")
            return []
    
    async def delete_collection(self) -> bool:
        """
        Delete the entire collection.
        
        Returns:
            bool: True if successful
        """
        try:
            # Reset in-memory store
            dim = getattr(self.embeddings_model, 'dimension', 768)
            self.document_embeddings = np.array([], dtype=np.float32).reshape(0, dim)
            self.documents = []
            
            # Delete files if they exist
            if self.embedding_path.exists():
                os.remove(self.embedding_path)
            if self.docstore_path.exists():
                os.remove(self.docstore_path)
                
            logger.info(f"[VECTOR DEBUG] Deleted vector store collection: {self.collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"[VECTOR DEBUG] Error deleting collection: {str(e)}")
            return False 