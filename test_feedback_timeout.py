#!/usr/bin/env python3
"""
Test feedback timeout logic to ensure feedback cards don't appear too frequently.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from datetime import datetime, timedelta

def test_feedback_timeout():
    """Test the feedback timeout logic."""
    
    # Import the function we're testing
    sys.path.append('src/hrbot/api/routers')
    from teams import _should_show_feedback
    
    print("Testing feedback timeout logic...\n")
    
    # Test 1: No feedback shown before
    state = {}
    result = _should_show_feedback(state)
    print(f"Test 1 - No feedback before: {result} (should be True)")
    
    # Test 2: Feedback shown but no timestamp
    state = {"feedback_shown": True}
    result = _should_show_feedback(state)
    print(f"Test 2 - Feedback shown, no timestamp: {result} (should be True)")
    
    # Test 3: Feedback shown recently (less than 10 minutes ago)
    recent_time = datetime.utcnow().timestamp() - 300  # 5 minutes ago
    state = {"feedback_shown": True, "last_feedback_time": recent_time}
    result = _should_show_feedback(state)
    print(f"Test 3 - Feedback 5 minutes ago: {result} (should be False)")
    
    # Test 4: Feedback shown long ago (more than 10 minutes ago)
    old_time = datetime.utcnow().timestamp() - 700  # 11+ minutes ago
    state = {"feedback_shown": True, "last_feedback_time": old_time}
    result = _should_show_feedback(state)
    print(f"Test 4 - Feedback 11+ minutes ago: {result} (should be True)")
    
    print("\n✅ Summary of expected behavior:")
    print("- Feedback cards should only appear once every 10 minutes")
    print("- Giving feedback (like/dislike) should NOT end the session")
    print("- Users should be able to continue asking questions after feedback")
    print("- No greeting cards should appear for returning users")

if __name__ == "__main__":
    test_feedback_timeout() 