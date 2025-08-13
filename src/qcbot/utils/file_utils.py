"""
File Management Utilities for QC Bot

This module contains utilities for file operations including upload handling,
async file operations, and file management functions.
"""

import asyncio
import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
import aiofiles
from qcbot.config.app_config import get_current_app_config

logger = logging.getLogger(__name__)


async def run_blocking(fn, *args):
    """Run blocking functions in a thread executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, fn, *args)


async def save_uploaded_file(file) -> str:
    """
    Save uploaded file to app instance-specific knowledge base directory using async I/O.
    
    Args:
        file: The uploaded file
        
    Returns:
        Path to the saved file
    """
    # Get QC app config (standalone)
    app_config = get_current_app_config()
    
    knowledge_dir = app_config.knowledge_base_dir
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    
    dst = knowledge_dir / file.filename
    
    # Use async file writing for better concurrency
    file_content = await file.read()
    async with aiofiles.open(dst, mode='wb') as f:
        await f.write(file_content)
        
    logger.info("Saved file → %s", dst)
    return str(dst)


async def read_file_async(file_path: str, encoding: str = "utf-8") -> str:
    """Read a file asynchronously."""
    try:
        async with aiofiles.open(file_path, mode='r', encoding=encoding) as f:
            return await f.read()
    except UnicodeDecodeError:
        # Fallback to latin-1 encoding
        async with aiofiles.open(file_path, mode='r', encoding='latin-1') as f:
            return await f.read()


def read_file_sync(file_path: str, encoding: str = "utf-8") -> str:
    """Read a file synchronously."""
    try:
        with open(file_path, encoding=encoding) as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file_path, encoding='latin-1') as f:
            return f.read()


async def write_file_async(file_path: str, content: str, encoding: str = "utf-8") -> bool:
    """Write content to a file asynchronously."""
    try:
        async with aiofiles.open(file_path, mode='w', encoding=encoding) as f:
            await f.write(content)
        return True
    except Exception as e:
        logger.error(f"Error writing file {file_path}: {e}")
        return False


def write_file_sync(file_path: str, content: str, encoding: str = "utf-8") -> bool:
    """Write content to a file synchronously."""
    try:
        with open(file_path, mode='w', encoding=encoding) as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"Error writing file {file_path}: {e}")
        return False


def get_file_hash(file_path: str) -> str:
    """Calculate MD5 hash of a file."""
    try:
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        logger.error(f"Error calculating hash for {file_path}: {e}")
        return ""


def get_file_info(file_path: str) -> dict:
    """Get comprehensive file information."""
    try:
        path = Path(file_path)
        if not path.exists():
            return {}
        
        stat = path.stat()
        return {
            "name": path.name,
            "path": str(path),
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "extension": path.suffix.lower(),
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "hash": get_file_hash(file_path)
        }
    except Exception as e:
        logger.error(f"Error getting file info for {file_path}: {e}")
        return {}


def ensure_directory_exists(directory_path: str) -> bool:
    """Ensure a directory exists, creating it if necessary."""
    try:
        Path(directory_path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Error creating directory {directory_path}: {e}")
        return False


def get_supported_extensions() -> set:
    """Get the set of supported file extensions."""
    return {'.pdf', '.docx', '.txt', '.md', '.csv'}


def is_supported_file(file_path: str) -> bool:
    """Check if a file is supported based on its extension."""
    return Path(file_path).suffix.lower() in get_supported_extensions()


def get_knowledge_base_files() -> list:
    """Get all supported files in the knowledge base directory."""
    try:
        app_config = get_current_app_config()
        knowledge_dir = app_config.knowledge_base_dir
        
        if not knowledge_dir.exists():
            return []
        
        supported_extensions = get_supported_extensions()
        system_files = {'.DS_Store', '.Thumbs.db', 'Thumbs.db', '.desktop', '.directory'}
        files = []
        
        for file_path in knowledge_dir.iterdir():
            if (file_path.is_file() 
                and file_path.suffix.lower() in supported_extensions
                and file_path.name not in system_files
                and not file_path.name.startswith('.')):
                files.append(get_file_info(str(file_path)))
        
        # Sort by modification time (newest first)
        files.sort(key=lambda x: x.get('modified', ''), reverse=True)
        
        return files
    except Exception as e:
        logger.error(f"Error getting knowledge base files: {e}")
        return []


def delete_file(file_path: str) -> bool:
    """Delete a file safely."""
    try:
        path = Path(file_path)
        if path.exists():
            path.unlink()
            logger.info(f"Deleted file: {file_path}")
            return True
        else:
            logger.warning(f"File not found: {file_path}")
            return False
    except Exception as e:
        logger.error(f"Error deleting file {file_path}: {e}")
        return False


def copy_file_async(src_path: str, dst_path: str) -> bool:
    """Copy a file asynchronously."""
    try:
        # Ensure destination directory exists
        dst_dir = Path(dst_path).parent
        dst_dir.mkdir(parents=True, exist_ok=True)
        
        # Use async file operations
        async def _copy():
            async with aiofiles.open(src_path, 'rb') as src:
                content = await src.read()
                async with aiofiles.open(dst_path, 'wb') as dst:
                    await dst.write(content)
        
        asyncio.create_task(_copy())
        return True
    except Exception as e:
        logger.error(f"Error copying file from {src_path} to {dst_path}: {e}")
        return False


def get_file_size_mb(file_path: str) -> float:
    """Get file size in megabytes."""
    try:
        size_bytes = Path(file_path).stat().st_size
        return round(size_bytes / (1024 * 1024), 2)
    except Exception:
        return 0.0


def validate_file_size(file_path: str, max_size_mb: float = 50.0) -> bool:
    """Validate that a file is within size limits."""
    file_size_mb = get_file_size_mb(file_path)
    return file_size_mb <= max_size_mb
