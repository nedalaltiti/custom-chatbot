"""
Validation Response Formats for uwbot

This module centralizes all response formatting for validation services:
- Hardship validation responses
- Budget validation responses  
- Contact validation responses
- Combined validation responses
- Error responses

Provides consistent formatting across all validation endpoints.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class ValidationResult(Enum):
    """Enum for validation result types."""
    PASS = "pass"
    NO_PASS = "no_pass"
    MIXED = "mixed"
    NO_DATA = "no_data"
    ERROR = "error"


@dataclass
class ValidationResponse:
    """Structured validation response data."""
    contact_id: int
    result: ValidationResult
    message: str
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ValidationResponseFormatter:
    """Centralized formatter for all validation responses."""
    
    @staticmethod
    def format_hardship_response(analysis: Any, hardship_data: Dict[str, Any]) -> str:
        """Format hardship analysis into a user-friendly response."""
        contact_id = hardship_data.get('contact_id', 'Unknown')
        financial_hardship = hardship_data.get('financial_hardship', '')
        hardship_description = hardship_data.get('hardship_description', '')
        
        # Format confidence as percentage with one decimal place
        confidence_percent = f"{analysis.confidence * 100:.1f}%"
        
        # Build organized response
        response_parts = []
        
        # Header with status icon
        if analysis.result.value == "pass":
            response_parts.append(f"Contact {contact_id} has hardship validation data\n")
        else:
            response_parts.append(f"Contact {contact_id} hardship validation failed\n")
        
        # Hardship information section
        hardship_info = []
        if hardship_description:
            hardship_info.append(f"• Hardship Description: {hardship_description}")
        if financial_hardship:
            hardship_info.append(f"• Financial Hardship Status: {financial_hardship}")
        
        if hardship_info:
            response_parts.append("**Hardship Information:**\n")
            response_parts.extend(hardship_info)
            response_parts.append("")
        
        # Analysis results section
        response_parts.append("**Validation Analysis:**\n")
        response_parts.append(f"• Result: **{analysis.result.value.upper()}**\n")
        response_parts.append(f"• Confidence: **{confidence_percent}**\n")
        response_parts.append(f"• Reason: {analysis.reason}\n")
        
        return "\n".join(response_parts)
    
    @staticmethod
    def format_budget_response(analysis: Any, budget_data: Any) -> str:
        """Format budget analysis into a user-friendly response."""
        contact_id = budget_data.contact_id
        
        # Format currency values
        income_formatted = f"${analysis.total_net_income:,.2f}"
        expenses_formatted = f"${analysis.total_expenses:,.2f}"
        surplus_formatted = f"${analysis.surplus:,.2f}"
        
        # Build organized response
        response_parts = []
        
        # Header with status icon
        if analysis.result.value == "pass":
            response_parts.append(f"Contact {contact_id} has a **positive budget surplus**\n")
        else:
            response_parts.append(f"Contact {contact_id} has a **negative budget surplus**\n")
        
        # Budget information section
        response_parts.append("**Budget Analysis:**\n")
        response_parts.append(f"• Total Net Income: **{income_formatted}**\n")
        response_parts.append(f"• Total Expenses: **{expenses_formatted}**\n")
        response_parts.append(f"• Surplus/Deficit: **{surplus_formatted}**\n")
        
        # Analysis results section
        response_parts.append("**Validation Result:**\n")
        response_parts.append(f"• Status: **{analysis.result.value.upper()}**\n")
        response_parts.append(f"• Reason: {analysis.reason}\n")
        
        return "\n".join(response_parts)
    
    @staticmethod
    def format_contact_response(contact: Dict[str, Any]) -> str:
        """Format contact analysis results into a user-friendly response."""
        if not contact:
            return "No hardship data found for that contact ID."
        
        # If there's a formatted response already provided, use it
        if contact.get('formatted_response'):
            return contact['formatted_response']
        
        # If there's an error, return the error message
        if contact.get('error'):
            return f"Error analyzing hardship data: {contact['error']}"
        
        contact_id = contact.get('contact_id', 'Unknown')
        
        # Check if there's hardship data available
        hardship_data = contact.get('hardship_data', {})
        financial_hardship = hardship_data.get('financial_hardship', '')
        hardship_description = hardship_data.get('hardship_description', '')
        
        has_hardship_data = any([financial_hardship, hardship_description])
        
        if not has_hardship_data:
            return f"Contact {contact_id} does not have hardship validation data.\nNo hardship information has been recorded for this contact."
        
        # If there's analysis data, format it with organized structure
        analysis = contact.get('analysis')
        if analysis:
            result = analysis.get('result', 'unknown')
            confidence = analysis.get('confidence', 0.0)
            reason = analysis.get('reason', 'No reason provided')
            
            # Format confidence as percentage with one decimal place
            confidence_percent = f"{confidence * 100:.1f}%"
            
            # Build organized response
            response_parts = []
            
            # Header with status icon
            if result == 'pass':
                response_parts.append(f"Contact {contact_id} has hardship validation data")
            else:
                response_parts.append(f"Contact {contact_id} hardship validation failed")
            
            # Hardship information section
            hardship_info = []
            if hardship_description:
                hardship_info.append(f"• Hardship Description: {hardship_description}")
            if financial_hardship:
                hardship_info.append(f"• Financial Hardship Status: {financial_hardship}")
            
            if hardship_info:
                response_parts.append("Hardship Information:")
                response_parts.extend(hardship_info)
            
            # Analysis results section
            response_parts.append("")
            response_parts.append("Validation Analysis:")
            response_parts.append(f"• Result: {result.upper()}")
            response_parts.append(f"• Confidence: {confidence_percent}")
            response_parts.append(f"• Reason: {reason}")
            
            # Summary statement
            if result == 'pass':
                response_parts.append("")
                response_parts.append("The hardship validation data is available for this contact.")
            else:
                response_parts.append("")
                response_parts.append("The hardship validation data requires review or additional information.")
            
            return "\n".join(response_parts)
        
        return "Unable to format hardship analysis results. Please try again."
    
    @staticmethod
    def format_budget_analysis_response(budget: Dict[str, Any]) -> str:
        """Format budget analysis results into a user-friendly response."""
        if not budget:
            return "No budget data found for that contact ID."
        
        # If there's a formatted response already provided, use it
        if budget.get('formatted_response'):
            return budget['formatted_response']
        
        # If there's an error, return the error message
        if budget.get('error'):
            return f"Error analyzing budget data: {budget['error']}"
        
        contact_id = budget.get('contact_id', 'Unknown')
        
        # Check if there's budget data available
        budget_data = budget.get('budget_data', {})
        total_net_income = budget_data.get('total_net_income', 0)
        total_expenses = budget_data.get('total_expenses', 0)
        
        has_budget_data = any([total_net_income > 0, total_expenses > 0])
        
        if not has_budget_data:
            return f"Contact {contact_id} does not have budget validation data.\nNo budget information has been recorded for this contact."
        
        # If there's analysis data, format it with organized structure
        analysis = budget.get('analysis')
        if analysis:
            result = analysis.get('result', 'unknown')
            reason = analysis.get('reason', 'No reason provided')
            surplus = analysis.get('surplus', 0)
            
            # Format currency values
            income_formatted = f"${total_net_income:,.2f}"
            expenses_formatted = f"${total_expenses:,.2f}"
            surplus_formatted = f"${surplus:,.2f}"
            
            # Build organized response
            response_parts = []
            
            # Header with status icon
            if result == 'pass':
                response_parts.append(f"Contact {contact_id} has a **positive budget surplus**")
            else:
                response_parts.append(f"Contact {contact_id} has a **negative budget surplus**")
            
            # Budget information section
            response_parts.append("")
            response_parts.append("**Budget Analysis:**")
            response_parts.append(f"• Total Net Income: **{income_formatted}**")
            response_parts.append(f"• Total Expenses: **{expenses_formatted}**")
            response_parts.append(f"• Surplus/Deficit: **{surplus_formatted}**")
            
            # Analysis results section
            response_parts.append("")
            response_parts.append("**Validation Result:**")
            response_parts.append(f"• Status: **{result.upper()}**")
            response_parts.append(f"• Reason: {reason}")
            
            # Summary statement
            if result == 'pass':
                response_parts.append("")
                response_parts.append("**PASS** - This client shows a positive surplus and can be shown to agents.")
            else:
                response_parts.append("")
                response_parts.append("**NO PASS** - This client shows a negative surplus and should not be shown to agents.")
            
            return "\n".join(response_parts)
        
        return "Unable to format budget analysis results. Please try again."
    
    @staticmethod
    def format_combined_validation_response(
        contact_id: int,
        hardship_data: Dict[str, Any],
        budget_data: Dict[str, Any],
        hardship_analysis: Any,
        budget_analysis: Any,
        combined_result: str
    ) -> str:
        """Format combined hardship and budget analysis into a comprehensive response."""
        response_parts = []
        
        # Header
        response_parts.append(f"# **Validation Analysis for Contact {contact_id}**\n")
        
        # Overall result
        if combined_result == "pass":
            response_parts.append("## **OVERALL RESULT: PASS**\n")
        elif combined_result == "no_pass":
            response_parts.append("## **OVERALL RESULT: NO PASS**\n")
        elif combined_result == "mixed":
            response_parts.append("## **OVERALL RESULT: MIXED** (Requires Manual Review)\n")
        else:
            response_parts.append("## **OVERALL RESULT: NO DATA**\n")
        
        # Hardship Analysis Section
        response_parts.append("### **Hardship Validation**\n")
        if hardship_analysis:
            hardship_status = "**PASS**" if hardship_analysis.result.value == "pass" else "**NO PASS**"
            response_parts.append(f"**Status:** {hardship_status}\n")
            response_parts.append(f"**Confidence:** {hardship_analysis.confidence * 100:.1f}%\n")
            response_parts.append(f"**Reason:** {hardship_analysis.reason}\n")
        else:
            response_parts.append("**Status:** No hardship data available\n")
        
        # Budget Analysis Section
        response_parts.append("### **Budget Validation**\n")
        if budget_analysis:
            budget_status = "**PASS**" if budget_analysis.result.value == "pass" else "**NO PASS**"
            response_parts.append(f"**Status:** {budget_status}\n")
            response_parts.append(f"**Reason:** {budget_analysis.reason}\n")
        else:
            response_parts.append("**Status:** No budget data available\n")
        
        return "\n".join(response_parts)
    
    @staticmethod
    def format_no_data_response(contact_id: int, validation_type: str = "validation") -> str:
        """Format response when no data is available."""
        return f"Contact {contact_id} does not have {validation_type} data.\nNo {validation_type} information has been recorded for this contact."
    
    @staticmethod
    def format_error_response(contact_id: int, error_message: str, validation_type: str = "validation") -> str:
        """Format error response."""
        return f"Contact {contact_id} {validation_type} error.\n{error_message}"
    
    @staticmethod
    def format_invalid_contact_id_response(contact_id: int) -> str:
        """Format response for invalid contact ID."""
        return f"Invalid contact ID: {contact_id}. Please provide a valid contact ID between 1 and 999,999,999."
    
    @staticmethod
    def format_help_message() -> str:
        """Format help message for users."""
        return (
            "I'm here to help you validate both hardship and budget data.\n"
            "Please provide a contact ID to check both hardship and budget validation.\n\n"
        )
    
    @staticmethod
    def format_goodbye_message() -> str:
        """Format goodbye message."""
        return "You're welcome! I'm glad I could help you with your validation check. Feel free to reach out anytime you need to validate hardship data for other contacts. Have a great day! 👋"
    
    @staticmethod
    def format_debug_help_message() -> str:
        """Format help message for debug endpoint."""
        return (
            "I'm here to help you check hardship validation data. "
            "Please provide a contact ID to check if hardship data exists.\n\n"
        )


# Convenience functions for easy access
def format_hardship_response(analysis: Any, hardship_data: Dict[str, Any]) -> str:
    """Format hardship analysis response."""
    return ValidationResponseFormatter.format_hardship_response(analysis, hardship_data)


def format_budget_response(analysis: Any, budget_data: Any) -> str:
    """Format budget analysis response."""
    return ValidationResponseFormatter.format_budget_response(analysis, budget_data)


def format_contact_response(contact: Dict[str, Any]) -> str:
    """Format contact analysis response."""
    return ValidationResponseFormatter.format_contact_response(contact)


def format_combined_validation_response(
    contact_id: int,
    hardship_data: Dict[str, Any],
    budget_data: Dict[str, Any],
    hardship_analysis: Any,
    budget_analysis: Any,
    combined_result: str
) -> str:
    """Format combined validation response."""
    return ValidationResponseFormatter.format_combined_validation_response(
        contact_id, hardship_data, budget_data, hardship_analysis, budget_analysis, combined_result
    )


def format_no_data_response(contact_id: int, validation_type: str = "validation") -> str:
    """Format no data response."""
    return ValidationResponseFormatter.format_no_data_response(contact_id, validation_type)


def format_error_response(contact_id: int, error_message: str, validation_type: str = "validation") -> str:
    """Format error response."""
    return ValidationResponseFormatter.format_error_response(contact_id, error_message, validation_type)


def format_invalid_contact_id_response(contact_id: int) -> str:
    """Format invalid contact ID response."""
    return ValidationResponseFormatter.format_invalid_contact_id_response(contact_id)


def format_help_message() -> str:
    """Format help message."""
    return ValidationResponseFormatter.format_help_message()


def format_goodbye_message() -> str:
    """Format goodbye message."""
    return ValidationResponseFormatter.format_goodbye_message()


def format_debug_help_message() -> str:
    """Format debug help message."""
    return ValidationResponseFormatter.format_debug_help_message() 