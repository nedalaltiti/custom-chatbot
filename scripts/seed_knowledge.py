"""
This script is used to seed the knowledge base with initial documents.

Features:
1. Batch processing of documents from directories
2. Support for multiple file formats (PDF, DOCX, TXT)
3. Progress tracking and reporting
4. Post-processing validation
"""

import os
import sys
import argparse
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime
import time
import json
import mimetypes

# Add the parent directory to the Python path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.hrbot.core.chunking import process_document
from src.hrbot.infrastructure.vector_store import VectorStore
from src.hrbot.utils.error import DocumentError, ErrorCode

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("seed_knowledge")

# Supported file extensions and their MIME types
SUPPORTED_FORMATS = {
    # PDF files
    '.pdf': 'application/pdf',
    
    # Microsoft Office formats
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.ppt': 'application/vnd.ms-powerpoint',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    
    # Text formats
    '.txt': 'text/plain',
    '.md': 'text/markdown',
    '.csv': 'text/csv',
    '.json': 'application/json',
    '.html': 'text/html',
    '.htm': 'text/html',
    '.xml': 'application/xml',
}

def is_supported_file(file_path: Path) -> bool:
    """
    Check if a file is supported for knowledge extraction.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if supported, False otherwise
    """
    # Check extension first (fast check)
    if file_path.suffix.lower() in SUPPORTED_FORMATS:
        return True
    
    # Fallback to MIME type detection
    try:
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type in SUPPORTED_FORMATS.values()
    except:
        return False

def check_environment() -> Tuple[bool, Optional[str]]:
    """
    Check if the environment is properly set up.
    
    Returns:
        Tuple of (success, error_message)
    """
    # Check that the knowledge directory exists
    knowledge_dir = Path("data/knowledge")
    if not knowledge_dir.exists():
        return False, f"Knowledge directory not found: {knowledge_dir}. Create it with: mkdir -p data/knowledge"
    
    # Check that Google credentials are set
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return False, "GOOGLE_APPLICATION_CREDENTIALS not set. Please set it to your credentials file path."
    
    # Check that the credentials file exists
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path and not Path(creds_path).exists():
        return False, f"Credentials file not found: {creds_path}"
    
    return True, None

async def process_file(file_path: Path, vector_store: VectorStore) -> Dict[str, Any]:
    """
    Process a single file and add it to the vector store.
    
    Args:
        file_path: Path to the file
        vector_store: Vector store instance
        
    Returns:
        Dictionary with processing statistics
    """
    start_time = time.time()
    logger.info(f"Processing file: {file_path}")
    
    try:
        # Check if file exists
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Check if file is supported
        if not is_supported_file(file_path):
            raise DocumentError(
                code=ErrorCode.UNSUPPORTED_FORMAT,
                message=f"Unsupported file format: {file_path.suffix}",
                details={"file": str(file_path)}
            )
        
        # Process document into chunks
        chunks = await process_document(str(file_path))
        
        if not chunks:
            logger.warning(f"No chunks extracted from {file_path}")
            return {
                "file": str(file_path),
                "status": "warning",
                "chunks": 0,
                "time_seconds": time.time() - start_time,
                "message": "No chunks extracted"
            }
        
        # Add chunks to vector store
        success = await vector_store.add_documents(chunks)
        
        if not success:
            logger.error(f"Failed to add chunks from {file_path} to vector store")
            return {
                "file": str(file_path),
                "status": "error",
                "chunks": len(chunks),
                "time_seconds": time.time() - start_time,
                "message": "Failed to add to vector store"
            }
        
        logger.info(f"Successfully processed {file_path}: {len(chunks)} chunks")
        return {
            "file": str(file_path),
            "status": "success",
            "chunks": len(chunks),
            "time_seconds": time.time() - start_time,
            "message": "Successfully processed"
        }
        
    except DocumentError as e:
        logger.error(f"Document error processing {file_path}: {e.message}")
        return {
            "file": str(file_path),
            "status": "error",
            "chunks": 0,
            "time_seconds": time.time() - start_time,
            "message": f"Document error: {e.message}",
            "error_code": e.code.name if hasattr(e, 'code') else "UNKNOWN"
        }
    except Exception as e:
        logger.error(f"Error processing {file_path}: {str(e)}")
        return {
            "file": str(file_path),
            "status": "error",
            "chunks": 0,
            "time_seconds": time.time() - start_time,
            "message": f"Error: {str(e)}"
        }

