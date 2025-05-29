"""
Microsoft Teams API Rate Limits Configuration

Based on Microsoft documentation and observed behavior:
- Teams enforces strict rate limits to prevent API abuse
- Conversation API: Observed safe limit is 3-4 requests per 10 seconds
- HTTP 429 "API calls quota exceeded" when limits are hit
- Streaming should be very conservative to avoid rate limits

Best practices:
1. Use larger chunks with longer delays for streaming
2. Batch updates when possible  
3. Implement exponential backoff on 429 errors
4. Monitor rate limit headers in responses
5. Leave significant buffer room in rate limits
"""

import random

# Rate limit configuration - Made more conservative based on observed 429 errors
TEAMS_RATE_LIMITS = {
    # Maximum API calls per time window - Reduced further after observing 429s
    "conversation_api": {
        "max_calls": 3,        # Reduced from 5 - very conservative
        "window_seconds": 10,
        "description": "Teams conversation API rate limit (conservative)"
    },
    
    # Streaming configuration for optimal performance - Slower streaming
    "streaming": {
        "throttle_seconds": 0.5,   # Balanced - not too fast, not too slow
        "chars_per_chunk": 100,    # Larger chunks to reduce API calls
        "max_chunk_size": 600,     # Reasonable max size
        "min_message_length": 800, # Only stream really long messages
        "min_chunk_delay": 0.3,    # Minimum delay between chunks
    },
    
    # Retry configuration for rate limit errors - More aggressive retries
    "retry": {
        "max_attempts": 4,         # Increased from 3
        "initial_delay": 3.0,      # Increased from 2.0
        "backoff_factor": 2.5,     # Increased from 2.0  
        "max_delay": 30.0,         # Increased from 10.0
        "jitter_max": 2.0,         # Add jitter to prevent thundering herd
    }
}

def get_safe_streaming_params():
    """Get streaming parameters that respect Teams rate limits."""
    s = TEAMS_RATE_LIMITS["streaming"]
    return {
        "avg_cps": s["chars_per_chunk"],
        "throttle": s["throttle_seconds"], 
        "max_len": s["max_chunk_size"],
        "min_delay": s["min_chunk_delay"],
    }

def get_rate_limit_config():
    """Get rate limiting configuration for the adapter."""
    api = TEAMS_RATE_LIMITS["conversation_api"]
    return {
        "max_calls": api["max_calls"],
        "window_seconds": api["window_seconds"],
    }

def get_retry_config():
    """Get retry configuration for handling 429 errors."""
    return TEAMS_RATE_LIMITS["retry"].copy()

def should_enable_streaming(message_length: int) -> bool:
    """Determine if streaming should be enabled based on message length."""
    return message_length > TEAMS_RATE_LIMITS["streaming"]["min_message_length"]

def calculate_backoff_delay(attempt: int, base_delay: float = None) -> float:
    """Calculate exponential backoff delay with jitter."""
    retry_config = TEAMS_RATE_LIMITS["retry"]
    base = base_delay or retry_config["initial_delay"]
    
    # Exponential backoff
    delay = base * (retry_config["backoff_factor"] ** attempt)
    delay = min(delay, retry_config["max_delay"])
    
    # Add jitter to prevent thundering herd
    jitter = random.uniform(0, retry_config["jitter_max"])
    return delay + jitter

def log_rate_limit_event(event_type: str, details: dict = None):
    """Log rate limiting events for monitoring."""
    import logging
    logger = logging.getLogger(__name__)
    
    if event_type == "429_error":
        logger.warning(f"Teams API rate limit hit: {details}")
    elif event_type == "backoff":
        logger.info(f"Rate limit backoff: waiting {details.get('delay', 0):.1f}s")
    elif event_type == "recovery":
        logger.info(f"Rate limit recovery after {details.get('attempts', 0)} failures")

# Emergency rate limiting - if things get really bad
EMERGENCY_LIMITS = {
    "max_calls": 2,
    "window_seconds": 15,
    "throttle_seconds": 2.0,
    "emergency_backoff": 60.0,  # 1 minute emergency backoff
}

def get_emergency_limits():
    """Get emergency rate limits when standard limits fail."""
    return EMERGENCY_LIMITS.copy()