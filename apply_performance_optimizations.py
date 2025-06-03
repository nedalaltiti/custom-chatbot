#!/usr/bin/env python3
"""
Performance Optimization Applier

Automatically applies key performance optimizations for load testing.
Run this before your load tests to ensure optimal performance.
"""

import os
from pathlib import Path
import shutil

def apply_database_optimizations():
    """Apply database connection pool optimizations to .env files."""
    print("🔧 Applying database optimizations...")
    
    optimizations = {
        "DB_POOL_SIZE": "20",
        "DB_MAX_OVERFLOW": "50", 
        "DB_POOL_TIMEOUT": "60",
        "DB_POOL_RECYCLE": "3600"
    }
    
    # Find all .env files
    env_files = []
    for pattern in [".env", ".env.jo", ".env.us"]:
        if Path(pattern).exists():
            env_files.append(pattern)
    
    if not env_files:
        print("  ⚠️ No .env files found, creating .env with optimizations")
        env_files = [".env"]
    
    for env_file in env_files:
        print(f"  📝 Updating {env_file}")
        
        # Read existing content
        existing_content = {}
        if Path(env_file).exists():
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        existing_content[key] = value
        
        # Add optimizations
        existing_content.update(optimizations)
        
        # Write back
        with open(env_file, 'w') as f:
            f.write("# Database optimizations for load testing\n")
            for key, value in existing_content.items():
                f.write(f"{key}={value}\n")
    
    print("  ✅ Database optimizations applied")

def apply_performance_settings():
    """Apply performance settings to .env files."""
    print("🚀 Applying performance settings...")
    
    performance_settings = {
        "CACHE_EMBEDDINGS": "true",
        "CACHE_TTL_SECONDS": "7200",
        "MIN_STREAMING_LENGTH": "100", 
        "ENABLE_STREAMING": "true",
        "STREAMING_DELAY": "0.8",
        "SESSION_IDLE_MINUTES": "60"
    }
    
    # Apply to all .env files
    for pattern in [".env", ".env.jo", ".env.us"]:
        if Path(pattern).exists():
            print(f"  📝 Updating {pattern}")
            
            # Append performance settings
            with open(pattern, 'a') as f:
                f.write("\n# Performance optimizations for load testing\n")
                for key, value in performance_settings.items():
                    f.write(f"{key}={value}\n")
    
    print("  ✅ Performance settings applied")

def create_optimized_startup_script():
    """Create an optimized startup script for load testing."""
    print("🎯 Creating optimized startup script...")
    
    startup_script = """#!/bin/bash
# Optimized startup script for load testing
# Usage: ./start_for_load_testing.sh

echo "🚀 Starting HR Bot with load testing optimizations..."

# Set optimized uvicorn settings
export UVICORN_WORKERS=2
export UVICORN_WORKER_CLASS="uvicorn.workers.UvicornWorker"
export UVICORN_LOOP="asyncio"
export UVICORN_HTTP="httptools"
export UVICORN_KEEPALIVE_TIMEOUT=5

# Start with optimized settings
uvicorn hrbot.api.app:app \\
    --host 0.0.0.0 \\
    --port 3978 \\
    --workers 2 \\
    --worker-class uvicorn.workers.UvicornWorker \\
    --loop asyncio \\
    --http httptools \\
    --access-log \\
    --keepalive-timeout 5

echo "✅ HR Bot started with load testing optimizations"
"""
    
    with open("start_for_load_testing.sh", 'w') as f:
        f.write(startup_script)
    
    # Make executable
    os.chmod("start_for_load_testing.sh", 0o755)
    
    print("  ✅ Created start_for_load_testing.sh")

