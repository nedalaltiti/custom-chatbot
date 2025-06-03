#!/usr/bin/env python3
"""
Load Testing Script for HR Bot with Streaming Support

Tests the application under different load scenarios:
- 100 concurrent requests
- 200 concurrent requests  
- 1000 concurrent requests
- Back to 100 requests

Measures performance metrics including streaming response times.
"""

import asyncio
import aiohttp
import time
import json
import statistics
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass, asdict
import argparse


@dataclass
class TestResult:
    """Results from a single request."""
    request_id: int
    status_code: int
    response_time: float
    first_chunk_time: float  # Time to first streaming chunk
    total_chunks: int
    total_response_length: int
    error: str = None
    is_streaming: bool = False


@dataclass
class LoadTestSummary:
    """Summary of load test results."""
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time: float
    p95_response_time: float
    p99_response_time: float
    avg_first_chunk_time: float
    requests_per_second: float
    total_duration: float
    errors: Dict[str, int]


class HRBotLoadTester:
    """Load tester for HR Bot API with streaming support."""
    
    def __init__(self, base_url: str = "http://localhost:3978"):
        self.base_url = base_url
        self.session: aiohttp.ClientSession = None
        
        # Test payloads (realistic HR questions)
        self.test_payloads = [
            {
                "type": "message",
                "text": "What is the resignation process?",
                "from": {"id": f"test-user-{{}}"},
                "conversation": {"id": f"test-conv-{{}}"},
                "serviceUrl": "https://test.service.url"
            },
            {
                "type": "message", 
                "text": "Tell me about employee benefits",
                "from": {"id": f"test-user-{{}}"},
                "conversation": {"id": f"test-conv-{{}}"},
                "serviceUrl": "https://test.service.url"
            },
            {
                "type": "message",
                "text": "How do I submit a leave request?", 
                "from": {"id": f"test-user-{{}}"},
                "conversation": {"id": f"test-conv-{{}}"},
                "serviceUrl": "https://test.service.url"
            },
            {
                "type": "message",
                "text": "What are the working hours policy?",
                "from": {"id": f"test-user-{{}}"},
                "conversation": {"id": f"test-conv-{{}}"},
                "serviceUrl": "https://test.service.url"
            },
            {
                "type": "message",
                "text": "NOI process information",
                "from": {"id": f"test-user-{{}}"},
                "conversation": {"id": f"test-conv-{{}}"},
                "serviceUrl": "https://test.service.url"
            }
        ]
    
    async def __aenter__(self):
        """Async context manager entry."""
        connector = aiohttp.TCPConnector(
            limit=2000,  # High connection limit for load testing
            limit_per_host=1000,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(
            total=120,  # 2 minutes total timeout
            connect=10,  # 10 seconds to connect
            sock_read=60  # 1 minute to read response
        )
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"Content-Type": "application/json"}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def health_check(self) -> bool:
        """Check if the service is healthy before testing."""
        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                return response.status == 200
        except Exception as e:
            print(f"Health check failed: {e}")
            return False
    
    async def send_single_request(self, request_id: int) -> TestResult:
        """Send a single request and measure performance."""
        start_time = time.time()
        first_chunk_time = None
        total_chunks = 0
        total_length = 0
        
        # Select payload (cycle through them)
        payload = self.test_payloads[request_id % len(self.test_payloads)].copy()
        
        # Make unique IDs for this request
        payload["from"]["id"] = payload["from"]["id"].format(request_id)
        payload["conversation"]["id"] = payload["conversation"]["id"].format(request_id)
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/messages",
                json=payload
            ) as response:
                
                status_code = response.status
                
                if response.status != 200:
                    error_text = await response.text()
                    return TestResult(
                        request_id=request_id,
                        status_code=status_code,
                        response_time=time.time() - start_time,
                        first_chunk_time=0,
                        total_chunks=0,
                        total_response_length=0,
                        error=f"HTTP {status_code}: {error_text[:200]}"
                    )
                
                # Handle streaming response
                content_type = response.headers.get('content-type', '')
                is_streaming = 'text/plain' in content_type or 'text/event-stream' in content_type
                
                if is_streaming:
                    # Read streaming response
                    async for chunk in response.content.iter_chunked(1024):
                        if chunk:
                            if first_chunk_time is None:
                                first_chunk_time = time.time() - start_time
                            total_chunks += 1
                            total_length += len(chunk)
                else:
                    # Read regular JSON response
                    response_text = await response.text()
                    total_length = len(response_text)
                    first_chunk_time = time.time() - start_time
                    total_chunks = 1
                
                response_time = time.time() - start_time
                
                return TestResult(
                    request_id=request_id,
                    status_code=status_code,
                    response_time=response_time,
                    first_chunk_time=first_chunk_time or response_time,
                    total_chunks=total_chunks,
                    total_response_length=total_length,
                    is_streaming=is_streaming
                )
                
        except asyncio.TimeoutError:
            return TestResult(
                request_id=request_id,
                status_code=0,
                response_time=time.time() - start_time,
                first_chunk_time=0,
                total_chunks=0,
                total_response_length=0,
                error="Request timeout"
            )
        except Exception as e:
            return TestResult(
                request_id=request_id,
                status_code=0,
                response_time=time.time() - start_time,
                first_chunk_time=0,
                total_chunks=0,
                total_response_length=0,
                error=str(e)
            )
    
    async def run_load_test(self, num_requests: int, max_concurrent: int = None) -> LoadTestSummary:
        """Run load test with specified number of requests."""
        if max_concurrent is None:
            max_concurrent = min(num_requests, 100)  # Reasonable default
        
        print(f"🚀 Starting load test: {num_requests} requests, max {max_concurrent} concurrent")
        
        start_time = time.time()
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def bounded_request(request_id: int) -> TestResult:
            async with semaphore:
                return await self.send_single_request(request_id)
        
        # Create all tasks
        tasks = [bounded_request(i) for i in range(num_requests)]
        
        # Execute with progress reporting
        results = []
        completed = 0
        
        for task in asyncio.as_completed(tasks):
            result = await task
            results.append(result)
            completed += 1
            
            if completed % max(1, num_requests // 10) == 0:
                progress = (completed / num_requests) * 100
                print(f"   Progress: {completed}/{num_requests} ({progress:.1f}%)")
        
        total_duration = time.time() - start_time
        
        # Analyze results
        successful_results = [r for r in results if r.status_code == 200 and not r.error]
        failed_results = [r for r in results if r.status_code != 200 or r.error]
        
        # Calculate metrics
        if successful_results:
            response_times = [r.response_time for r in successful_results]
            first_chunk_times = [r.first_chunk_time for r in successful_results if r.first_chunk_time > 0]
            
            avg_response_time = statistics.mean(response_times)
            p95_response_time = statistics.quantile(response_times, 0.95) if len(response_times) > 1 else avg_response_time
            p99_response_time = statistics.quantile(response_times, 0.99) if len(response_times) > 1 else avg_response_time
            avg_first_chunk_time = statistics.mean(first_chunk_times) if first_chunk_times else 0
        else:
            avg_response_time = 0
            p95_response_time = 0
            p99_response_time = 0
            avg_first_chunk_time = 0
        
        # Count errors
        errors = {}
        for result in failed_results:
            error_key = result.error or f"HTTP {result.status_code}"
            errors[error_key] = errors.get(error_key, 0) + 1
        
        requests_per_second = num_requests / total_duration if total_duration > 0 else 0
        
        return LoadTestSummary(
            total_requests=num_requests,
            successful_requests=len(successful_results),
            failed_requests=len(failed_results),
            avg_response_time=avg_response_time,
            p95_response_time=p95_response_time,
            p99_response_time=p99_response_time,
            avg_first_chunk_time=avg_first_chunk_time,
            requests_per_second=requests_per_second,
            total_duration=total_duration,
            errors=errors
        )


async def run_full_load_test_suite(base_url: str, output_file: str = None):
    """Run the complete load test suite: 100 -> 200 -> 1000 -> 100."""
    
    test_scenarios = [
        (100, "Initial Load Test"),
        (200, "Medium Load Test"), 
        (1000, "High Load Test"),
        (100, "Recovery Test")
    ]
    
    results = {}
    
    async with HRBotLoadTester(base_url) as tester:
        # Health check first
        print("🏥 Performing health check...")
        if not await tester.health_check():
            print("❌ Health check failed! Ensure the service is running.")
            return
        print("✅ Service is healthy")
        
        print(f"\n📊 Starting Load Test Suite at {datetime.now()}")
        print("=" * 60)
        
        for num_requests, description in test_scenarios:
            print(f"\n🧪 {description}")
            print("-" * 40)
            
            # Run the test
            summary = await tester.run_load_test(num_requests)
            results[description] = asdict(summary)
            
            # Print results
            print(f"✅ Completed: {summary.successful_requests}/{summary.total_requests} successful")
            print(f"📈 Requests/sec: {summary.requests_per_second:.2f}")
            print(f"⏱️  Avg response time: {summary.avg_response_time:.3f}s")
            print(f"⏱️  P95 response time: {summary.p95_response_time:.3f}s") 
            print(f"⏱️  First chunk time: {summary.avg_first_chunk_time:.3f}s")
            
            if summary.errors:
                print(f"❌ Errors: {summary.errors}")
            
            # Cool down between tests
            if num_requests < 1000:
                print("💤 Cooling down for 5 seconds...")
                await asyncio.sleep(5)
    
    # Generate report
    print("\n" + "=" * 60)
    print("📊 LOAD TEST SUITE COMPLETE")
    print("=" * 60)
    
    for description, result in results.items():
        print(f"\n{description}:")
        print(f"  Success Rate: {(result['successful_requests']/result['total_requests']*100):.1f}%")
        print(f"  Requests/sec: {result['requests_per_second']:.2f}")
        print(f"  Avg Response: {result['avg_response_time']:.3f}s")
        print(f"  P95 Response: {result['p95_response_time']:.3f}s")
    
    # Save detailed results
    if output_file:
        with open(output_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'base_url': base_url,
                'results': results
            }, f, indent=2)
        print(f"\n📁 Detailed results saved to: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HR Bot Load Testing")
    parser.add_argument("--url", default="http://localhost:3978", help="Base URL of the service")
    parser.add_argument("--output", help="Output file for detailed results")
    parser.add_argument("--requests", type=int, help="Run single test with N requests")
    
    args = parser.parse_args()
    
    if args.requests:
        # Single test mode
        async def single_test():
            async with HRBotLoadTester(args.url) as tester:
                if await tester.health_check():
                    summary = await tester.run_load_test(args.requests)
                    print(f"Results: {summary.successful_requests}/{summary.total_requests} successful")
                    print(f"Avg response time: {summary.avg_response_time:.3f}s")
        
        asyncio.run(single_test())
    else:
        # Full suite
        asyncio.run(run_full_load_test_suite(args.url, args.output)) 