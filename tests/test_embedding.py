#!/usr/bin/env python
"""
Simple test script to verify Vertex AI embedding models are working.
Run with: python test_embedding.py
"""

import os
import sys
from google.cloud import aiplatform
from vertexai.preview.language_models import TextEmbeddingModel

# Initialize Vertex AI with your project details
aiplatform.init(
    project="gemini-deployment",
    location="us-central1",
)

def test_embedding_model(model_name="text-embedding-005"):
    """Test if embedding model works by getting embeddings for a sample text."""
    try:
        print(f"Initializing embedding model: {model_name}")
        model = TextEmbeddingModel.from_pretrained(model_name)
        
        # Test with simple text
        sample_text = "Hello, this is a test for embedding models."
        print(f"Getting embeddings for text: '{sample_text}'")
        
        response = model.get_embeddings([sample_text])
        print(f"Response type: {type(response)}")
        
        # Handle different response formats based on model version
        if isinstance(response, list):
            # Direct list format
            embedding_values = response[0].values
            print(f"Embedding dimension: {len(embedding_values)}")
            print(f"First 5 values: {embedding_values[:5]}")
        else:
            # Object with embeddings attribute
            print(f"Response attributes: {dir(response)}")
            if hasattr(response, 'embeddings'):
                embeddings = response.embeddings
                print(f"Embeddings type: {type(embeddings)}")
                print(f"Embeddings attributes: {dir(embeddings[0])}")
                embedding_values = embeddings[0].values
                print(f"Embedding dimension: {len(embedding_values)}")
                print(f"First 5 values: {embedding_values[:5]}")
            else:
                print(f"Unknown response format: {response}")
        
        print(f"Success! {model_name} is working properly.")
        return True
        
    except Exception as e:
        print(f"Error testing embedding model: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_all_models():
    """Test multiple embedding models to see which ones work."""
    models_to_test = [
        "text-embedding-005",
        "text-embedding-004",
        "text-embedding-003",
        "textembedding-gecko@latest",
        "textembedding-gecko-multilingual@latest"
    ]
    
    results = {}
    for model in models_to_test:
        print(f"\n{'='*50}")
        print(f"Testing model: {model}")
        result = test_embedding_model(model)
        results[model] = "✅ WORKS" if result else "❌ FAILED"
    
    # Print summary
    print("\n\n" + "="*50)
    print("EMBEDDING MODEL TEST SUMMARY")
    print("="*50)
    for model, status in results.items():
        print(f"{model}: {status}")

if __name__ == "__main__":
    # Test a specific model if provided as argument
    if len(sys.argv) > 1:
        model_name = sys.argv[1]
        test_embedding_model(model_name)
    else:
        # Otherwise test all models
        test_all_models() 