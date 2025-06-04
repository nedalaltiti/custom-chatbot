#!/usr/bin/env python3
"""
Simple Load Test Runner for QA Team

Runs the exact sequence requested:
1. 100 requests
2. 200 requests  
3. 1000 requests
4. 100 requests (recovery test)

Usage:
    python tests/run_load_tests.py
    python tests/run_load_tests.py --url http://your-server:3978
    python tests/run_load_tests.py --quick  # Skip 1000 request test
"""

import sys
import os
import asyncio
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "src"))

# Import the load tester
sys.path.append(str(Path(__file__).parent / "load_testing"))
from load_test import HRBotLoadTester

async def run_qa_load_tests(base_url: str, quick_mode: bool = False):
    """Run the QA team's requested load test sequence."""
    
    print("🚀 HR Bot Load Testing - QA Sequence")
    print("=" * 50)
    print(f"Target URL: {base_url}")
    print(f"Quick Mode: {'Yes' if quick_mode else 'No'}")
    print()
    
    # Define test sequence as requested by QA
    if quick_mode:
        test_sequence = [
            (100, "Initial Load (100 requests)"),
            (200, "Medium Load (200 requests)"),
            (100, "Recovery Test (100 requests)")
        ]
    else:
        test_sequence = [
            (100, "Initial Load (100 requests)"),
            (200, "Medium Load (200 requests)"), 
            (1000, "High Load (1000 requests)"),
            (100, "Recovery Test (100 requests)")
        ]
    
    results = []
    
    async with HRBotLoadTester(base_url) as tester:
        # Health check first
        print("🏥 Health Check...")
        if not await tester.health_check():
            print("❌ FAILED: Service is not responding!")
            print("   Make sure the HR Bot is running at:", base_url)
            return False
        print("✅ Service is healthy and ready for testing")
        print()
        
        # Run each test in sequence
        for i, (num_requests, description) in enumerate(test_sequence, 1):
            print(f"🧪 Test {i}/{len(test_sequence)}: {description}")
            print("-" * 40)
            
            try:
                # Run the load test
                summary = await tester.run_load_test(num_requests)
                results.append((description, summary))
                
                # Show immediate results
                success_rate = (summary.successful_requests / summary.total_requests) * 100
                print(f"✅ Results:")
                print(f"   Success Rate: {success_rate:.1f}% ({summary.successful_requests}/{summary.total_requests})")
                print(f"   Requests/sec: {summary.requests_per_second:.2f}")
                print(f"   Avg Response: {summary.avg_response_time:.3f}s")
                print(f"   P95 Response: {summary.p95_response_time:.3f}s")
                print(f"   First Chunk:  {summary.avg_first_chunk_time:.3f}s")
                
                if summary.errors:
                    print(f"   ⚠️ Errors: {summary.errors}")
                
                # Determine if test passed
                test_passed = success_rate >= 85 and summary.avg_response_time < 10
                print(f"   Status: {'🟢 PASS' if test_passed else '🔴 FAIL'}")
                
            except Exception as e:
                print(f"❌ Test failed with error: {e}")
                results.append((description, None))
            
            print()
            
            # Cool down between tests (except after last test)
            if i < len(test_sequence):
                cooldown = 10 if num_requests >= 1000 else 5
                print(f"💤 Cooling down for {cooldown} seconds...")
                await asyncio.sleep(cooldown)
                print()
    
    # Generate final report
    print("=" * 50)
    print("📊 FINAL QA TEST REPORT")
    print("=" * 50)
    
    all_passed = True
    
    for description, summary in results:
        if summary is None:
            print(f"❌ {description}: FAILED (Error)")
            all_passed = False
            continue
            
        success_rate = (summary.successful_requests / summary.total_requests) * 100
        test_passed = success_rate >= 85 and summary.avg_response_time < 10
        
        status = "🟢 PASS" if test_passed else "🔴 FAIL"
        if not test_passed:
            all_passed = False
            
        print(f"{status} {description}:")
        print(f"      Success Rate: {success_rate:.1f}%")
        print(f"      Avg Response: {summary.avg_response_time:.3f}s")
        print(f"      Requests/sec: {summary.requests_per_second:.2f}")
        
        if summary.errors:
            print(f"      Errors: {list(summary.errors.keys())}")
        print()
    
    # Overall result
    overall_status = "🎉 ALL TESTS PASSED" if all_passed else "⚠️ SOME TESTS FAILED"
    print(overall_status)
    print()
    
    # Recommendations
    if not all_passed:
        print("🔧 RECOMMENDATIONS:")
        print("1. Check the optimization guide: optimization_guide.md")
        print("2. Increase database connection pool size")
        print("3. Optimize streaming settings")
        print("4. Monitor system resources during tests")
        print()
    
    return all_passed

def main():
    parser = argparse.ArgumentParser(description="QA Load Testing for HR Bot")
    parser.add_argument(
        "--url", 
        default="http://localhost:3978", 
        help="Base URL of the HR Bot service (default: http://localhost:3978)"
    )
    parser.add_argument(
        "--quick", 
        action="store_true", 
        help="Quick mode: skip the 1000 request test"
    )
    
    args = parser.parse_args()
    
    print("Starting QA Load Tests...")
    print("Press Ctrl+C to cancel")
    print()
    
    try:
        success = asyncio.run(run_qa_load_tests(args.url, args.quick))
        exit_code = 0 if success else 1
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n🛑 Tests cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test runner failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 