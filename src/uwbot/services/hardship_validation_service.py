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
        
        prompt = f"""
You are a financial hardship validation expert. Analyze the following hardship claim and determine if it passes validation.

CONTACT ID: {contact_id}

HARDSHIP DATA:
- Financial Hardship Status: {financial_hardship}
- Hardship Description: {hardship_description}

VALIDATION CRITERIA:
1. **Financial Hardship Relevance**: The description should clearly indicate a financial hardship situation
2. **Acceptable Formats**: Single words (e.g., "bankruptcy", "covid 19") or short descriptions are acceptable
3. **Common Hardship Types**: Job loss, medical expenses, natural disasters, economic downturns, etc.
4. **Reasonableness**: The hardship should be reasonable and verifiable
5. **Compliance**: The hardship should comply with relevant regulations and policies

EXAMPLES OF VALID HARDSHIPS:
- "bankruptcy", "job loss", "medical bills", "covid 19", "natural disaster"
- "home repair", "car accident", "divorce", "death in family"
- "reduced hours", "layoff", "medical emergency", "disability"

EXAMPLES OF INVALID HARDSHIPS:
- "vacation", "luxury purchase", "entertainment", "hobby expenses"
- "want new car", "planning trip", "shopping", "dining out"

ANALYSIS REQUIREMENTS:
Please analyze the hardship claim and provide a structured response in the following JSON format:

{{
    "result": "pass|no_pass",
    "confidence": 0.85,
    "reason": "Detailed explanation of why the hardship passes or fails validation"
}}

RESULT GUIDELINES:
- **pass**: The hardship description makes sense as a financial hardship (single words like "bankruptcy", "covid 19" are acceptable)
- **no_pass**: The description does not relate to financial hardship or is clearly inappropriate (e.g., "vacation", "luxury purchase")

CONFIDENCE SCALE:
- 0.9-1.0: Very high confidence - clear financial hardship (e.g., "bankruptcy", "job loss")
- 0.7-0.89: High confidence - reasonable hardship with minor uncertainties
- 0.5-0.69: Moderate confidence - some uncertainty about hardship relevance
- 0.3-0.49: Low confidence - unclear if it's a financial hardship
- 0.0-0.29: Very low confidence - likely not a financial hardship

ANALYSIS FOCUS:
- Focus on whether the hardship description indicates genuine financial difficulty
- Consider if the hardship is temporary or ongoing
- Evaluate if the hardship affects the person's ability to meet financial obligations
- Assess if the hardship is beyond the person's control

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
        financial_hardship = hardship_data.get('financial_hardship', '')
        hardship_description = hardship_data.get('hardship_description', '')
        
        # Format confidence as percentage with one decimal place
        confidence_percent = f"{analysis.confidence * 100:.1f}%"
        
        # Build organized response
        response_parts = []
        
        # Header with status icon
        if analysis.result == HardshipValidity.PASS:
            response_parts.append(f"✅ Contact {contact_id} has hardship validation data \n")
        else:
            response_parts.append(f"❌ Contact {contact_id} hardship validation failed \n")
        
        # Hardship information section
        hardship_info = []
        if hardship_description:
            hardship_info.append(f"\n • Hardship Description: {hardship_description}")
        if financial_hardship:
            hardship_info.append(f"\n • Financial Hardship Status: {financial_hardship}")
        
        if hardship_info:
            response_parts.append("**Hardship Information:** \n")
            response_parts.extend(hardship_info)
        
        # Analysis results section
        response_parts.append("")
        response_parts.append("**Validation Analysis:** \n")
        response_parts.append(f"• Result: **{analysis.result.value.upper()}** \n")
        response_parts.append(f"• Confidence: **{confidence_percent}** \n")
        response_parts.append(f"• Reason: {analysis.reason} \n")
        
        # Summary statement
        if analysis.result == HardshipValidity.PASS:
            response_parts.append("")
        else:
            response_parts.append("")
        
        return "\n".join(response_parts) 