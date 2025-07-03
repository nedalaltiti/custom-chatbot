"""
Hardship Validation Service for uwbot

Uses Gemini model to analyze financial hardship data and determine validity.
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

from uwbot.services.gemini_service import GeminiService
from uwbot.utils.result import Result, Success, Error

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
    
    # Custom field IDs for hardship-related data
    FINANCIAL_HARDSHIP_ID = 322256
    HARDSHIP_DESCRIPTION_ID = 322271
    FINANCIAL_HARDSHIP_DETAILS_ID = 322256  # Same as financial_hardship_id based on your query
    
    def __init__(self, llm_service: Optional[GeminiService] = None):
        """Initialize the hardship validation service."""
        self.llm_service = llm_service or GeminiService()
        logger.info("HardshipValidationService initialized")
    
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
            # Build the analysis prompt
            prompt = self._build_hardship_analysis_prompt(hardship_data)
            
            # Get AI analysis
            result = await self.llm_service.analyze_messages([prompt])
            
            if result.is_error():
                logger.error(f"LLM analysis failed: {result.error}")
                return Error(result.error)
            
            # Parse the AI response
            analysis = self._parse_hardship_analysis(result.value, hardship_data)
            
            logger.info(f"Hardship analysis completed for contact {hardship_data.get('contact_id')}: {analysis.result.value}")
            return Success(analysis)
            
        except Exception as e:
            logger.error(f"Error analyzing hardship validity: {e}")
            return Error(f"Analysis failed: {str(e)}")
    
    def _build_hardship_analysis_prompt(self, hardship_data: Dict[str, Any]) -> str:
        """Build a comprehensive prompt for hardship analysis."""
        
        # Extract relevant data
        contact_id = hardship_data.get('contact_id', 'Unknown')
        financial_hardship = hardship_data.get('financial_hardship', '')
        hardship_description = hardship_data.get('hardship_description', '')
        hardship_details = hardship_data.get('financial_hardship_details', '')
        
        prompt = f"""
You are a financial hardship validation expert. Analyze the following hardship claim and determine if it passes validation.

CONTACT ID: {contact_id}

HARDSHIP DATA:
- Financial Hardship Status: {financial_hardship}
- Hardship Description: {hardship_description}
- Financial Hardship Details: {hardship_details}

VALIDATION CRITERIA:
1. **Documentation Completeness**: The hardship claim should have sufficient supporting documentation
2. **Financial Impact**: There should be evidence of significant financial impact
3. **Temporary Nature**: Hardships should typically be temporary, not permanent
4. **Reasonableness**: The hardship should be reasonable and verifiable
5. **Compliance**: The hardship should comply with relevant regulations and policies

ANALYSIS REQUIREMENTS:
Please analyze the hardship claim and provide a structured response in the following JSON format:

{{
    "result": "pass|no_pass",
    "confidence": 0.85,
    "reason": "Detailed explanation of why the hardship passes or fails validation"
}}

RESULT GUIDELINES:
- **pass**: Clear evidence of legitimate hardship with proper documentation and reasonable circumstances
- **no_pass**: Insufficient documentation, fraudulent claim, non-compliant, or clearly unreasonable hardship

CONFIDENCE SCALE:
- 0.9-1.0: Very high confidence in the decision
- 0.7-0.89: High confidence with minor uncertainties
- 0.5-0.69: Moderate confidence, some uncertainty
- 0.3-0.49: Low confidence, significant uncertainty
- 0.0-0.29: Very low confidence, highly uncertain

Please provide your analysis in the exact JSON format specified above.
"""
        
        return prompt
    
    def _parse_hardship_analysis(self, llm_response: Dict[str, Any], hardship_data: Dict[str, Any]) -> HardshipAnalysis:
        """Parse the LLM response into a structured HardshipAnalysis object."""
        
        try:
            # Extract the response text
            response_text = llm_response.get('response', '')
            
            # Try to extract JSON from the response
            import json
            import re
            
            # Look for JSON in the response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                parsed_data = json.loads(json_str)
            else:
                # Fallback: create a basic analysis
                logger.warning("Could not parse JSON from LLM response, using fallback analysis")
                parsed_data = self._create_fallback_analysis(response_text)
            
            # Map the parsed data to our analysis object
            result_str = parsed_data.get('result', 'no_pass').lower()
            result_map = {
                'pass': HardshipValidity.PASS,
                'no_pass': HardshipValidity.NO_PASS
            }
            
            result = result_map.get(result_str, HardshipValidity.NO_PASS)
            confidence = float(parsed_data.get('confidence', 0.5))
            reason = parsed_data.get('reason', 'No reason provided')
            
            return HardshipAnalysis(
                result=result,
                confidence=confidence,
                reason=reason
            )
            
        except Exception as e:
            logger.error(f"Error parsing hardship analysis: {e}")
            return self._create_default_analysis()
    
    def _create_fallback_analysis(self, response_text: str) -> Dict[str, Any]:
        """Create a fallback analysis when JSON parsing fails."""
        # Simple keyword-based analysis
        text_lower = response_text.lower()
        
        if any(word in text_lower for word in ['pass', 'valid', 'legitimate', 'approved', 'acceptable']):
            result = 'pass'
            confidence = 0.6
        else:
            result = 'no_pass'
            confidence = 0.6
        
        return {
            'result': result,
            'confidence': confidence,
            'reason': f'Fallback analysis based on response: {response_text[:200]}...'
        }
    
    def _create_default_analysis(self) -> HardshipAnalysis:
        """Create a default analysis when parsing completely fails."""
        return HardshipAnalysis(
            result=HardshipValidity.NO_PASS,
            confidence=0.0,
            reason="Unable to analyze hardship data due to processing error"
        )
    
    def format_hardship_response(self, analysis: HardshipAnalysis, hardship_data: Dict[str, Any]) -> str:
        """Format the hardship analysis into a user-friendly response."""
        
        contact_id = hardship_data.get('contact_id', 'Unknown')
        
        response_parts = [
            f"**Financial Hardship Analysis for Contact {contact_id}**",
            "",
            f"**Result:** {analysis.result.value.upper()}",
            f"**Confidence:** {analysis.confidence:.1%}",
            "",
            f"**Reason:** {analysis.reason}",
            ""
        ]
        
        return "\n".join(response_parts) 