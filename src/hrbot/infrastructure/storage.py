"""
Storage interface and implementations for the HR bot application.

This module provides:
1. Abstract storage interface for data persistence
2. Multiple storage backends (local file, memory, cloud)
3. Serialization/deserialization helpers
4. Common storage patterns and utilities
"""

import os
import json
import pickle
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, TypeVar, Generic, Type
from pathlib import Path
from datetime import datetime
import shutil

import psycopg2

from hrbot.utils.error import StorageError, ErrorCode

logger = logging.getLogger(__name__)

# Generic type for storage items
T = TypeVar('T')


class Storage(Generic[T], ABC):
    """Abstract base storage interface with typed operations."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[T]:
        """
        Get an item from storage by key.
        
        Args:
            key: The item key
            
        Returns:
            The item if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def put(self, key: str, value: T) -> bool:
        """
        Put an item into storage.
        
        Args:
            key: The item key
            value: The item value
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete an item from storage.
        
        Args:
            key: The item key
            
        Returns:
            True if deleted, False otherwise
        """
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """
        Check if an item exists in storage.
        
        Args:
            key: The item key
            
        Returns:
            True if exists, False otherwise
        """
        pass
    
    @abstractmethod
    async def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """
        List all keys in storage.
        
        Args:
            prefix: Optional prefix filter
            
        Returns:
            List of keys
        """
        pass
    
    @abstractmethod
    async def clear(self) -> bool:
        """
        Clear all items from storage.
        
        Returns:
            True if successful, False otherwise
        """
        pass


class MemoryStorage(Storage[T]):
    """In-memory storage implementation."""
    
    def __init__(self):
        """Initialize empty in-memory storage."""
        self._storage: Dict[str, T] = {}
        logger.info("Initialized in-memory storage")
    
    async def get(self, key: str) -> Optional[T]:
        """Get an item from memory storage."""
        return self._storage.get(key)
    
    async def put(self, key: str, value: T) -> bool:
        """Put an item into memory storage."""
        self._storage[key] = value
        return True
    
    async def delete(self, key: str) -> bool:
        """Delete an item from memory storage."""
        if key in self._storage:
            del self._storage[key]
            return True
        return False
    
    async def exists(self, key: str) -> bool:
        """Check if an item exists in memory storage."""
        return key in self._storage
    
    async def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """List all keys in memory storage."""
        if prefix:
            return [k for k in self._storage.keys() if k.startswith(prefix)]
        return list(self._storage.keys())
    
    async def clear(self) -> bool:
        """Clear all items from memory storage."""
        self._storage.clear()
        return True


