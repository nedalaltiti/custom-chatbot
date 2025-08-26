#!/usr/bin/env python3
"""
Debug External Validation API

This script helps diagnose 502 Bad Gateway errors from the external validation API.
"""

import asyncio
import httpx
import json
import time
from datetime import datetime

API_BASE_URL = "https://underwriting-validator-dev.usclaritytech.com"
TIMEOUT = 30.0

async def test_api_connectivity():
    """Test basic connectivity to the external API."""
    print("🔍 DEBUGGING EXTERNAL VALIDATION API")
    print(f"📡 API Base URL: {API_BASE_URL}")
    print(f"⏱️  Timeout: {TIMEOUT}s")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Test 1: Basic connectivity
        print("\n1️⃣ BASIC CONNECTIVITY TEST")
        try:
            response = await client.get(API_BASE_URL)
            print(f"   ✅ Base URL accessible: {response.status_code}")
            print(f"   📄 Response headers: {dict(response.headers)}")
        except Exception as e:
            print(f"   ❌ Base URL failed: {e}")
        
        # Test 2: Health/Status endpoint
        print("\n2️⃣ HEALTH ENDPOINT TEST")
        health_endpoints = ["/health", "/status", "/api/health", "/api/status"]
        for endpoint in health_endpoints:
            try:
                response = await client.get(f"{API_BASE_URL}{endpoint}")
                print(f"   ✅ {endpoint}: {response.status_code}")
                if response.status_code == 200:
                    print(f"   📋 Response: {response.text[:200]}")
                    break
            except Exception as e:
                print(f"   ❌ {endpoint}: {e}")
        
        # Test 3: Validation endpoint structure
        print("\n3️⃣ VALIDATION ENDPOINT TEST")
        validation_endpoints = [
            "/api/validation",
            "/api/validation/combined", 
            "/validation",
            "/validation/combined"
        ]
        
        for endpoint in validation_endpoints:
            try:
                # Try GET first
                response = await client.get(f"{API_BASE_URL}{endpoint}")
                print(f"   📍 GET {endpoint}: {response.status_code}")
                
                # Try POST with test payload
                test_payload = {
                    "contact_id": 123456,
                    "user_id": "debug-test",
                    "user_name": "debug-user"
                }
                
                response = await client.post(
                    f"{API_BASE_URL}{endpoint}", 
                    json=test_payload
                )
                print(f"   📍 POST {endpoint}: {response.status_code}")
                
                if response.status_code != 502:
                    print(f"   📋 Response: {response.text[:200]}")
                    if response.status_code == 200:
                        print("   🎉 FOUND WORKING ENDPOINT!")
                        
            except Exception as e:
                print(f"   ❌ {endpoint}: {e}")
        
        # Test 4: DNS and network diagnostics
        print("\n4️⃣ NETWORK DIAGNOSTICS")
        try:
            import socket
            domain = "underwriting-validator-dev.usclaritytech.com"
            ip = socket.gethostbyname(domain)
            print(f"   🌐 DNS Resolution: {domain} → {ip}")
        except Exception as e:
            print(f"   ❌ DNS Resolution failed: {e}")
        
        # Test 5: SSL Certificate check
        print("\n5️⃣ SSL CERTIFICATE CHECK")
        try:
            import ssl
            import socket
            
            context = ssl.create_default_context()
            with socket.create_connection(("underwriting-validator-dev.usclaritytech.com", 443)) as sock:
                with context.wrap_socket(sock, server_hostname="underwriting-validator-dev.usclaritytech.com") as ssock:
                    cert = ssock.getpeercert()
                    print(f"   🔒 SSL Certificate valid")
                    print(f"   📅 Expires: {cert.get('notAfter', 'Unknown')}")
        except Exception as e:
            print(f"   ❌ SSL Certificate issue: {e}")

async def test_specific_contact():
    """Test the specific contact ID that was failing."""
    print("\n6️⃣ SPECIFIC CONTACT TEST")
    contact_id = 1137524603  # From the error log
    
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        payload = {
            "contact_id": contact_id,
            "user_id": "debug-test",
            "user_name": "debug-user"
        }
        
        try:
            start_time = time.time()
            response = await client.post(
                f"{API_BASE_URL}/api/validation/combined",
                json=payload
            )
            duration = time.time() - start_time
            
            print(f"   📞 Contact ID: {contact_id}")
            print(f"   📊 Status Code: {response.status_code}")
            print(f"   ⏱️  Response Time: {duration:.2f}s")
            print(f"   📄 Response Headers: {dict(response.headers)}")
            print(f"   📋 Response Body: {response.text[:500]}")
            
        except Exception as e:
            print(f"   ❌ Contact validation failed: {e}")

async def main():
    """Run all diagnostic tests."""
    print(f"🚀 Starting API diagnostics at {datetime.now()}")
    
    await test_api_connectivity()
    await test_specific_contact()
    
    print("\n" + "=" * 60)
    print("🎯 RECOMMENDATIONS:")
    print("   • If all tests fail → External API is completely down")
    print("   • If base URL works but endpoints fail → API structure changed")
    print("   • If SSL fails → Certificate expired or misconfigured")
    print("   • If DNS fails → Domain/network configuration issue")
    print("   • Check with the external API team for service status")

if __name__ == "__main__":
    asyncio.run(main())
