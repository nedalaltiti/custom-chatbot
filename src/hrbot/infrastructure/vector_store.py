"""
In-house NumPy/ndarray vector store (disk-backed, no FAISS) with multi-tenant support.
"""

from __future__ import annotations

import asyncio
import logging
import pickle
import time
from pathlib import Path
from typing import List, Sequence, Dict, Tuple

import numpy as np

from hrbot.core.document import Document
from hrbot.infrastructure.embeddings import VertexDirectEmbeddings
from hrbot.utils.error import StorageError, ErrorCode
from hrbot.config.settings import settings
from hrbot.config.tenant import get_current_tenant

logger = logging.getLogger(__name__)


class VectorStore:
    """Minimal but solid disk-backed cosine-similarity store with caching and multi-tenant support."""

    FILE_EXT = ".npz"          # single compressed archive <collection>.npz

    def __init__(
        self,
        *,
        collection_name: str = "hr_documents",
        data_dir: str | Path = None,  # Will be auto-detected from tenant if not provided
        embeddings: VertexDirectEmbeddings | None = None,
    ) -> None:
        self.collection_name = collection_name
        
        # Use tenant-specific data directory if not provided
        if data_dir is None:
            tenant = get_current_tenant()
            self.data_dir = tenant.embeddings_dir
            logger.info(f"Using tenant-specific embeddings directory: {self.data_dir}")
        else:
            self.data_dir = Path(data_dir)
            
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._archive_path = self.data_dir / f"{collection_name}{self.FILE_EXT}"
        self._doclist_path = self.data_dir / f"{collection_name}_docs.pkl"

        self._embeddings = embeddings or VertexDirectEmbeddings()
        # engine.py expects this name
        self.embeddings_model = self._embeddings
        self._matrix: np.ndarray | None = None       # shape (N, dim)
        self._docs: list[Document] = []
        
        # Simple cache for similarity searches
        self._cache: Dict[Tuple[str, int], Tuple[List[Document], float]] = {}
        self._cache_enabled = settings.performance.cache_embeddings
        self._cache_ttl = settings.performance.cache_ttl_seconds

        self._load_or_init()

    @property
    def documents(self) -> list[Document]:
        """Public accessor used by the ingest layer."""
        return self._docs

    def _load_or_init(self) -> None:
        if self._archive_path.exists() and self._doclist_path.exists():
            try:
                self._matrix = np.load(self._archive_path)["arr_0"]
                with open(self._doclist_path, "rb") as f:
                    self._docs = pickle.load(f)
                logger.info(
                    "VectorStore loaded (%d docs, dim=%d) from %s",
                    len(self._docs),
                    self._matrix.shape[1],
                    self.data_dir
                )
                return
            except Exception as exc:                                 # noqa: BLE001
                logger.warning("Corrupted vector store – rebuilding (%s)", exc)

        # fresh empty store
        dim = self._embeddings.dimension
        self._matrix = np.empty((0, dim), dtype=np.float32)
        self._docs = []
        logger.info("VectorStore initialised empty (dim=%d) in %s", dim, self.data_dir)

    def sync_disk(self) -> None:
        """Flush current state to disk (atomic)."""
        if self._matrix is None:      # pragma: no cover
            return

        tmp = self._archive_path.with_suffix(".tmp.npz")   # ends with .npz
        np.savez_compressed(tmp, self._matrix)             # atomic
        tmp.replace(self._archive_path)

        with open(self._doclist_path, "wb") as f:
            pickle.dump(self._docs, f)
            
        # Clear cache when store is updated
        self._cache.clear()


    async def add_documents(self, docs: Sequence[Document]) -> int:
        """Embed & add *only* the docs that are not present yet.

        Returns the **number of NEW documents embedded**.
        """
        if not docs:
            return 0
        if self._matrix is None:
            raise RuntimeError("VectorStore not initialised")

        existing_hashes = {d.metadata.get("sha256") or d.sha256() for d in self._docs}
        fresh: list[Document] = []
        for d in docs:
            h = d.sha256()
            if h not in existing_hashes:
                d.metadata["sha256"] = h
                fresh.append(d)

        if not fresh:
            return 0

        texts = [d.page_content for d in fresh]
        embeds = await asyncio.to_thread(self._embeddings.embed_documents, texts)
        embeds = np.asarray(embeds, dtype=np.float32)

        # L2-normalise ⇒ cosine == dot
        embeds /= np.linalg.norm(embeds, axis=1, keepdims=True) + 1e-9

        self._matrix = (
            np.vstack([self._matrix, embeds]) if self._matrix.size else embeds
        )
        self._docs.extend(fresh)
        self.sync_disk()
        logger.info("Added %d new docs (total =%d)", len(fresh), len(self._docs))
        return len(fresh)

    async def similarity_search(
         self,
         query: str,
         k: int = 5,
         *,
         top_k: int | None = None,      

     ) -> list[Document]:
        logger.debug(f"Similarity search called with query: '{query[:50]}...', k={k}, docs available: {len(self._docs)}")
        
        if self._matrix is None or not len(self._docs):
            logger.warning(f"No documents available for search! Matrix: {self._matrix is not None}, Docs: {len(self._docs)}")
            return []

        if top_k is not None:
            k = top_k
            
        # Check cache first
        cache_key = (query, k)
        if self._cache_enabled and cache_key in self._cache:
            cached_result, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug(f"Cache hit for query: {query[:50]}...")
                return cached_result
            else:
                # Remove expired entry
                del self._cache[cache_key]

        # Use async embedding generation for better concurrency
        q = await asyncio.to_thread(self._embeddings.embed_query, query)
        q = np.asarray(q, dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-9

        # Optimized similarity computation using vectorized operations
        sims = np.dot(self._matrix, q)  # More efficient than matrix multiplication
        
        # Use argpartition for better performance when k << n
        if k < len(sims) // 10:  # Only use argpartition for small k
            top_idx = np.argpartition(sims, -k)[-k:]
            top_idx = top_idx[np.argsort(sims[top_idx])[::-1]]
        else:
            top_idx = np.argsort(sims)[-k:][::-1]
            
        results = [self._docs[i] for i in top_idx]
        
        # Debug logging
        logger.debug(f"Similarity scores: {[sims[i] for i in top_idx[:5]]}")  # Top 5 scores
        logger.debug(f"Retrieved {len(results)} documents for query: '{query[:30]}...'")
        if results:
            logger.debug(f"Top result: {results[0].page_content[:100]}...")
        
        # Cache the results
        if self._cache_enabled:
            self._cache[cache_key] = (results, time.time())
            # Clean up old cache entries if cache is getting large
            if len(self._cache) > 100:
                current_time = time.time()
                expired_keys = [
                    key for key, (_, timestamp) in self._cache.items()
                    if current_time - timestamp >= self._cache_ttl
                ]
                for key in expired_keys:
                    del self._cache[key]
        
        return results

    async def warmup(self) -> None:
        """Load data into RAM (called from FastAPI lifespan)."""
        if self._matrix is not None and self._matrix.size:
            _ = float(self._matrix[0] @ self._matrix[0])  # touch memory

    async def clear(self) -> None:
        """Danger: wipe cache from disk & memory."""
        for p in (self._archive_path, self._doclist_path):
            p.unlink(missing_ok=True)
        self._cache.clear()
        self._load_or_init()
        
    async def delete_collection(self) -> None:
        """Delete the entire collection."""
        await self.clear()


# Optional ChromaDB implementation for enhanced vector database capabilities
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    
    class ChromaVectorStore:
        """
        Enhanced vector store using ChromaDB for better performance and features.
        
        Advantages over basic VectorStore:
        - Better scalability and performance
        - Advanced filtering and metadata queries
        - Built-in persistence and reliability
        - Support for multiple collections
        - Advanced similarity algorithms
        """
        
        def __init__(
            self,
            *,
            collection_name: str = "hr_documents",
            data_dir: str | Path = "data/chroma",
            embeddings: VertexDirectEmbeddings | None = None,
        ) -> None:
            self.collection_name = collection_name
            self.data_dir = Path(data_dir)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            
            self._embeddings = embeddings or VertexDirectEmbeddings()
            self.embeddings_model = self._embeddings
            
            # Initialize ChromaDB client
            chroma_settings = ChromaSettings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=str(self.data_dir),
                anonymized_telemetry=False
            )
            
            self._client = chromadb.Client(chroma_settings)
            
            # Get or create collection
            try:
                self._collection = self._client.get_collection(
                    name=collection_name,
                    embedding_function=None  # We'll handle embeddings ourselves
                )
                logger.info(f"Loaded existing ChromaDB collection: {collection_name}")
            except ValueError:
                self._collection = self._client.create_collection(
                    name=collection_name,
                    embedding_function=None
                )
                logger.info(f"Created new ChromaDB collection: {collection_name}")
        
        @property 
        def documents(self) -> list[Document]:
            """Get all documents from the collection."""
            try:
                result = self._collection.get()
                docs = []
                
                if result['documents']:
                    for i, doc_text in enumerate(result['documents']):
                        metadata = result['metadatas'][i] if result['metadatas'] else {}
                        docs.append(Document(page_content=doc_text, metadata=metadata))
                
                return docs
            except Exception as e:
                logger.warning(f"Error retrieving documents from ChromaDB: {e}")
                return []
        
        async def add_documents(self, docs: Sequence[Document]) -> int:
            """Add documents to ChromaDB with deduplication."""
            if not docs:
                return 0
            
            # Check for existing documents to avoid duplicates
            existing_hashes = set()
            try:
                result = self._collection.get()
                if result['metadatas']:
                    existing_hashes = {
                        meta.get('sha256') for meta in result['metadatas'] 
                        if meta.get('sha256')
                    }
            except Exception as e:
                logger.warning(f"Error checking existing documents: {e}")
            
            # Filter new documents
            fresh_docs = []
            for doc in docs:
                doc_hash = doc.sha256()
                if doc_hash not in existing_hashes:
                    doc.metadata['sha256'] = doc_hash
                    fresh_docs.append(doc)
            
            if not fresh_docs:
                return 0
            
            # Generate embeddings
            texts = [doc.page_content for doc in fresh_docs]
            embeddings = await asyncio.to_thread(
                self._embeddings.embed_documents, 
                texts
            )
            
            # Prepare data for ChromaDB
            ids = [f"doc_{hash(doc.page_content)}_{i}" for i, doc in enumerate(fresh_docs)]
            metadatas = [doc.metadata for doc in fresh_docs]
            
            # Add to collection
            try:
                self._collection.add(
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=metadatas,
                    ids=ids
                )
                
                # Persist changes
                self._client.persist()
                
                logger.info(f"Added {len(fresh_docs)} new documents to ChromaDB")
                return len(fresh_docs)
                
            except Exception as e:
                logger.error(f"Error adding documents to ChromaDB: {e}")
                return 0
        
        async def similarity_search(
            self,
            query: str,
            k: int = 5,
            *,
            top_k: int | None = None,
            where: Dict | None = None  # Additional filtering
        ) -> list[Document]:
            """Search for similar documents using ChromaDB."""
            if top_k is not None:
                k = top_k
            
            try:
                # Generate query embedding
                query_embedding = await asyncio.to_thread(
                    self._embeddings.embed_query, 
                    query
                )
                
                # Perform similarity search
                results = self._collection.query(
                    query_embeddings=[query_embedding],
                    n_results=k,
                    where=where,
                    include=['documents', 'metadatas', 'distances']
                )
                
                # Convert results to Document objects
                documents = []
                if results['documents'] and results['documents'][0]:
                    for i, doc_text in enumerate(results['documents'][0]):
                        metadata = results['metadatas'][0][i] if results['metadatas'][0] else {}
                        
                        # Add similarity score to metadata
                        if results['distances'] and results['distances'][0]:
                            # ChromaDB returns distances (lower is better), convert to similarity
                            distance = results['distances'][0][i]
                            similarity = 1 / (1 + distance)  # Convert distance to similarity
                            metadata['similarity_score'] = similarity
                        
                        documents.append(Document(
                            page_content=doc_text,
                            metadata=metadata
                        ))
                
                return documents
                
            except Exception as e:
                logger.error(f"Error in ChromaDB similarity search: {e}")
                return []
        
        async def warmup(self) -> None:
            """Warmup ChromaDB collection."""
            try:
                # Test query to warm up the collection
                await self.similarity_search("test", k=1)
                logger.debug("ChromaDB warmed up successfully")
            except Exception as e:
                logger.warning(f"ChromaDB warmup failed: {e}")
        
        async def clear(self) -> None:
            """Clear all documents from the collection."""
            try:
                self._client.delete_collection(self.collection_name)
                self._collection = self._client.create_collection(
                    name=self.collection_name,
                    embedding_function=None
                )
                logger.info(f"Cleared ChromaDB collection: {self.collection_name}")
            except Exception as e:
                logger.error(f"Error clearing ChromaDB collection: {e}")
        
        async def delete_collection(self) -> None:
            """Delete the entire collection."""
            await self.clear()
    
    logger.info("ChromaDB available - enhanced vector store enabled")
    
except ImportError:
    class ChromaVectorStore:
        """Placeholder class when ChromaDB is not available."""
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "ChromaDB not installed. Install with: pip install chromadb\n"
                "Or use the basic VectorStore implementation."
            )
    
    logger.info("ChromaDB not available - using basic VectorStore only")


def create_vector_store(
    store_type: str = "basic",
    **kwargs
) -> VectorStore | ChromaVectorStore:
    """
    Factory function to create the appropriate vector store.
    
    Args:
        store_type: "basic" for NumPy-based store, "chroma" for ChromaDB
        **kwargs: Additional arguments for the vector store
        
    Returns:
        Configured vector store instance
    """
    if store_type.lower() == "chroma":
        return ChromaVectorStore(**kwargs)
    else:
        return VectorStore(**kwargs)