class FileStorage(Storage[T]):
    """File-based storage implementation."""
    
    def __init__(self, base_dir: str, serializer: Optional[str] = "pickle"):
        """
        Initialize file storage.
        
        Args:
            base_dir: Base directory for file storage
            serializer: Serialization format ('json' or 'pickle')
        """
        self.base_dir = Path(base_dir)
        self.serializer = serializer
        
        # Create base directory if it doesn't exist
        os.makedirs(self.base_dir, exist_ok=True)
        logger.info(f"Initialized file storage in {self.base_dir}")
    
    def _get_path(self, key: str) -> Path:
        """Convert key to file path."""
        # Sanitize key for file path
        safe_key = key.replace('/', '_').replace('\\', '_')
        
        # Add file extension based on serializer
        if self.serializer == "json":
            extension = ".json"
        else:
            extension = ".pkl"
            
        return self.base_dir / f"{safe_key}{extension}"
    
    async def get(self, key: str) -> Optional[T]:
        """Get an item from file storage."""
        path = self._get_path(key)
        
        try:
            if not path.exists():
                return None
                
            if self.serializer == "json":
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                with open(path, 'rb') as f:
                    return pickle.load(f)
                    
        except Exception as e:
            logger.error(f"Error reading from file storage: {e}")
            raise StorageError(
                code=ErrorCode.FILE_CORRUPTED,
                message=f"Failed to read from file storage: {str(e)}",
                details={"key": key, "path": str(path)}
            )
    
    async def put(self, key: str, value: T) -> bool:
        """Put an item into file storage."""
        path = self._get_path(key)
        
        try:
            # Create parent directories if they don't exist
            path.parent.mkdir(parents=True, exist_ok=True)
            
            if self.serializer == "json":
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(value, f, indent=2, default=str)
            else:
                with open(path, 'wb') as f:
                    pickle.dump(value, f)
                    
            return True
            
        except Exception as e:
            logger.error(f"Error writing to file storage: {e}")
            raise StorageError(
                code=ErrorCode.STORAGE_UNAVAILABLE,
                message=f"Failed to write to file storage: {str(e)}",
                details={"key": key, "path": str(path)}
            )
    
    async def delete(self, key: str) -> bool:
        """Delete an item from file storage."""
        path = self._get_path(key)
        
        try:
            if path.exists():
                os.remove(path)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error deleting from file storage: {e}")
            raise StorageError(
                code=ErrorCode.PERMISSION_DENIED,
                message=f"Failed to delete from file storage: {str(e)}",
                details={"key": key, "path": str(path)}
            )
    
    async def exists(self, key: str) -> bool:
        """Check if an item exists in file storage."""
        path = self._get_path(key)
        return path.exists()
    
    async def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """List all keys in file storage."""
        try:
            extensions = [".json"] if self.serializer == "json" else [".pkl"]
            
            # Get all files with the correct extension
            files = []
            for ext in extensions:
                files.extend(self.base_dir.glob(f"*{ext}"))
                
            # Extract keys from filenames
            keys = []
            for file in files:
                key = file.stem  # Remove extension
                
                # Filter by prefix if provided
                if prefix is None or key.startswith(prefix):
                    keys.append(key)
                    
            return keys
            
        except Exception as e:
            logger.error(f"Error listing keys in file storage: {e}")
            raise StorageError(
                code=ErrorCode.STORAGE_UNAVAILABLE,
                message=f"Failed to list keys in file storage: {str(e)}",
                details={"prefix": prefix}
            )
    
    async def clear(self) -> bool:
        """Clear all items from file storage."""
        try:
            # Remove and recreate the directory
            shutil.rmtree(self.base_dir)
            os.makedirs(self.base_dir, exist_ok=True)
            return True
            
        except Exception as e:
            logger.error(f"Error clearing file storage: {e}")
            raise StorageError(
                code=ErrorCode.PERMISSION_DENIED,
                message=f"Failed to clear file storage: {str(e)}",
                details={"base_dir": str(self.base_dir)}
            )


class StorageFactory:
    """Factory for creating storage instances."""
    
    @staticmethod
    def get_storage(storage_type: str, **kwargs) -> Storage:
        """
        Get a storage instance by type.
        
        Args:
            storage_type: The type of storage ('memory' or 'file')
            **kwargs: Additional arguments for the storage
            
        Returns:
            Storage instance
        """
        if storage_type == "memory":
            return MemoryStorage()
        
        elif storage_type == "file":
            base_dir = kwargs.get("base_dir", "data/storage")
            serializer = kwargs.get("serializer", "pickle")
            return FileStorage(base_dir, serializer)
        
        else:
            raise ValueError(f"Unknown storage type: {storage_type}")


