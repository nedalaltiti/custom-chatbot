"""
Validation Guides for uwbot

This module contains prompt templates and validation guides for different types of analysis.
Separates prompt authoring from service orchestration for better maintainability.
"""

from typing import Dict, Any

def get_hardship_validation_prompt() -> str:
    """
    Get the hardship validation prompt template.
    
    Returns:
        Formatted prompt template string with placeholders for dynamic content.
    """
    return """You are a financial hardship validation expert. Analyze the following hardship claim and determine if it passes validation.

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
You MUST respond with ONLY valid JSON in this exact format:

{{
    "result": "pass",
    "confidence": 0.85,
    "reason": "Detailed explanation of why the hardship passes or fails validation"
}}

IMPORTANT: 
- Respond with ONLY the JSON object, no additional text
- Use "pass" or "no_pass" for the result field
- Use a number between 0.0 and 1.0 for confidence
- Provide a clear reason in the reason field

RESULT GUIDELINES:
- **pass**: The hardship description makes sense as a financial hardship (single words like "bankruptcy", "covid 19" are acceptable)
- **no_pass**: The description does not relate to financial hardship or is clearly inappropriate (e.g., "vacation", "luxury purchase")

ANALYSIS FOCUS:
- Focus on whether the hardship description indicates genuine financial difficulty
- Consider if the hardship is temporary or ongoing
- Evaluate if the hardship affects the person's ability to meet financial obligations
- Assess if the hardship is beyond the person's control
- Avoid mentioning the examples of valid and invalid hardships in the response

RESPONSE FORMAT:
Return ONLY a valid JSON object with the three required fields: result, confidence, and reason."""

def format_hardship_prompt(contact_id: str, financial_hardship: str, hardship_description: str) -> str:
    """
    Format the hardship validation prompt with contact-specific data.
    
    Args:
        contact_id: The contact ID for the analysis
        financial_hardship: The financial hardship status
        hardship_description: The hardship description
        
    Returns:
        Formatted prompt string ready for LLM processing
    """
    prompt_template = get_hardship_validation_prompt()
    return prompt_template.format(
        contact_id=contact_id,
        financial_hardship=financial_hardship,
        hardship_description=hardship_description
    ) 