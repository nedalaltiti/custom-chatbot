#!/usr/bin/env python
"""
Load/reload embeddings for app instances.

Usage:
    python scripts/load_embeddings.py jordan
    python scripts/load_embeddings.py us
"""

import os
import sys
import asyncio
import argparse

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def load_embeddings(instance: str):
    # Set the app instance
    os.environ['APP_INSTANCE'] = instance
    
    print(f"\nLoading embeddings for {instance.upper()} instance...")
    print("="*60)
    
    # Import after setting environment
    from src.hrbot.utils.di import get_vector_store
    from src.hrbot.infrastructure.ingest import refresh_vector_index
    from src.hrbot.config.app_config import get_current_app_config
    
    # Get app config
    app_config = get_current_app_config()
    print(f"App: {app_config.name}")
    print(f"Knowledge: {app_config.knowledge_base_dir}")
    print(f"Embeddings: {app_config.embeddings_dir}")
    
    # Check if knowledge directory has files
    if not app_config.knowledge_base_dir.exists():
        print(f"\n❌ Knowledge directory does not exist: {app_config.knowledge_base_dir}")
        print(f"   Please add some documents to this directory first.")
        return
        
    files = list(app_config.knowledge_base_dir.glob("*"))
    if not files:
        print(f"\n❌ No files found in knowledge directory: {app_config.knowledge_base_dir}")
        print(f"   Please add some documents to this directory first.")
        return
        
    print(f"\nFound {len(files)} files in knowledge directory")
    
    # Get vector store (this will use the app-specific directory)
    print("\nInitializing vector store...")
    vector_store = get_vector_store()
    
    # Check current status
    existing_docs = len(vector_store.documents)
    print(f"Current documents in vector store: {existing_docs}")
    
    # Refresh the index
    print("\nRefreshing vector index...")
    new_docs = await refresh_vector_index(vector_store)
    
    if new_docs > 0:
        print(f"\n✅ Successfully indexed {new_docs} new documents!")
    else:
        print(f"\n✅ All documents are already indexed.")
        
    # Final status
    print(f"\nTotal documents in vector store: {len(vector_store.documents)}")
    
    # Check embeddings files
    embeddings_files = list(app_config.embeddings_dir.glob("*.npz"))
    if embeddings_files:
        print(f"Embeddings saved to: {app_config.embeddings_dir}")
        for f in embeddings_files:
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  - {f.name} ({size_mb:.2f} MB)")


def main():
    parser = argparse.ArgumentParser(description="Load embeddings for app instance")
    parser.add_argument(
        "instance",
        choices=["jordan", "us"],
        help="App instance to load embeddings for"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reload all documents (clear existing embeddings)"
    )
    
    args = parser.parse_args()
    
    if args.force:
        # Set environment before importing
        os.environ['APP_INSTANCE'] = args.instance
        
        from src.hrbot.utils.di import get_vector_store
        print(f"\n⚠️  Clearing existing embeddings for {args.instance}...")
        vector_store = get_vector_store()
        asyncio.run(vector_store.clear())
        print("✅ Cleared existing embeddings")
    
    # Load embeddings
    asyncio.run(load_embeddings(args.instance))


if __name__ == "__main__":
    main() 