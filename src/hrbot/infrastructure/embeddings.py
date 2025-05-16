"""
Direct embedding implementation using Google Vertex AI.

This module provides a custom embeddings implementation that uses
the Vertex AI SDK directly rather than relying on LangChain's wrappers.
"""

import logging
import numpy as np
from typing import List, Any, Optional
from hrbot.config.settings import settings

# Import Vertex AI SDK
from google.cloud import aiplatform
from vertexai.preview.language_models import TextEmbeddingModel

logger = logging.getLogger(__name__)

class VertexDirectEmbeddings:
    """
    Custom embeddings implementation using Vertex AI directly.
    
    This class bypasses LangChain's VertexAIEmbeddings implementation and
    uses the Vertex AI Python SDK directly, allowing us to use newer models
    like text-embedding-005 which may not be supported in LangChain yet.
    """
    
    def __init__(
        self,
        model_name: str = "text-embedding-005",
        project: Optional[str] = None,
        location: str = "us-central1",
        **kwargs
    ):
        """
        Initialize the embeddings model.
        
        Args:
            model_name: Name of the embedding model to use
            project: Google Cloud project ID
            location: Google Cloud location
            **kwargs: Additional arguments to pass to the model
        """
        self.model_name = model_name
        self.project = project or settings.google_cloud.project_id
        self.location = location or settings.google_cloud.location
        self.model = None
        self.dimension = 768  # Default dimension for text-embedding-005
        
        # Initialize the model
        self.initialize_model()
        
    def initialize_model(self):
        """Initialize the Vertex AI embedding model."""
        try:
            # Initialize Vertex AI with project settings
            aiplatform.init(
                project=self.project,
                location=self.location
            )
            
            # Load the embedding model
            logger.info(f"Initializing embedding model: {self.model_name}")
            self.model = TextEmbeddingModel.from_pretrained(self.model_name)
            logger.info(f"Successfully initialized embedding model: {self.model_name}")
            
            # Test the model with a simple input to verify and get dimensions
            test_result = self.model.get_embeddings(["Test embedding initialization"])
            if len(test_result) > 0:
                embedding_values = test_result[0].values
                self.dimension = len(embedding_values)
                logger.info(f"Embedding dimension: {self.dimension}")
            
        except Exception as e:
            logger.error(f"Error initializing embedding model: {str(e)}")
            raise
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of documents.
        
        Args:
            texts: List of document texts to embed
            
        Returns:
            List of embeddings as float arrays
        """
        try:
            if not self.model:
                self.initialize_model()
                
            if not texts:
                return []
                
            # Process in batches if needed (API may have limits)
            batch_size = 5  # Adjust based on API limits
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i+batch_size]
                response = self.model.get_embeddings(batch)
                batch_embeddings = [emb.values for emb in response]
                all_embeddings.extend(batch_embeddings)
                
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Error in embed_documents: {str(e)}")
            raise
    
    def embed_query(self, text: str) -> List[float]:
        """
        Generate embedding for a single query text.
        
        Args:
            text: The query text to embed
            
        Returns:
            Embedding as a float array
        """
        try:
            if not self.model:
                self.initialize_model()
                
            response = self.model.get_embeddings([text])
            return response[0].values
            
        except Exception as e:
            logger.error(f"Error in embed_query: {str(e)}")
            raise 