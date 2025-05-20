#!/usr/bin/env python
"""
Test script for the Gemini service
"""

import asyncio
import sys
import os
import logging
from pathlib import Path

# Add the src directory to the path so we can import our modules
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
sys.path.append(str(src_dir))

from hrbot.services.gemini_service import GeminiService
from hrbot.services.processor import ChatProcessor

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("gemini_test")

async def test_gemini_service():
    """Test basic functionality of the Gemini service"""
    try:
        # Initialize the service
        service = GeminiService()
        logger.info("Gemini service initialized successfully")
        
        # Test connection
        logger.info("Testing connection...")
        is_connected = await service.test_connection()
        logger.info(f"Connection test: {'SUCCESS' if is_connected else 'FAILED'}")
        
        if not is_connected:
            logger.error("Connection test failed, check credentials")
            return
        
        # Test a simple query
        test_query = "What is the capital of France?"
        logger.info(f"Testing query: '{test_query}'")
        
        result = await service.analyze_messages([test_query])
        if result.is_success():
            response = result.unwrap()
            logger.info(f"Response: {response['response']}")
        else:
            logger.error(f"Query failed: {result.error}")
            
        # Test the processor
        logger.info("Testing ChatProcessor...")
        processor = ChatProcessor(service)
        processor_result = await processor.process_message(
            "Tell me about the benefits of exercise",
            chat_history=["I want to learn about healthy habits"]
        )
        
        if processor_result.is_success():
            processor_response = processor_result.unwrap()
            logger.info(f"Processor response: {processor_response['response'][:100]}...")
        else:
            logger.error(f"Processor query failed: {processor_result.error}")
        
        logger.info("Tests completed")
        
    except Exception as e:
        logger.error(f"Error during test: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Run the test
    asyncio.run(test_gemini_service()) 