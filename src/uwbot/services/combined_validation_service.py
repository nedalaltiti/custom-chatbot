"""
Combined Validation Service for uwbot

This service handles combined hardship and budget validation analysis.
It provides a unified interface for analyzing both hardship and budget data
for a given contact ID.
"""

import logging
from typing import Optional, Dict, Any
from uwbot.services.hardship_validation_service import HardshipValidationService
from uwbot.services.budget_validation_service import BudgetValidationService, BudgetDataIn
from uwbot.infrastructure.contact_repository import ContactRepository
from uwbot.utils.validation_responses import format_combined_validation_response, format_error_response, format_no_data_response

logger = logging.getLogger(__name__)

class CombinedValidationService:
    """Service for performing combined hardship and budget validation analysis."""
    
    def __init__(self, hardship_service: HardshipValidationService, budget_service: BudgetValidationService, repository: ContactRepository):
        self.hardship_service = hardship_service
        self.budget_service = budget_service
        self.repository = repository
        
        logger.info("CombinedValidationService initialized")
    
    async def perform_combined_validation(
        self, 
        contact_id: int, 
        hardship_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Perform combined hardship and budget validation analysis.
        
        Args:
            contact_id: The ID of the contact to analyze
            hardship_data: Optional pre-fetched hardship data to avoid duplicate queries
            
        Returns:
            Dictionary containing combined hardship and budget analysis results
        """
        try:
            # Use provided hardship data or fetch it
            if hardship_data is None:
                hardship_data = await self.repository.fetch_contact_with_hardship_data(contact_id)
            
            # Get budget data using repository
            budget_data = await self.repository.fetch_contact_with_budget_data(contact_id)
            
            # Check if we have any data at all
            has_hardship_data = hardship_data and any([
                hardship_data.get('financial_hardship'),
                hardship_data.get('hardship_description')
            ])
            
            has_budget_data = budget_data and any([
                budget_data.get('total_net_income', 0) > 0,
                budget_data.get('total_expenses', 0) > 0
            ])
            
            if not has_hardship_data and not has_budget_data:
                logger.warning(f"No hardship or budget data found for contact {contact_id}")
                return {
                    "contact_id": contact_id,
                    "hardship_analysis": None,
                    "budget_analysis": None,
                    "combined_result": "no_data",
                    "formatted_response": format_no_data_response(contact_id, "validation")
                }
            
            # Analyze hardship if data exists
            hardship_analysis = None
            if has_hardship_data:
                hardship_result = await self.hardship_service.analyze_hardship_validity(hardship_data)
                if not hardship_result.is_error():
                    hardship_analysis = hardship_result.value
                else:
                    logger.error(f"Hardship analysis failed for contact {contact_id}: {hardship_result.error}")
            
            # Analyze budget if data exists
            budget_analysis = None
            if has_budget_data:
                # Convert dictionary to Pydantic model for type safety
                budget_data_model = BudgetDataIn(
                    contact_id=budget_data['contact_id'],
                    total_net_income=budget_data['total_net_income'],
                    total_expenses=budget_data['total_expenses']
                )
                budget_result = await self.budget_service.analyze_budget_validity(budget_data_model)
                if not budget_result.is_error():
                    budget_analysis = budget_result.value
                else:
                    logger.error(f"Budget analysis failed for contact {contact_id}: {budget_result.error}")
            
            # Determine combined result
            combined_result = self._determine_combined_result(hardship_analysis, budget_analysis)
            
            # Format combined response
            formatted_response = self._format_combined_response(
                contact_id, hardship_data, budget_data, hardship_analysis, budget_analysis, combined_result
            )
            
            return {
                "contact_id": contact_id,
                "hardship_data": hardship_data,
                "budget_data": budget_data,
                "hardship_analysis": {
                    "result": hardship_analysis.result.value if hardship_analysis else "no_data",
                    "confidence": hardship_analysis.confidence if hardship_analysis else 0.0,
                    "reason": hardship_analysis.reason if hardship_analysis else "No hardship data available"
                } if hardship_analysis else None,
                "budget_analysis": {
                    "result": budget_analysis.result.value if budget_analysis else "no_data",
                    "reason": budget_analysis.reason if budget_analysis else "No budget data available",
                    "total_net_income": budget_analysis.total_net_income if budget_analysis else 0.0,
                    "total_expenses": budget_analysis.total_expenses if budget_analysis else 0.0,
                    "surplus": budget_analysis.surplus if budget_analysis else 0.0
                } if budget_analysis else None,
                "combined_result": combined_result,
                "formatted_response": formatted_response
            }
            
        except Exception as e:
            logger.error(f"Error performing combined validation for contact {contact_id}: {e}")
            return {
                "contact_id": contact_id,
                "error": str(e),
                "hardship_analysis": None,
                "budget_analysis": None,
                "combined_result": "error",
                "formatted_response": format_error_response(contact_id, f"Error analyzing validation data for contact {contact_id}. Please try again.", "validation")
            }
    
    def _determine_combined_result(self, hardship_analysis, budget_analysis) -> str:
        """
        Determine the combined validation result based on both hardship and budget analyses.
        
        Returns:
            "pass" - Both validations pass or at least one passes with strong confidence
            "no_pass" - Both validations fail or insufficient data
            "mixed" - One passes, one fails (needs manual review)
            "no_data" - No data available for either validation
        """
        has_hardship = hardship_analysis is not None
        has_budget = budget_analysis is not None
        
        # If no data for either, return no_data
        if not has_hardship and not has_budget:
            return "no_data"
        
        # If only one type of data available, use that result
        if has_hardship and not has_budget:
            return hardship_analysis.result.value
        elif has_budget and not has_hardship:
            return budget_analysis.result.value
        
        # Both analyses available - determine combined result
        hardship_result = hardship_analysis.result.value
        budget_result = budget_analysis.result.value
        
        # If both pass, overall result is pass
        if hardship_result == "pass" and budget_result == "pass":
            return "pass"
        
        # If both fail, overall result is no_pass
        if hardship_result == "no_pass" and budget_result == "no_pass":
            return "no_pass"
        
        # Mixed results - one passes, one fails
        # For mixed results, we lean toward "pass" if the hardship validation has high confidence
        # Budget validation is deterministic (no confidence), so we only check hardship confidence
        if hardship_result == "pass" and hardship_analysis.confidence >= 0.8:
            return "pass"
        else:
            return "mixed"
    
    def _format_combined_response(
        self, 
        contact_id: int, 
        hardship_data: Dict[str, Any], 
        budget_data: Dict[str, Any],
        hardship_analysis, 
        budget_analysis, 
        combined_result: str
    ) -> str:
        """
        Format combined hardship and budget analysis into a comprehensive response.
        """
        return format_combined_validation_response(
            contact_id, hardship_data, budget_data, hardship_analysis, budget_analysis, combined_result
        )
    
    async def validate_contact_with_prefetched_data(
        self, 
        contact_id: int, 
        hardship_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Optimized version that accepts pre-fetched hardship data.
        
        This method is specifically designed to avoid duplicate database queries when
        hardship data has already been fetched by other services.
        
        Args:
            contact_id: The ID of the contact to analyze
            hardship_data: Pre-fetched hardship data
            
        Returns:
            Dictionary containing combined hardship and budget analysis results
        """
        return await self.perform_combined_validation(contact_id, hardship_data) 