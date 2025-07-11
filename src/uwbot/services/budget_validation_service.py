"""
Budget Validation Service for uwbot

Uses database queries to analyze budget data and determine if a client has a positive surplus.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from uwbot.utils.result import Result, Success, Error

logger = logging.getLogger(__name__)


class BudgetValidity(Enum):
    """Enum for budget validation results."""
    PASS = "pass"
    NO_PASS = "no_pass"


@dataclass
class BudgetAnalysis:
    """Result of budget validation analysis."""
    result: BudgetValidity  # "pass" or "no_pass"
    confidence: float  # 0.0 to 1.0
    reason: str
    total_net_income: float
    total_expenses: float
    surplus: float


class BudgetValidationService:
    """Service for validating budget data and determining positive surplus."""
    
    def __init__(self):
        """Initialize the budget validation service."""
        logger.info("BudgetValidationService initialized")
    
    async def analyze_budget_validity(
        self, 
        budget_data: Dict[str, Any]
    ) -> Result[BudgetAnalysis]:
        """
        Analyze budget data and determine if it shows a positive surplus.
        
        Args:
            budget_data: Dictionary containing budget information
            
        Returns:
            Result containing BudgetAnalysis
        """
        try:
            # Extract budget values
            total_net_income = budget_data.get('total_net_income', 0.0)
            total_expenses = budget_data.get('total_expenses', 0.0)
            
            # Calculate surplus
            surplus = total_net_income - total_expenses
            
            # Determine if it's a positive surplus
            if surplus > 0:
                result = BudgetValidity.PASS
                confidence = 1.0
                reason = f"Positive surplus of ${surplus:,.2f} (Income: ${total_net_income:,.2f}, Expenses: ${total_expenses:,.2f})"
            else:
                result = BudgetValidity.NO_PASS
                confidence = 1.0
                reason = f"Negative surplus of ${surplus:,.2f} (Income: ${total_net_income:,.2f}, Expenses: ${total_expenses:,.2f})"
            
            analysis = BudgetAnalysis(
                result=result,
                confidence=confidence,
                reason=reason,
                total_net_income=total_net_income,
                total_expenses=total_expenses,
                surplus=surplus
            )
            
            logger.info(f"Budget analysis completed for contact {budget_data.get('contact_id')}: {analysis.result.value}")
            return Success(analysis)
            
        except Exception as e:
            logger.error(f"Error analyzing budget validity: {e}")
            return Error(f"Analysis failed: {str(e)}")
    
    def format_budget_response(self, analysis: BudgetAnalysis, budget_data: Dict[str, Any]) -> str:
        """Format the budget analysis into a user-friendly response."""
        
        contact_id = budget_data.get('contact_id', 'Unknown')
        
        # Format currency values
        income_formatted = f"${analysis.total_net_income:,.2f}"
        expenses_formatted = f"${analysis.total_expenses:,.2f}"
        surplus_formatted = f"${analysis.surplus:,.2f}"
        
        # Build organized response
        response_parts = []
        
        # Header with status icon
        if analysis.result == BudgetValidity.PASS:
            response_parts.append(f"✅ Contact {contact_id} has a **positive budget surplus**\n")
        else:
            response_parts.append(f"❌ Contact {contact_id} has a **negative budget surplus**\n")
        
        # Budget information section
        response_parts.append("")
        response_parts.append("**Budget Analysis:**\n")
        response_parts.append(f"• Total Net Income: **{income_formatted}**\n")
        response_parts.append(f"• Total Expenses: **{expenses_formatted}**\n")
        response_parts.append(f"• Surplus/Deficit: **{surplus_formatted}**\n")
        
        # Analysis results section
        response_parts.append("")
        response_parts.append("**Validation Result:**\n")
        response_parts.append(f"• Status: **{analysis.result.value.upper()}**\n")
        response_parts.append(f"• Confidence: **{analysis.confidence * 100:.1f}%**\n")
        response_parts.append(f"• Reason: {analysis.reason}\n")
        
        # Summary statement
        if analysis.result == BudgetValidity.PASS:
            response_parts.append("")
            response_parts.append("✅ **PASS** - This client shows a positive surplus and can be shown to agents.\n")
        else:
            response_parts.append("")
            response_parts.append("❌ **NO PASS** - This client shows a negative surplus and should not be shown to agents.\n")
        
        return "\n".join(response_parts) 