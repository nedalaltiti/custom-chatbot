#!/usr/bin/env python3
"""
Test the new greeting logic to ensure it works as expected.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from hrbot.utils.message import split_greeting

def test_new_greeting_logic():
    """Test the new greeting logic scenarios."""
    test_cases = [
        # (input, should_show_card, processed_message)
        ("hi", True, None),  # Just greeting → show card, no further processing
        ("hi! i want to quit my work", True, "i want to quit my work"),  # Greeting + question → show card + process question
        ("hello, what are the leave policies?", True, "what are the leave policies?"),  # Greeting + question
        ("I want to quit", False, "I want to quit"),  # No greeting → no card, process as is
        ("good morning! help me with benefits", True, "help me with benefits"),  # Greeting + question
        ("hey there, resignation process?", True, "resignation process?"),  # Greeting + question
    ]
    
    print("Testing new greeting logic...\n")
    
    all_passed = True
    for i, (input_msg, should_show_card, expected_processed) in enumerate(test_cases, 1):
        greet_only, user_payload = split_greeting(input_msg)
        
        # Simulate the new logic from teams.py
        has_greeting = greet_only or user_payload
        if has_greeting:
            if user_payload:
                processed_message = user_payload.strip()
            else:
                processed_message = None
        else:
            processed_message = input_msg
            
        print(f"Test {i}: '{input_msg}'")
        print(f"  split_greeting returned: greet_only={greet_only}, user_payload='{user_payload}'")
        print(f"  Expected: show_card={should_show_card}, processed='{expected_processed}'")
        print(f"  Actual:   show_card={has_greeting}, processed='{processed_message}'")
        
        if has_greeting == should_show_card and processed_message == expected_processed:
            print(f"  ✅ PASS")
        else:
            print(f"  ❌ FAIL")
            all_passed = False
        print()
    
    return all_passed

if __name__ == "__main__":
    success = test_new_greeting_logic()
    if success:
        print("🎉 All greeting behavior tests passed!")
        print("\nBehavior Summary:")
        print("• 'hi' → shows greeting card, no further processing")
        print("• 'hi! question' → shows greeting card AND processes question")
        print("• 'question' → no greeting card, processes question normally")
    else:
        print("⚠️ Some greeting behavior tests failed.") 