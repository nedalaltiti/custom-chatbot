"""
Hardship Validation Service for uwbot

Uses Gemini model to analyze financial hardship data and determine validity.
"""

import logging
import asyncio
import httpx
import backoff
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

from uwbot.services.gemini_service import GeminiService
from uwbot.utils.result import Result, Success, Error
from uwbot.config.settings import settings
from uwbot.config.validation_guides import format_hardship_prompt

logger = logging.getLogger(__name__)


class HardshipValidity(Enum):
    """Enum for hardship validation results."""
    PASS = "pass"
    NO_PASS = "no_pass"


@dataclass
class HardshipAnalysis:
    """Result of hardship validation analysis."""
    result: HardshipValidity  # "pass" or "no_pass"
    confidence: float  # 0.0 to 1.0
    reason: str


class HardshipValidationService:
    """Service for validating financial hardship claims using AI analysis."""
    
    def __init__(self, llm_service: Optional[GeminiService] = None):
        """Initialize the hardship validation service."""
        self.llm_service = llm_service or GeminiService()
        
        # Get field IDs from settings
        self.financial_hardship_id = settings.hardship_fields.financial_hardship_id
        self.hardship_description_id = settings.hardship_fields.hardship_description_id
        
        logger.info(f"HardshipValidationService initialized with field IDs: financial={self.financial_hardship_id}, description={self.hardship_description_id}")
    
    @backoff.on_exception(backoff.expo, (httpx.HTTPError, RuntimeError), max_tries=4)
    async def _call_gemini(self, prompt: str):
        """Call Gemini with proper timeout and retry logic."""
        return await asyncio.wait_for(
            self.llm_service.analyze_messages([prompt], response_format="json"),
            timeout=15
        )
    
    async def analyze_hardship_validity(
        self, 
        hardship_data: Dict[str, Any]
    ) -> Result[HardshipAnalysis]:
        """
        Analyze hardship data and determine if it's valid.
        
        Args:
            hardship_data: Dictionary containing hardship information
            
        Returns:
            Result containing HardshipAnalysis
        """
        try:
            # Short-circuit if no hardship data is present
            financial_hardship = hardship_data.get('financial_hardship', '')
            hardship_description = hardship_data.get('hardship_description', '')
            if not financial_hardship and not hardship_description:
                return Success(HardshipAnalysis(
                    result=HardshipValidity.NO_PASS,
                    confidence=0.0,
                    reason="No hardship data available for analysis"
                ))

            # Build the analysis prompt using validation guides
            contact_id = hardship_data.get('contact_id', 'Unknown')
            prompt = format_hardship_prompt(
                contact_id=contact_id,
                financial_hardship=financial_hardship,
                hardship_description=hardship_description
            )
            
            # Get AI analysis with proper rate limiting and timeout
            result = await self._call_gemini(prompt)
            
            if result.is_error():
                logger.error(f"LLM analysis failed: {result.error}")
                return Error(result.error)
            
            # Parse the AI response
            analysis = self._parse_hardship_analysis(result.value, hardship_data)
            
            logger.info(f"Hardship analysis completed for contact {hardship_data.get('contact_id')}: {analysis.result.value}")
            return Success(analysis)
            
        except asyncio.TimeoutError:
            logger.error("LLM analysis timed out after 15 seconds")
            return Error("Analysis timed out - please try again")
        except Exception as e:
            logger.error(f"Error analyzing hardship validity: {e}")
            return Error(f"Analysis failed: {str(e)}")
    
    def _parse_hardship_analysis(self, llm_response: Dict[str, Any], hardship_data: Dict[str, Any]) -> HardshipAnalysis:
        """Parse the LLM response into a structured HardshipAnalysis object."""
        import json
        import re
        
        response_text = llm_response.get("response", "No response available")
        
        # Try to extract JSON from the response
        try:
            # First, try to parse the entire response as JSON
            parsed_data = json.loads(response_text)
        except json.JSONDecodeError:
            # If that fails, try to extract JSON from within the response
            try:
                # Look for JSON object in the response
                json_match = re.search(r'\{[^{}]*"result"[^{}]*\}', response_text)
                if json_match:
                    json_str = json_match.group(0)
                    parsed_data = json.loads(json_str)
                else:
                    # Try to find any JSON-like structure
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        parsed_data = json.loads(json_str)
                    else:
                        raise ValueError("No JSON found in response")
            except (json.JSONDecodeError, ValueError):
                logger.warning(f"Could not parse JSON from response: {response_text[:200]}...")
                return self._create_default_analysis(
                    f"Unable to parse AI response: {response_text[:120]}…" 
                )

        # Map the parsed data to our analysis object
        result_str = parsed_data.get('result', 'no_pass').lower()
        result_map = {
            'pass': HardshipValidity.PASS,
            'no_pass': HardshipValidity.NO_PASS
        }
        result = result_map.get(result_str, HardshipValidity.NO_PASS)
        
        # Handle confidence with better error handling
        try:
            confidence = float(parsed_data.get("confidence", 0.0))
            # Ensure confidence is between 0 and 1
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.0
        
        reason = parsed_data.get('reason', 'No reason provided')
        
        logger.info(f"Successfully parsed hardship analysis: result={result.value}, confidence={confidence}")
        
        return HardshipAnalysis(
            result=result,
            confidence=confidence,
            reason=reason
        )
    
    def _create_default_analysis(self, reason: str = "Unable to analyze hardship data due to processing error") -> HardshipAnalysis:
        """Create a default analysis when parsing completely fails."""
        return HardshipAnalysis(
            result=HardshipValidity.NO_PASS,
            confidence=0.0,
            reason=reason
        )
    
    def format_hardship_response(self, analysis: HardshipAnalysis, hardship_data: Dict[str, Any]) -> str:
        """Format the hardship analysis into a user-friendly response."""
        from uwbot.utils.validation_responses import format_hardship_response
        return format_hardship_response(analysis, hardship_data) 