async def process_directory(directory: Path, vector_store: VectorStore, recursive: bool = False) -> List[Dict[str, Any]]:
    """
    Process all files in a directory.
    
    Args:
        directory: Directory path
        vector_store: Vector store instance
        recursive: Whether to process subdirectories
        
    Returns:
        List of dictionaries with processing statistics
    """
    logger.info(f"Processing directory: {directory} (recursive: {recursive})")
    
    # Check if directory exists
    if not directory.exists() or not directory.is_dir():
        logger.error(f"Directory not found or not a directory: {directory}")
        return []
    
    # Get all files
    pattern = "**/*" if recursive else "*"
    files = []
    
    for path in directory.glob(pattern):
        if path.is_file() and is_supported_file(path):
            files.append(path)
    
    logger.info(f"Found {len(files)} supported files to process")
    
    # Process files with progress tracking
    results = []
    for i, file_path in enumerate(files, 1):
        logger.info(f"Processing file {i}/{len(files)}: {file_path.name}")
        result = await process_file(file_path, vector_store)
        results.append(result)
        
        # Log progress
        successful = sum(1 for r in results if r['status'] == 'success')
        errors = sum(1 for r in results if r['status'] == 'error')
        logger.info(f"Progress: {i}/{len(files)} files, {successful} successful, {errors} errors")
    
    return results

async def main():
    """Main function for seeding the knowledge base."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Seed the knowledge base with documents")
    parser.add_argument(
        "source",
        help="File or directory path with documents to process"
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Process subdirectories recursively"
    )
    parser.add_argument(
        "-o", "--output",
        help="Path to save processing report (JSON)",
        default=None
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset vector store before processing"
    )
    parser.add_argument(
        "--collection-name",
        default="hr_documents",
        help="Name of the vector store collection"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan files without processing them (for testing)"
    )
    
    args = parser.parse_args()
    
    # Check environment
    env_ok, env_error = check_environment()
    if not env_ok:
        logger.error(f"Environment check failed: {env_error}")
        sys.exit(1)
    
    # Initialize vector store (unless dry run)
    vector_store = None
    if not args.dry_run:
        try:
            vector_store = VectorStore(collection_name=args.collection_name)
            
            # Reset vector store if requested
            if args.reset:
                logger.info("Resetting vector store...")
                await vector_store.delete_collection()
                logger.info("Vector store reset complete")
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {str(e)}")
            sys.exit(1)
    
    # Process source
    source_path = Path(args.source).resolve()
    results = []
    
    if args.dry_run:
        logger.info(f"DRY RUN: Scanning files without processing them")
        
        # Just scan for supported files
        if source_path.is_file():
            if is_supported_file(source_path):
                logger.info(f"File would be processed: {source_path}")
                results = [{
                    "file": str(source_path),
                    "status": "would_process",
                    "message": "File would be processed (dry run)"
                }]
            else:
                logger.warning(f"File would be skipped (unsupported format): {source_path}")
                results = [{
                    "file": str(source_path),
                    "status": "would_skip",
                    "message": f"Unsupported file format: {source_path.suffix}"
                }]
        elif source_path.is_dir():
            # Scan directory for supported files
            pattern = "**/*" if args.recursive else "*"
            files = []
            
            for path in source_path.glob(pattern):
                if path.is_file():
                    if is_supported_file(path):
                        logger.info(f"File would be processed: {path}")
                        files.append(path)
                    else:
                        logger.debug(f"File would be skipped (unsupported): {path}")
                        
            logger.info(f"Would process {len(files)} files from directory: {source_path}")
            results = [{"file": str(path), "status": "would_process"} for path in files]
        else:
            logger.error(f"Source not found: {source_path}")
            sys.exit(1)
    else:
        # Actually process files
        if source_path.is_file():
            # Process single file
            results = [await process_file(source_path, vector_store)]
        elif source_path.is_dir():
            # Process directory
            results = await process_directory(source_path, vector_store, args.recursive)
        else:
            logger.error(f"Source not found: {source_path}")
            sys.exit(1)
    
    # Generate report
    total_files = len(results)
    successful_files = sum(1 for r in results if r['status'] == 'success')
    warning_files = sum(1 for r in results if r['status'] == 'warning')
    error_files = sum(1 for r in results if r['status'] == 'error')
    would_process = sum(1 for r in results if r['status'] == 'would_process')
    total_chunks = sum(r.get('chunks', 0) for r in results)
    total_time = sum(r.get('time_seconds', 0) for r in results)
    
    logger.info("=" * 60)
    
    if args.dry_run:
        logger.info(f"Dry run completed: would process {would_process} files")
    else:
        logger.info(f"Processing completed: {successful_files}/{total_files} files successful")
        logger.info(f"- Warnings: {warning_files} files")
        logger.info(f"- Errors: {error_files} files")
        logger.info(f"Total chunks added: {total_chunks}")
        logger.info(f"Total processing time: {total_time:.2f} seconds")
    
    # Save report if requested
    if args.output:
        report = {
            "timestamp": datetime.now().isoformat(),
            "source": str(source_path),
            "recursive": args.recursive,
            "collection_name": args.collection_name,
            "dry_run": args.dry_run,
            "summary": {
                "total_files": total_files,
                "successful_files": successful_files,
                "warning_files": warning_files,
                "error_files": error_files,
                "would_process": would_process,
                "total_chunks": total_chunks,
                "total_time_seconds": total_time
            },
            "results": results
        }
        
        output_path = Path(args.output)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str)
        logger.info(f"Report saved to {output_path}")

if __name__ == "__main__":
    asyncio.run(main())