# Optional Redis implementation if redis is available
try:
    import redis.asyncio as redis
    
    class PostgresStorage(Storage[T]):
        """Redis-based storage implementation."""
        
        def __init__(
            self,
            url: str = "postgresql://localhost:5432/hrbot",
            serializer: str = "pickle",
            **kwargs
        ):
            """
            Initialize Redis storage.
            
            Args:
                host: Redis host
                port: Redis port
                db: Redis database
                prefix: Key prefix
                serializer: Serialization format ('json' or 'pickle')
                **kwargs: Additional Redis client arguments
            """
            self.prefix = "2/hrbot"
            self.serializer = serializer
            self.client = psycopg2.connect(url)
            logger.info(f"Initialized Postgres storage at {url}")
        
        def _get_key(self, key: str) -> str:
            """Add prefix to key."""
            return f"{self.prefix}{key}"
        
        def _serialize(self, value: T) -> bytes:
            """Serialize value to bytes."""
            if self.serializer == "json":
                return json.dumps(value, default=str).encode('utf-8')
            else:
                return pickle.dumps(value)
        
        def _deserialize(self, value: bytes) -> T:
            """Deserialize bytes to value."""
            if self.serializer == "json":
                return json.loads(value.decode('utf-8'))
            else:
                return pickle.loads(value)
        
        async def get(self, key: str) -> Optional[T]:
            """Get an item from Redis storage."""
            try:
                data = await self.client.get(self._get_key(key))
                if data:
                    return self._deserialize(data)
                return None
            except Exception as e:
                logger.error(f"Error reading from Redis: {e}")
                raise StorageError(
                    code=ErrorCode.STORAGE_UNAVAILABLE,
                    message=f"Failed to read from Redis: {str(e)}",
                    details={"key": key}
                )
        
        async def put(self, key: str, value: T) -> bool:
            """Put an item into Redis storage."""
            try:
                await self.client.set(
                    self._get_key(key),
                    self._serialize(value)
                )
                return True
            except Exception as e:
                logger.error(f"Error writing to Redis: {e}")
                raise StorageError(
                    code=ErrorCode.STORAGE_UNAVAILABLE,
                    message=f"Failed to write to Redis: {str(e)}",
                    details={"key": key}
                )
        
        async def delete(self, key: str) -> bool:
            """Delete an item from Redis storage."""
            try:
                count = await self.client.delete(self._get_key(key))
                return count > 0
            except Exception as e:
                logger.error(f"Error deleting from Redis: {e}")
                raise StorageError(
                    code=ErrorCode.STORAGE_UNAVAILABLE,
                    message=f"Failed to delete from Redis: {str(e)}",
                    details={"key": key}
                )
        
        async def exists(self, key: str) -> bool:
            """Check if an item exists in Redis storage."""
            try:
                exists = await self.client.exists(self._get_key(key))
                return exists > 0
            except Exception as e:
                logger.error(f"Error checking existence in Redis: {e}")
                raise StorageError(
                    code=ErrorCode.STORAGE_UNAVAILABLE,
                    message=f"Failed to check existence in Redis: {str(e)}",
                    details={"key": key}
                )
        
        async def list_keys(self, prefix: Optional[str] = None) -> List[str]:
            """List all keys in Redis storage."""
            try:
                # Create pattern with both the storage prefix and the optional prefix
                pattern = f"{self.prefix}{prefix or ''}*"
                
                # Use scan_iter for efficiency
                keys = []
                async for key in self.client.scan_iter(pattern):
                    # Remove the storage prefix to get the original key
                    original_key = key.decode('utf-8')[len(self.prefix):]
                    keys.append(original_key)
                
                return keys
            except Exception as e:
                logger.error(f"Error listing keys in Redis: {e}")
                raise StorageError(
                    code=ErrorCode.STORAGE_UNAVAILABLE,
                    message=f"Failed to list keys in Redis: {str(e)}",
                    details={"prefix": prefix}
                )
        
        async def clear(self) -> bool:
            """Clear all items from Redis storage with the storage prefix."""
            try:
                # Find all keys with the prefix
                pattern = f"{self.prefix}*"
                
                # Delete keys in batches to avoid blocking Redis
                keys_to_delete = []
                async for key in self.client.scan_iter(pattern):
                    keys_to_delete.append(key)
                    if len(keys_to_delete) >= 1000:
                        await self.client.delete(*keys_to_delete)
                        keys_to_delete = []
                
                # Delete any remaining keys
                if keys_to_delete:
                    await self.client.delete(*keys_to_delete)
                
                return True
            except Exception as e:
                logger.error(f"Error clearing Redis storage: {e}")
                raise StorageError(
                    code=ErrorCode.STORAGE_UNAVAILABLE,
                    message=f"Failed to clear Redis storage: {str(e)}"
                )
        
    # Add Redis to factory
    def get_postgres_storage(**kwargs) -> PostgresStorage:
        return PostgresStorage(**kwargs)
    logger.info("Postgres available. Postgres storage will be available.")  
    StorageFactory.get_postgres_storage = staticmethod(get_postgres_storage)
    
except ImportError:
    logger.info("Postgres not available. Postgres storage will not be available.")