"""
Storage interface and implementations for the QC bot application.

This module provides a unified storage interface with multiple backend implementations:
- MemoryStorage: In-memory storage for testing and caching
- FileStorage: File-based storage with serialization
- PostgresStorage: PostgreSQL-based storage for production use

All storage implementations follow the same interface, making it easy to switch
between different storage backends.
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

import aiofiles  # Add async file support
import psycopg2

from qcbot.utils.error import StorageError, ErrorCode

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
    """High-performance file-based storage with async I/O."""
    
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
        logger.info(f"Initialized high-performance file storage in {self.base_dir}")
    
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
        """Get an item from file storage using async I/O."""
        path = self._get_path(key)
        
        try:
            if not path.exists():
                return None
                
            if self.serializer == "json":
                async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content)
            else:
                async with aiofiles.open(path, 'rb') as f:
                    content = await f.read()
                    return pickle.loads(content)
                    
        except Exception as e:
            logger.error(f"Error reading from file storage: {e}")
            raise StorageError(
                code=ErrorCode.FILE_CORRUPTED,
                message=f"Failed to read from file storage: {str(e)}",
                details={"key": key, "path": str(path)}
            )
    
    async def put(self, key: str, value: T) -> bool:
        """Put an item into file storage using async I/O."""
        path = self._get_path(key)
        
        try:
            # Create parent directories if they don't exist
            path.parent.mkdir(parents=True, exist_ok=True)
            
            if self.serializer == "json":
                content = json.dumps(value, indent=2, default=str)
                async with aiofiles.open(path, 'w', encoding='utf-8') as f:
                    await f.write(content)
            else:
                content = pickle.dumps(value)
                async with aiofiles.open(path, 'wb') as f:
                    await f.write(content)
                    
            return True
            
        except Exception as e:
            logger.error(f"Error writing to file storage: {e}")
            raise StorageError(
                code=ErrorCode.STORAGE_UNAVAILABLE,
                message=f"Failed to write to file storage: {str(e)}",
                details={"key": key, "path": str(path)}
            )
    
    async def delete(self, key: str) -> bool:
        """Delete an item from file storage using async operations."""
        path = self._get_path(key)
        
        try:
            if path.exists():
                # Use thread executor for file deletion to avoid blocking
                import asyncio
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, os.remove, path)
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
        """List all keys in file storage with async directory operations."""
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            
            # Use thread executor for directory operations
            def _list_files():
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
            
            return await loop.run_in_executor(None, _list_files)
            
        except Exception as e:
            logger.error(f"Error listing keys in file storage: {e}")
            raise StorageError(
                code=ErrorCode.STORAGE_UNAVAILABLE,
                message=f"Failed to list keys in file storage: {str(e)}",
                details={"prefix": prefix}
            )
    
    async def clear(self) -> bool:
        """Clear all items from file storage using async operations."""
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            
            # Use thread executor for directory operations
            def _clear_directory():
                shutil.rmtree(self.base_dir)
                os.makedirs(self.base_dir, exist_ok=True)
            
            await loop.run_in_executor(None, _clear_directory)
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
"""Optional PostgreSQL implementation if asyncpg is available."""
try:
    import asyncpg

    class PostgresStorage(Storage[T]):
        """PostgreSQL-based async storage implementation."""

        def __init__(
            self,
            url: str = "postgresql://localhost:5432/qcbot",
            table_name: str = "qcbot_storage",
            serializer: str = "pickle",
            **kwargs
        ):
            """
            Initialize PostgreSQL storage.

            Args:
                url: PostgreSQL connection URL
                table_name: Name of the table to store key-value pairs
                serializer: Serialization format ('json' or 'pickle')
                **kwargs: Additional asyncpg connection arguments
            """
            self.url = url
            self.table_name = table_name
            self.serializer = serializer
            self.pool: Optional[asyncpg.pool.Pool] = None
            logger.info(f"Initialized PostgreSQL storage at {url}")

        async def _ensure_connection(self) -> None:
            """Ensure database connection pool is established."""
            if self.pool is None:
                self.pool = await asyncpg.create_pool(self.url)
                await self._create_table()

        async def _create_table(self) -> None:
            """Create the storage table if it doesn't exist."""
            assert self.pool is not None
            async with self.pool.acquire() as conn:
                await conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        key TEXT PRIMARY KEY,
                        value BYTEA NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                    """
                )
                await conn.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.table_name}_key_prefix
                    ON {self.table_name} USING btree (key text_pattern_ops)
                    """
                )

        def _serialize(self, value: T) -> bytes:
            """Serialize value to bytes."""
            if self.serializer == "json":
                return json.dumps(value, default=str).encode("utf-8")
            return pickle.dumps(value)

        def _deserialize(self, value: bytes) -> T:
            """Deserialize bytes to value."""
            if self.serializer == "json":
                return json.loads(value.decode("utf-8"))
            return pickle.loads(value)

        async def get(self, key: str) -> Optional[T]:
            """Get an item from PostgreSQL storage."""
            try:
                await self._ensure_connection()
                assert self.pool is not None
                async with self.pool.acquire() as conn:
                    row = await conn.fetchrow(
                        f"SELECT value FROM {self.table_name} WHERE key = $1",
                        key,
                    )
                    if row:
                        return self._deserialize(row["value"])  # type: ignore[arg-type]
                    return None
            except Exception as e:
                logger.error(f"Error reading from PostgreSQL: {e}")
                raise StorageError(
                    code=ErrorCode.STORAGE_UNAVAILABLE,
                    message=f"Failed to read from PostgreSQL: {str(e)}",
                    details={"key": key},
                )

        async def put(self, key: str, value: T) -> bool:
            """Put an item into PostgreSQL storage."""
            try:
                await self._ensure_connection()
                assert self.pool is not None
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        f"""
                        INSERT INTO {self.table_name} (key, value, updated_at)
                        VALUES ($1, $2, NOW())
                        ON CONFLICT (key) DO UPDATE SET
                            value = EXCLUDED.value,
                            updated_at = NOW()
                        """,
                        key,
                        self._serialize(value),
                    )
                return True
            except Exception as e:
                logger.error(f"Error writing to PostgreSQL: {e}")
                raise StorageError(
                    code=ErrorCode.STORAGE_UNAVAILABLE,
                    message=f"Failed to write to PostgreSQL: {str(e)}",
                    details={"key": key},
                )

        async def delete(self, key: str) -> bool:
            """Delete an item from PostgreSQL storage."""
            try:
                await self._ensure_connection()
                assert self.pool is not None
                async with self.pool.acquire() as conn:
                    result = await conn.execute(
                        f"DELETE FROM {self.table_name} WHERE key = $1",
                        key,
                    )
                    # result format is e.g., "DELETE 1"
                    return result.split()[1] != "0"
            except Exception as e:
                logger.error(f"Error deleting from PostgreSQL: {e}")
                raise StorageError(
                    code=ErrorCode.STORAGE_UNAVAILABLE,
                    message=f"Failed to delete from PostgreSQL: {str(e)}",
                    details={"key": key},
                )

        async def exists(self, key: str) -> bool:
            """Check if an item exists in PostgreSQL storage."""
            try:
                await self._ensure_connection()
                assert self.pool is not None
                async with self.pool.acquire() as conn:
                    return await conn.fetchval(
                        f"SELECT EXISTS(SELECT 1 FROM {self.table_name} WHERE key = $1)",
                        key,
                    )
            except Exception as e:
                logger.error(f"Error checking existence in PostgreSQL: {e}")
                raise StorageError(
                    code=ErrorCode.STORAGE_UNAVAILABLE,
                    message=f"Failed to check existence in PostgreSQL: {str(e)}",
                    details={"key": key},
                )

        async def list_keys(self, prefix: Optional[str] = None) -> List[str]:
            """List all keys in PostgreSQL storage."""
            try:
                await self._ensure_connection()
                assert self.pool is not None
                async with self.pool.acquire() as conn:
                    if prefix:
                        # Escape LIKE wildcards
                        escaped = prefix.replace("%", "\\%").replace("_", "\\_")
                        rows = await conn.fetch(
                            f"SELECT key FROM {self.table_name} WHERE key LIKE $1 ESCAPE '\\'",
                            f"{escaped}%",
                        )
                    else:
                        rows = await conn.fetch(
                            f"SELECT key FROM {self.table_name}"
                        )
                    return [r["key"] for r in rows]
            except Exception as e:
                logger.error(f"Error listing keys in PostgreSQL: {e}")
                raise StorageError(
                    code=ErrorCode.STORAGE_UNAVAILABLE,
                    message=f"Failed to list keys in PostgreSQL: {str(e)}",
                    details={"prefix": prefix},
                )

        async def clear(self) -> bool:
            """Clear all items from PostgreSQL storage."""
            try:
                await self._ensure_connection()
                assert self.pool is not None
                async with self.pool.acquire() as conn:
                    await conn.execute(f"DELETE FROM {self.table_name}")
                return True
            except Exception as e:
                logger.error(f"Error clearing PostgreSQL storage: {e}")
                raise StorageError(
                    code=ErrorCode.STORAGE_UNAVAILABLE,
                    message=f"Failed to clear PostgreSQL storage: {str(e)}",
                )

        async def close(self) -> None:
            """Close the database connection pool."""
            if self.pool:
                await self.pool.close()
                self.pool = None
                logger.info("PostgreSQL connection pool closed")

    # Add PostgreSQL to factory
    def get_postgres_storage(**kwargs) -> PostgresStorage:
        return PostgresStorage(**kwargs)
    logger.info("asyncpg available. PostgreSQL storage will be available.")
    StorageFactory.get_postgres_storage = staticmethod(get_postgres_storage)

except ImportError:
    logger.info("asyncpg not available. PostgreSQL storage will not be available.")