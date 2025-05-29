#!/usr/bin/env python3
"""
Debug greeting detection issues.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from hrbot.utils.message import split_greeting

def test_problematic_cases():
    """Test cases that are causing issues."""
    test_cases = [
        "nothing",
        "bye", 
        "hello",
        "hi",
        "nothing else",
        "bye bye",
        "Nothing at all",
        "BYE",
        "good morning",
        "I need nothing",
        "nothing special",
    ]
    
    print("Testing problematic greeting detection cases...\n")
    
    for test_input in test_cases:
        greet_only, user_payload = split_greeting(test_input)
        has_greeting = greet_only or user_payload
        
        print(f"Input: '{test_input}'")
        print(f"  greet_only: {greet_only}")
        print(f"  user_payload: '{user_payload}'")
        print(f"  has_greeting: {has_greeting}")
        print(f"  should_show_card: {has_greeting}")
        print()

def test_awaiting_more_help_scenario():
    """Test the scenario where bot asks 'anything else' and user says 'nothing'."""
    print("=== Testing 'awaiting_more_help' scenario ===")
    
    # This simulates when bot has asked "Is there anything else I can help you with?"
    # and user responds with "nothing"
    user_response = "nothing"
    
    # In teams.py, this should be handled by the "awaiting_more_help" logic
    # NOT by the greeting detection logic
    
    print(f"User responds to 'anything else?' with: '{user_response}'")
    
    # Check if it matches negative responses
    msg_lower = user_response.lower().strip()
    negative_responses = ["no", "nope", "nothing", "that's all", "that is all", "done", "finished", "bye", "goodbye", "thanks"]
    
    is_negative = any(word in msg_lower for word in negative_responses)
    print(f"Is negative response: {is_negative}")
    
    # Check greeting detection
    greet_only, user_payload = split_greeting(user_response)
    has_greeting = greet_only or user_payload
    print(f"Greeting detection triggered: {has_greeting}")
    
    print("\n✅ Expected behavior:")
    print("- 'nothing' should be handled as negative response to 'anything else?'")
    print("- Should NOT trigger greeting card")
    print("- Should end conversation and show feedback card")

if __name__ == "__main__":
    test_problematic_cases()
    print("\n" + "="*60 + "\n")
    test_awaiting_more_help_scenario() 