#!/usr/bin/env python3
"""
Docker healthcheck script for HR Teams Bot

This script performs a health check by making a request to the /health endpoint
and validates that the application is responding correctly.
"""

import os
import sys
import urllib.request
import urllib.error
import json
import time


def main():
    """Perform health check."""
    # Get port from environment
    port = os.environ.get('PORT', '3978')
    host = os.environ.get('HOST', '0.0.0.0')
    app_instance = os.environ.get('APP_INSTANCE', 'jo')
    
    # Use localhost for health checks regardless of bind address
    health_url = f"http://localhost:{port}/health/"
    
    print(f"[HEALTHCHECK] Checking {app_instance} instance at {health_url}")
    
    try:
        # Create request with timeout
        request = urllib.request.Request(health_url)
        request.add_header('User-Agent', 'Docker-Healthcheck/1.0')
        
        # Make the request
        start_time = time.time()
        with urllib.request.urlopen(request, timeout=5) as response:
            response_time = time.time() - start_time
            
            # Check status code
            if response.status != 200:
                print(f"[HEALTHCHECK] ERROR: HTTP {response.status}")
                sys.exit(1)
            
            # Try to parse response
            try:
                data = json.loads(response.read().decode('utf-8'))
                status = data.get('status', 'unknown')
                
                if status != 'ok':
                    print(f"[HEALTHCHECK] ERROR: Status is '{status}', expected 'ok'")
                    sys.exit(1)
                
                print(f"[HEALTHCHECK] SUCCESS: {app_instance} instance healthy (response time: {response_time:.3f}s)")
                sys.exit(0)
                
            except json.JSONDecodeError:
                # If we can't parse JSON, but got 200, assume it's okay
                print(f"[HEALTHCHECK] SUCCESS: {app_instance} instance responding (response time: {response_time:.3f}s)")
                sys.exit(0)
    
    except urllib.error.HTTPError as e:
        print(f"[HEALTHCHECK] ERROR: HTTP {e.code} - {e.reason}")
        sys.exit(1)
    
    except urllib.error.URLError as e:
        print(f"[HEALTHCHECK] ERROR: Connection failed - {e.reason}")
        sys.exit(1)
    
    except Exception as e:
        print(f"[HEALTHCHECK] ERROR: Unexpected error - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 