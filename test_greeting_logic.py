#!/usr/bin/env python3
"""
Test greeting detection logic.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from hrbot.utils.message import split_greeting

def test_greeting_logic():
    """Test various greeting scenarios."""
    test_cases = [
        # (input, expected_greet_only, expected_remainder)
        ("hi", True, ""),
        ("hello", True, ""),
        ("hi!", True, ""),
        ("hi I want to quit my work", False, "I want to quit my work"),
        ("hello, I need help with leave policy", False, "I need help with leave policy"),
        ("hey what are the benefits?", False, "what are the benefits?"),
        ("good morning, can you help me?", False, "can you help me?"),
        ("I want to quit", False, "I want to quit"),  # No greeting, should not match
        ("Hi! What is the resignation process?", False, "What is the resignation process?"),
    ]
    
    print("Testing greeting detection logic...\n")
    
    all_passed = True
    for i, (input_msg, expected_greet_only, expected_remainder) in enumerate(test_cases, 1):
        greet_only, remainder = split_greeting(input_msg)
        
        print(f"Test {i}: '{input_msg}'")
        print(f"  Expected: greet_only={expected_greet_only}, remainder='{expected_remainder}'")
        print(f"  Actual:   greet_only={greet_only}, remainder='{remainder}'")
        
        if greet_only == expected_greet_only and remainder == expected_remainder:
            print(f"  ✅ PASS")
        else:
            print(f"  ❌ FAIL")
            all_passed = False
        print()
    
    return all_passed

if __name__ == "__main__":
    success = test_greeting_logic()
    if success:
        print("🎉 All greeting tests passed!")
    else:
        print("⚠️ Some greeting tests failed.") 