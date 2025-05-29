#!/usr/bin/env python3
"""
Test script to demonstrate response speed improvements.

This shows how the bot now:
1. Sends immediate typing indicator
2. Shows "looking into it" for complex queries
3. Streams responses starting at 200 chars (down from 500)
4. Uses faster streaming with 0.5s throttle (down from 1s)
"""

import asyncio
import time
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from hrbot.utils.message import split_greeting

# Simulated responses of different lengths
SHORT_RESPONSE = "Your vacation balance is 15 days. You can check details in the HR portal."

MEDIUM_RESPONSE = """
According to our vacation policy, you have 15 days of annual leave remaining this year.

• Annual leave must be taken within the calendar year
• Unused days can be carried forward (maximum 5 days)
• Submit requests through the HR portal at least 2 weeks in advance

Is there anything else I can help you with?
""".strip()

LONG_RESPONSE = """
I'll help you understand our comprehensive vacation and leave policies.

Our company provides several types of leave:

1. **Annual Vacation Leave**
   • Full-time employees receive 21 days per year
   • Part-time employees receive pro-rated days based on hours worked
   • New employees accrue 1.75 days per month in their first year

2. **Sick Leave**
   • 10 days per year for personal illness
   • Doctor's note required after 3 consecutive days
   • Unused sick days do not carry forward

3. **Personal Leave**
   • 3 days per year for personal matters
   • No documentation required
   • Must be approved by your manager

4. **Bereavement Leave**
   • 5 days for immediate family members
   • 3 days for extended family
   • Additional unpaid leave available upon request

To request any type of leave, please use the HR Support portal at https://hrsupport.usclarity.com/support/home. Submit your request at least 2 weeks in advance when possible.

Is there anything else I can help you with?
""".strip()


def print_timeline(events):
    """Print a timeline of events with elapsed time."""
    start_time = events[0][0]
    print("\n📊 Response Timeline:")
    print("-" * 50)
    for timestamp, event in events:
        elapsed = timestamp - start_time
        print(f"{elapsed:6.2f}s | {event}")
    print("-" * 50)
    total_time = events[-1][0] - start_time
    print(f"Total: {total_time:.2f}s\n")


async def simulate_response(query: str, response: str, show_ack: bool = False):
    """Simulate how the bot responds with the new optimizations."""
    print(f"\n💬 User: {query}")
    events = [(time.time(), "User sends message")]
    
    # Immediate typing indicator
    await asyncio.sleep(0.1)  # Network latency
    events.append((time.time(), "Bot shows typing indicator"))
    
    # Show acknowledgment for complex queries
    if show_ack:
        await asyncio.sleep(0.2)
        events.append((time.time(), "Bot: 'I'm looking into that for you...'"))
    
    # Simulate LLM processing time
    await asyncio.sleep(2.0)  # Typical Gemini response time
    events.append((time.time(), "LLM generates response"))
    
    # Determine if streaming is needed
    if len(response) > 200:
        # Extract first sentence
        first_sentence_end = response.find('.') + 1
        if first_sentence_end > 0 and first_sentence_end < 100:
            first_part = response[:first_sentence_end].strip()
            rest = response[first_sentence_end:].strip()
        else:
            first_part = response[:80]
            rest = response[80:]
        
        # Show first part immediately
        await asyncio.sleep(0.1)
        events.append((time.time(), f"Bot shows: '{first_part[:50]}...'"))
        
        # Stream the rest
        chunks = []
        words = rest.split()
        chunk_size = 15  # ~75-90 chars per chunk at 0.5s intervals
        
        for i in range(0, len(words), chunk_size):
            chunk = ' '.join(words[i:i+chunk_size])
            chunks.append(chunk)
        
        for i, chunk in enumerate(chunks):
            await asyncio.sleep(0.4)  # 0.5s throttle * 0.8
            events.append((time.time(), f"Streaming chunk {i+1}/{len(chunks)}"))
        
        events.append((time.time(), "Response complete"))
    else:
        # Short response - send directly
        await asyncio.sleep(0.1)
        events.append((time.time(), f"Bot shows complete response"))
    
    print_timeline(events)
    print(f"🤖 Bot: {response[:100]}{'...' if len(response) > 100 else ''}")


async def main():
    print("=" * 60)
    print("HR Chatbot Response Speed Test")
    print("Demonstrating optimizations for faster perceived responses")
    print("=" * 60)
    
    # Test 1: Short response (no streaming)
    print("\n📝 Test 1: Short Response (<200 chars)")
    await simulate_response(
        "What's my vacation balance?",
        SHORT_RESPONSE,
        show_ack=False
    )
    
    # Test 2: Medium response with streaming
    print("\n📝 Test 2: Medium Response (200-500 chars)")
    await simulate_response(
        "Can you explain how vacation days work here?",
        MEDIUM_RESPONSE,
        show_ack=True  # Complex query
    )
    
    # Test 3: Long response with streaming
    print("\n📝 Test 3: Long Response (>500 chars)")
    await simulate_response(
        "I need detailed information about all types of leave available",
        LONG_RESPONSE,
        show_ack=True  # Complex query
    )
    
    print("\n✅ Key Improvements:")
    print("• Immediate typing indicator (< 0.1s)")
    print("• 'Looking into it' message for complex queries")
    print("• Streaming starts at 200 chars (was 500)")
    print("• Faster streaming: 0.4s between chunks (was 1s)")
    print("• First sentence shown immediately while streaming rest")


def test_new_greeting_logic():
    """Test the new greeting logic scenarios."""
    test_cases = [
        # (input, should_show_card, processed_message)
        ("hi", True, None),  # Just greeting → show card, no further processing
        ("hi! i want to quit my work", True, "i want to quit my work"),  # Greeting + question → show card + process question
        ("hello, what are the leave policies?", True, "what are the leave policies?"),  # Greeting + question
        ("I want to quit", False, "I want to quit"),  # No greeting → no card, process as is
        ("good morning! help me with benefits", True, "help me with benefits"),  # Greeting + question
    ]
    
    print("Testing new greeting logic...\n")
    
    for i, (input_msg, should_show_card, expected_processed) in enumerate(test_cases, 1):
        greet_only, user_payload = split_greeting(input_msg)
        
        # Simulate the new logic
        has_greeting = greet_only or user_payload
        if has_greeting:
            if user_payload:
                processed_message = user_payload.strip()
            else:
                processed_message = None
        else:
            processed_message = input_msg
            
        print(f"Test {i}: '{input_msg}'")
        print(f"  Expected: show_card={should_show_card}, processed='{expected_processed}'")
        print(f"  Actual:   show_card={has_greeting}, processed='{processed_message}'")
        
        if has_greeting == should_show_card and processed_message == expected_processed:
            print(f"  ✅ PASS")
        else:
            print(f"  ❌ FAIL")
        print()


if __name__ == "__main__":
    asyncio.run(main())
    test_new_greeting_logic() 