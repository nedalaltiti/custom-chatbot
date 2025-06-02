#!/usr/bin/env python3
"""
Performance testing script for HR chatbot optimizations.

This script tests and compares the performance of optimized vs non-optimized operations.
"""

import asyncio
import time
import logging
import sys
import statistics
from pathlib import Path
from typing import List, Dict, Any

# Add the parent directory to the Python path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.hrbot.core.chunking import (
    process_document, 
    reload_knowledge_base_concurrent,
    _extract_text_txt_async,
    _extract_text_txt
)
from src.hrbot.infrastructure.vector_store import VectorStore
from src.hrbot.infrastructure.storage import FileStorage
from src.hrbot.services.gemini_service import GeminiService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PerformanceTester:
    """Performance testing utilities for the HR chatbot."""
    
    def __init__(self):
        self.results = {}
    
    async def time_async_operation(self, operation_name: str, operation, *args, runs: int = 5):
        """Time an async operation multiple times and return statistics."""
        times = []
        
        for i in range(runs):
            start = time.perf_counter()
            try:
                result = await operation(*args)
                end = time.perf_counter()
                times.append(end - start)
                logger.debug(f"{operation_name} run {i+1}: {end - start:.3f}s")
            except Exception as e:
                logger.error(f"{operation_name} failed on run {i+1}: {e}")
                continue
        
        if not times:
            return {"error": "All runs failed"}
        
        stats = {
            "mean": statistics.mean(times),
            "median": statistics.median(times),
            "min": min(times),
            "max": max(times),
            "std_dev": statistics.stdev(times) if len(times) > 1 else 0,
            "runs": len(times)
        }
        
        self.results[operation_name] = stats
        logger.info(f"{operation_name}: {stats['mean']:.3f}s avg (±{stats['std_dev']:.3f}s)")
        return stats
    
    def time_sync_operation(self, operation_name: str, operation, *args, runs: int = 5):
        """Time a sync operation multiple times and return statistics."""
        times = []
        
        for i in range(runs):
            start = time.perf_counter()
            try:
                result = operation(*args)
                end = time.perf_counter()
                times.append(end - start)
                logger.debug(f"{operation_name} run {i+1}: {end - start:.3f}s")
            except Exception as e:
                logger.error(f"{operation_name} failed on run {i+1}: {e}")
                continue
        
        if not times:
            return {"error": "All runs failed"}
        
        stats = {
            "mean": statistics.mean(times),
            "median": statistics.median(times),
            "min": min(times),
            "max": max(times),
            "std_dev": statistics.stdev(times) if len(times) > 1 else 0,
            "runs": len(times)
        }
        
        self.results[operation_name] = stats
        logger.info(f"{operation_name}: {stats['mean']:.3f}s avg (±{stats['std_dev']:.3f}s)")
        return stats
    
    async def test_file_operations(self):
        """Test async vs sync file operations."""
        logger.info("🔬 Testing File I/O Performance...")
        
        # Create a test file
        test_content = "This is a test file for performance testing.\n" * 1000
        test_file = Path("data/test_performance.txt")
        test_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(test_file, "w") as f:
            f.write(test_content)
        
        # Test sync vs async file reading
        await self.time_async_operation("Async File Read", _extract_text_txt_async, str(test_file))
        self.time_sync_operation("Sync File Read", _extract_text_txt, str(test_file))
        
        # Cleanup
        test_file.unlink(missing_ok=True)
    
    async def test_vector_operations(self):
        """Test vector store performance."""
        logger.info("🔬 Testing Vector Store Performance...")
        
        try:
            vector_store = VectorStore()
            
            # Test similarity search performance
            test_query = "employee benefits vacation policy"
            await self.time_async_operation(
                "Vector Similarity Search", 
                vector_store.similarity_search, 
                test_query, 
                5
            )
            
        except Exception as e:
            logger.warning(f"Vector store test skipped: {e}")
    
    async def test_storage_operations(self):
        """Test storage performance."""
        logger.info("🔬 Testing Storage Performance...")
        
        try:
            storage = FileStorage("data/test_storage")
            
            # Test put/get operations
            test_data = {"test": "data", "number": 42, "list": [1, 2, 3]}
            
            await self.time_async_operation("Storage Put", storage.put, "test_key", test_data)
            await self.time_async_operation("Storage Get", storage.get, "test_key")
            
            # Cleanup
            await storage.clear()
            
        except Exception as e:
            logger.warning(f"Storage test skipped: {e}")
    
    async def test_concurrent_processing(self):
        """Test concurrent document processing."""
        logger.info("🔬 Testing Concurrent Processing...")
        
        # Create multiple test files
        test_files = []
        for i in range(5):
            test_file = Path(f"data/test_doc_{i}.txt")
            test_file.parent.mkdir(parents=True, exist_ok=True)
            content = f"Test document {i} content.\n" * 100
            with open(test_file, "w") as f:
                f.write(content)
            test_files.append(test_file)
        
        try:
            # Test single document processing
            await self.time_async_operation(
                "Single Document Processing", 
                process_document, 
                str(test_files[0])
            )
            
            # Test concurrent processing (if knowledge base exists)
            if Path("data/knowledge").exists():
                await self.time_async_operation(
                    "Concurrent Knowledge Base Reload", 
                    reload_knowledge_base_concurrent,
                    None,  # cfg
                    3      # concurrency
                )
        
        finally:
            # Cleanup
            for test_file in test_files:
                test_file.unlink(missing_ok=True)
    
    async def test_llm_performance(self):
        """Test LLM service performance."""
        logger.info("🔬 Testing LLM Performance...")
        
        try:
            llm = GeminiService()
            test_messages = ["What are the company benefits?"]
            
            await self.time_async_operation(
                "LLM Response Generation", 
                llm.analyze_messages, 
                test_messages
            )
            
        except Exception as e:
            logger.warning(f"LLM test skipped: {e}")
    
    async def run_all_tests(self):
        """Run all performance tests."""
        logger.info("🚀 Starting Performance Test Suite...")
        
        await self.test_file_operations()
        await self.test_storage_operations()
        await self.test_vector_operations()
        await self.test_concurrent_processing()
        await self.test_llm_performance()
        
        self.print_summary()
    
    def print_summary(self):
        """Print a summary of all test results."""
        logger.info("\n" + "="*60)
        logger.info("📊 PERFORMANCE TEST RESULTS")
        logger.info("="*60)
        
        if not self.results:
            logger.info("No test results available")
            return
        
        # Calculate improvements
        improvements = {}
        
        # File operations
        if "Async File Read" in self.results and "Sync File Read" in self.results:
            sync_time = self.results["Sync File Read"]["mean"]
            async_time = self.results["Async File Read"]["mean"]
            improvement = ((sync_time - async_time) / sync_time) * 100
            improvements["File I/O"] = improvement
        
        # Print results
        for test_name, stats in self.results.items():
            if "error" in stats:
                logger.info(f"❌ {test_name}: {stats['error']}")
            else:
                logger.info(f"✅ {test_name}: {stats['mean']:.3f}s (±{stats['std_dev']:.3f}s)")
        
        # Print improvements
        if improvements:
            logger.info("\n📈 PERFORMANCE IMPROVEMENTS:")
            for operation, improvement in improvements.items():
                if improvement > 0:
                    logger.info(f"   {operation}: {improvement:.1f}% faster")
                else:
                    logger.info(f"   {operation}: {abs(improvement):.1f}% slower")
        
        logger.info("="*60)

async def main():
    """Main function for performance testing."""
    tester = PerformanceTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main()) 