def create_monitoring_script():
    """Create a simple monitoring script for load testing."""
    print("📊 Creating monitoring script...")
    
    monitoring_script = """#!/usr/bin/env python3
# Simple monitoring script for load testing
import asyncio
import time
import sys
import os
sys.path.append('src')

from hrbot.db.session import get_connection_pool_status

async def monitor_performance():
    \"\"\"Monitor key performance metrics during load testing.\"\"\"
    print("📊 Starting performance monitoring...")
    print("Press Ctrl+C to stop")
    print()
    
    try:
        while True:
            try:
                # Get database pool status
                pool_status = await get_connection_pool_status()
                
                print(f"⏱️  {time.strftime('%H:%M:%S')} | "
                      f"DB Pool: {pool_status.get('checked_out', 0)}/{pool_status.get('size', 0)} "
                      f"({pool_status.get('utilization_percent', 0):.1f}%) | "
                      f"Available: {pool_status.get('total_available', 0)}")
                
                await asyncio.sleep(5)
                
            except Exception as e:
                print(f"❌ Monitoring error: {e}")
                await asyncio.sleep(5)
                
    except KeyboardInterrupt:
        print("\\n🛑 Monitoring stopped")

if __name__ == "__main__":
    asyncio.run(monitor_performance())
"""
    
    with open("monitor_performance.py", 'w') as f:
        f.write(monitoring_script)
    
    os.chmod("monitor_performance.py", 0o755)
    
    print("  ✅ Created monitor_performance.py")

def create_quick_test_script():
    """Create a quick health and performance test."""
    print("🧪 Creating quick test script...")
    
    test_script = """#!/usr/bin/env python3
# Quick performance test script
import asyncio
import time
import sys
import os
sys.path.append('src')
sys.path.append('tests/load_testing')

from load_test import HRBotLoadTester

async def quick_test():
    \"\"\"Run a quick 10-request test to verify performance.\"\"\"
    print("🧪 Quick Performance Test")
    print("=" * 30)
    
    async with HRBotLoadTester() as tester:
        # Health check
        if not await tester.health_check():
            print("❌ Service not responding!")
            return
        
        print("✅ Service healthy, running 10 test requests...")
        
        # Run quick test
        summary = await tester.run_load_test(10)
        
        print("\\n📊 Results:")
        print(f"  Success Rate: {(summary.successful_requests/summary.total_requests*100):.1f}%")
        print(f"  Avg Response: {summary.avg_response_time:.3f}s")
        print(f"  First Chunk:  {summary.avg_first_chunk_time:.3f}s")
        print(f"  Requests/sec: {summary.requests_per_second:.2f}")
        
        if summary.errors:
            print(f"  ⚠️ Errors: {summary.errors}")
        
        # Performance assessment
        if summary.avg_response_time < 2.0 and summary.successful_requests == summary.total_requests:
            print("\\n🟢 Performance looks good for load testing!")
        else:
            print("\\n🟡 Consider applying optimizations before full load test")

if __name__ == "__main__":
    asyncio.run(quick_test())
"""
    
    with open("quick_test.py", 'w') as f:
        f.write(test_script)
    
    os.chmod("quick_test.py", 0o755)
    
    print("  ✅ Created quick_test.py")

def main():
    """Apply all performance optimizations."""
    print("🚀 HR Bot Performance Optimization Setup")
    print("=" * 50)
    print("This will optimize your HR Bot for load testing")
    print()
    
    try:
        # Apply optimizations
        apply_database_optimizations()
        apply_performance_settings()
        create_optimized_startup_script()
        create_monitoring_script()
        create_quick_test_script()
        
        print()
        print("=" * 50)
        print("✅ OPTIMIZATION COMPLETE!")
        print("=" * 50)
        print()
        print("🎯 Next Steps:")
        print("1. Start your app with optimizations:")
        print("   ./start_for_load_testing.sh")
        print()
        print("2. Run a quick test to verify:")
        print("   python quick_test.py")
        print()
        print("3. Monitor performance (in another terminal):")
        print("   python monitor_performance.py")
        print()
        print("4. Run the full QA load test:")
        print("   python tests/run_load_tests.py")
        print()
        print("📖 For more optimizations, see: optimization_guide.md")
        
    except Exception as e:
        print(f"❌ Optimization failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 