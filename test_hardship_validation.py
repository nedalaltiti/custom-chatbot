#!/usr/bin/env python3
"""
Test script for hardship validation functionality.

This script demonstrates how to use the hardship validation service
to analyze financial hardship data using the Gemini model.
"""

import asyncio
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from uwbot.services.hardship_validation_service import HardshipValidationService, HardshipValidity
from uwbot.services.contact_service import ContactService
from uwbot.utils.result import Success, Error

async def test_hardship_validation():
    """Test the hardship validation functionality."""
    
    print("🧪 Testing Hardship Validation Service")
    print("=" * 50)
    
    # Initialize services
    hardship_service = HardshipValidationService()
    contact_service = ContactService()
    
    # Test data - simulate hardship information
    test_hardship_data = {
        "contact_id": 12345,
        "financial_hardship": "Yes",
        "hardship_description": "Lost job due to company downsizing. Currently unemployed and struggling to pay bills. Have been actively looking for work for 3 months.",
        "financial_hardship_details": "Monthly income reduced from $5000 to $1200 (unemployment benefits). Behind on mortgage payments by 2 months. Medical bills from recent surgery totaling $8000. No savings remaining."
    }
    
    print(f"📋 Test Data:")
    print(f"Contact ID: {test_hardship_data['contact_id']}")
    print(f"Financial Hardship: {test_hardship_data['financial_hardship']}")
    print(f"Description: {test_hardship_data['hardship_description']}")
    print(f"Details: {test_hardship_data['financial_hardship_details']}")
    print()
    
    try:
        # Test 1: Direct hardship analysis
        print("🔍 Test 1: Direct Hardship Analysis")
        print("-" * 30)
        
        result = await hardship_service.analyze_hardship_validity(test_hardship_data)
        
        if result.is_success():
            analysis = result.value
            print(f"✅ Analysis completed successfully!")
            print(f"Result: {analysis.result.value.upper()}")
            print(f"Confidence: {analysis.confidence:.1%}")
            print()
            print(f"Reason: {analysis.reason}")
            print()
        else:
            print(f"❌ Analysis failed: {result.error}")
        
        print()
        
        # Test 2: Formatted response
        print("📝 Test 2: Formatted Response")
        print("-" * 30)
        
        if result.is_success():
            formatted_response = hardship_service.format_hardship_response(result.value, test_hardship_data)
            print(formatted_response)
        else:
            print("Cannot format response - analysis failed")
        
        print()
        
        # Test 3: Contact service integration
        print("🔗 Test 3: Contact Service Integration")
        print("-" * 30)
        
        # Note: This would require a real database connection
        print("Note: This test requires a real database connection with hardship data.")
        print("To test with real data, use the API endpoints:")
        print("  POST /debug/contact")
        print("  or send a message in Teams with a contact ID")
        
        # Test 4: Different hardship scenarios
        print()
        print("🎭 Test 4: Different Hardship Scenarios")
        print("-" * 30)
        
        scenarios = [
            {
                "name": "Valid Hardship",
                "data": {
                    "contact_id": 1001,
                    "financial_hardship": "Yes",
                    "hardship_description": "Medical emergency requiring surgery. Unable to work for 6 weeks.",
                    "financial_hardship_details": "Medical bills: $15,000. Lost wages: $8,000. No health insurance coverage."
                }
            },
            {
                "name": "Suspicious Hardship",
                "data": {
                    "contact_id": 1002,
                    "financial_hardship": "Yes",
                    "hardship_description": "Need money for vacation",
                    "financial_hardship_details": "Want to go to Hawaii next month"
                }
            },
            {
                "name": "Insufficient Data",
                "data": {
                    "contact_id": 1003,
                    "financial_hardship": "Yes",
                    "hardship_description": "",
                    "financial_hardship_details": ""
                }
            }
        ]
        
        for scenario in scenarios:
            print(f"\n📊 Scenario: {scenario['name']}")
            print(f"Description: {scenario['data']['hardship_description']}")
            
            result = await hardship_service.analyze_hardship_validity(scenario['data'])
            
            if result.is_success():
                analysis = result.value
                print(f"Result: {analysis.result.value.upper()} (Confidence: {analysis.confidence:.1%})")
            else:
                print(f"Error: {result.error}")
        
        print()
        print("✅ All tests completed!")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

def print_usage_instructions():
    """Print usage instructions for the hardship validation system."""
    
    print("\n📖 Usage Instructions")
    print("=" * 50)
    print()
    print("1. API Endpoints:")
    print("   • POST /debug/contact")
    print("     Body: {\"contact_id\": 123, \"user_id\": \"test-user\"}")
    print()
    print("2. Teams Integration:")
    print("   • Send a message like: \"Contact 123\"")
    print("   • Or: \"Get hardship analysis for contact 456\"")
    print()
    print("3. Database Requirements:")
    print("   • contacts table with hardship-related fields")
    print("   • contacts_userfields table with custom_id values:")
    print("     - 322256: financial_hardship")
    print("     - 322271: hardship_description")
    print("     - 322256: financial_hardship_details")
    print()
    print("4. Configuration:")
    print("   • Ensure Gemini API is configured")
    print("   • Database connection is established")
    print("   • Proper environment variables are set")
    print()

if __name__ == "__main__":
    print("🚀 UWBot Hardship Validation Test")
    print("=" * 50)
    
    # Run the tests
    asyncio.run(test_hardship_validation())
    
    # Print usage instructions
    print_usage_instructions() 