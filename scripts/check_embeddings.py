#!/usr/bin/env python
"""
Check embeddings status for app instances.

Usage:
    python scripts/check_embeddings.py
"""

import os
import sys
from pathlib import Path

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.hrbot.config.app_config import get_instance_manager

def check_embeddings_for_instance(instance_name: str):
    """Check if embeddings exist for the given instance."""
    print(f"\n=== Checking embeddings for {instance_name} ===")
    
    manager = get_instance_manager()
    config = manager.get_instance(instance_name)
    
    if not config:
        print(f"❌ Invalid instance: {instance_name}")
        print(f"Available instances: {list(manager.get_all_instances().keys())}")
        return
    
    embeddings_dir = config.embeddings_dir
    print(f"Embeddings directory: {embeddings_dir}")

def check_embeddings():
    """Check embeddings status for all app instances."""
    print("Checking embeddings status for all app instances...\n")
    
    manager = get_instance_manager()
    all_instances = manager.get_all_instances()
    
    for instance_id, config in all_instances.items():
        print(f"{'='*60}")
        print(f"App Instance: {instance_id} ({config.name})")
        print(f"{'='*60}")
        
        # Check knowledge directory
        knowledge_dir = config.knowledge_base_dir
        print(f"Knowledge Directory: {knowledge_dir}")
        if knowledge_dir.exists():
            files = list(knowledge_dir.iterdir())
            print(f"  ✓ Exists - {len(files)} files")
            for f in files[:3]:
                print(f"    - {f.name}")
            if len(files) > 3:
                print(f"    ... and {len(files) - 3} more files")
        else:
            print(f"  ✗ Does not exist!")
            
        # Check embeddings directory
        embeddings_dir = config.embeddings_dir
        print(f"\nEmbeddings Directory: {embeddings_dir}")
        if embeddings_dir.exists():
            npz_files = list(embeddings_dir.glob("*.npz"))
            pkl_files = list(embeddings_dir.glob("*.pkl"))
            print(f"  ✓ Exists")
            print(f"    - {len(npz_files)} .npz files (embeddings)")
            print(f"    - {len(pkl_files)} .pkl files (document metadata)")
            
            if npz_files:
                # Show file sizes
                for f in npz_files[:2]:
                    size_mb = f.stat().st_size / (1024 * 1024)
                    print(f"      • {f.name} ({size_mb:.2f} MB)")
        else:
            print(f"  ✗ Does not exist!")
            
        # Check prompts directory
        prompt_dir = config.prompt_dir
        print(f"\nPrompts Directory: {prompt_dir}")
        if prompt_dir.exists():
            prompt_file = prompt_dir / "prompt.py"
            if prompt_file.exists():
                print(f"  ✓ Custom prompt exists")
            else:
                print(f"  ⚠ No custom prompt (will use default)")
        else:
            print(f"  ✗ Does not exist!")
            
        print("\n")


if __name__ == "__main__":
    check_embeddings() 