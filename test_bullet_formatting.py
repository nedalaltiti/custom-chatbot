#!/usr/bin/env python3
"""
Test bullet point formatting to ensure proper spacing.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from hrbot.services.processor import ChatProcessor

def test_bullet_formatting():
    """Test the bullet point formatting with real examples."""
    
    processor = ChatProcessor()
    
    # Test case 1: The exact problem from user
    problematic_text = """Here's some information about resigning from your job.
• You must first inform your direct manager about your resignation.
• You will then have a meeting with HR for an exit interview and to complete the resignation letter. • If you are still within your probation period, your last working day will be the same day you submit your resignation; otherwise, you are required to serve a one-month notice period.
Is there anything else I can help you with?"""

    print("🔧 Testing bullet point formatting fix...\n")
    print("📝 Original problematic text:")
    print(repr(problematic_text))
    print("\n" + "="*60 + "\n")
    
    formatted = processor._format_bullet_points(problematic_text)
    
    print("✅ Formatted text:")
    print(repr(formatted))
    print("\n" + "="*60 + "\n")
    
    print("📋 Visual representation:")
    print(formatted)
    print("\n" + "="*60 + "\n")
    
    # Check if the fix worked
    lines = formatted.split('\n')
    bullet_lines = [i for i, line in enumerate(lines) if line.strip().startswith('•')]
    
    print(f"🔍 Found {len(bullet_lines)} bullet points at lines: {bullet_lines}")
    
    # Verify each bullet point is on its own line
    for i, line_num in enumerate(bullet_lines):
        line = lines[line_num].strip()
        print(f"  Bullet {i+1}: {line[:50]}{'...' if len(line) > 50 else ''}")
    
    # Check for proper spacing between bullet points
    proper_spacing = True
    for i in range(len(bullet_lines) - 1):
        current_line = bullet_lines[i]
        next_line = bullet_lines[i + 1]
        
        # There should be exactly one empty line between bullet points
        if next_line - current_line != 2:
            proper_spacing = False
            print(f"❌ Improper spacing between bullet {i+1} and {i+2}")
        else:
            print(f"✅ Proper spacing between bullet {i+1} and {i+2}")
    
    if proper_spacing:
        print("\n🎉 All bullet points are properly spaced!")
    else:
        print("\n⚠️ Some bullet points still have spacing issues.")
    
    return proper_spacing

def test_various_bullet_scenarios():
    """Test various bullet point scenarios."""
    
    processor = ChatProcessor()
    
    test_cases = [
        # Case 1: Concatenated bullets
        "First point. • Second point. • Third point.",
        
        # Case 2: Colon followed by bullet
        "Here are the steps:• First step• Second step",
        
        # Case 3: Mixed formatting
        "Introduction.\n• First bullet• Second bullet on same line\n• Third bullet properly spaced",
        
        # Case 4: Already properly formatted
        "Text.\n\n• First\n\n• Second\n\n• Third",
    ]
    
    print("\n" + "="*80)
    print("🧪 Testing various bullet point scenarios...\n")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test Case {i}:")
        print(f"Input:  {repr(test_case)}")
        
        formatted = processor._format_bullet_points(test_case)
        print(f"Output: {repr(formatted)}")
        print(f"Visual:\n{formatted}")
        print("-" * 40)

if __name__ == "__main__":
    success = test_bullet_formatting()
    test_various_bullet_scenarios()
    
    if success:
        print("\n🎉 Bullet point formatting test PASSED!")
    else:
        print("\n❌ Bullet point formatting test FAILED!") 