"""
Budget Validation Service for uwbot

Uses database queries to analyze budget data and determine if a client has a positive surplus.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
from pydantic import BaseModel, Field

from uwbot.utils.result import Result, Success, Error

logger = logging.getLogger(__name__)


class BudgetDataIn(BaseModel):
    """Input model for budget validation data."""
    contact_id: int
    total_net_income: float = Field(ge=0)
    total_expenses: float = Field(ge=0)


class BudgetValidity(Enum):
    """Enum for budget validation results."""
    PASS = "pass"
    NO_PASS = "no_pass"


@dataclass
class BudgetAnalysis:
    """Result of budget validation analysis."""
    result: BudgetValidity  # "pass" or "no_pass"
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
        budget_data: BudgetDataIn
    ) -> Result[BudgetAnalysis]:
        """
        Analyze budget data and determine if it shows a positive surplus.
        
        Args:
            budget_data: BudgetDataIn model containing budget information
            
        Returns:
            Result containing BudgetAnalysis
        """
        try:
            # Extract budget values from the validated model
            total_net_income = budget_data.total_net_income
            total_expenses = budget_data.total_expenses
            
            # Calculate surplus
            surplus = total_net_income - total_expenses
            
            # Determine if it's a positive surplus
            if surplus > 0:
                result = BudgetValidity.PASS
                reason = f"Positive surplus of ${surplus:,.2f} (Income: ${total_net_income:,.2f}, Expenses: ${total_expenses:,.2f})"
            else:
                result = BudgetValidity.NO_PASS
                reason = f"Negative surplus of ${surplus:,.2f} (Income: ${total_net_income:,.2f}, Expenses: ${total_expenses:,.2f})"
            
            analysis = BudgetAnalysis(
                result=result,
                reason=reason,
                total_net_income=total_net_income,
                total_expenses=total_expenses,
                surplus=surplus
            )
            
            logger.info(f"Budget analysis completed for contact {budget_data.contact_id}: {analysis.result.value}")
            return Success(analysis)
            
        except Exception as e:
            logger.error(f"Error analyzing budget validity: {e}")
            return Error(f"Analysis failed: {str(e)}")
    
    def format_budget_response(self, analysis: BudgetAnalysis, budget_data: BudgetDataIn) -> str:
        """Format the budget analysis into a user-friendly response."""
        from uwbot.utils.validation_responses import format_budget_response
        return format_budget_response(analysis, budget_data) 