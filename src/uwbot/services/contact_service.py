"""
Contact Service for uwbot

Handles database operations for the public.contacts table.
Allows users to query contact information by ID.
"""

import logging
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from uwbot.infrastructure.contact_repository import ContactRepository
from uwbot.services.hardship_validation_service import HardshipValidationService
from uwbot.services.budget_validation_service import BudgetValidationService, BudgetDataIn
from uwbot.config.settings import settings

class InvalidContactIDError(ValueError):
    """Raised when a contact ID is invalid or out of range."""
    pass

logger = logging.getLogger(__name__)

class ContactQueryRequest(BaseModel):
    """Request model for contact queries with validation."""
    contact_id: int = Field(ge=1, le=999_999_999)

class ContactService:
    """Service for managing contact information from the public.contacts table."""
    
    def __init__(self, hardship_service: HardshipValidationService, repository: ContactRepository):
        self.hardship_service = hardship_service
        self.budget_service = BudgetValidationService()
        self.repository = repository
        
        # Per-request cache for hardship data to avoid duplicate queries
        self._hardship_cache = {}
        
        logger.info("ContactService initialized with repository pattern")
    

    
    def validate_contact_id(self, contact_id: int) -> bool:
        """
        Validate contact ID range.
        
        Args:
            contact_id: The contact ID to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            ContactQueryRequest(contact_id=contact_id)
            return True
        except ValueError:
            return False
    
    async def _get_or_fetch_hardship(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """
        Get hardship data from cache or fetch from database.
        
        This helper method implements a per-request cache to avoid
        duplicate database queries for the same contact ID.
        
        Args:
            contact_id: The contact ID to fetch hardship data for
            
        Returns:
            Hardship data dictionary or None if not found
        """
        # Check cache first
        if contact_id in self._hardship_cache:
            logger.debug(f"Using cached hardship data for contact {contact_id}")
            return self._hardship_cache[contact_id]
        
        # Fetch from database
        logger.debug(f"Fetching hardship data for contact {contact_id} from database")
        data = await self.repository.fetch_contact_with_hardship_data(contact_id)
        
        # Cache the result (even if None, to avoid repeated DB calls)
        self._hardship_cache[contact_id] = data
        return data
    
    async def analyze_contact_hardship(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve hardship data and analyze its validity using the Gemini model.
        
        Args:
            contact_id: The ID of the contact to analyze
            
        Returns:
            Dictionary containing hardship analysis results or None if contact not found
        """
        # Validate contact ID first
        if not self.validate_contact_id(contact_id):
            raise InvalidContactIDError(f"Contact ID {contact_id} is out of range")
        
        try:
            # Get hardship data using cached fetch
            hardship_data = await self._get_or_fetch_hardship(contact_id)
            
            if not hardship_data:
                logger.warning(f"No hardship data found for contact {contact_id}")
                return None
            
            # Check if there's any hardship data to analyze
            has_hardship_data = any([
                hardship_data.get('financial_hardship'),
                hardship_data.get('hardship_description')
            ])
            
            if not has_hardship_data:
                logger.info(f"No hardship data available for contact {contact_id}")
                from uwbot.utils.validation_responses import format_no_data_response
                return {
                    "contact_id": contact_id,
                    "analysis": {
                        "result": "no_pass",
                        "confidence": 0.0,
                        "reason": "No hardship data available for analysis"
                    },
                    "formatted_response": format_no_data_response(contact_id, "hardship")
                }
            
            # Analyze hardship validity
            analysis_result = await self.hardship_service.analyze_hardship_validity(hardship_data)
            
            if analysis_result.is_error():
                logger.error(f"Hardship analysis failed for contact {contact_id}: {analysis_result.error}")
                from uwbot.utils.validation_responses import format_error_response
                return {
                    "contact_id": contact_id,
                    "error": str(analysis_result.error),
                    "analysis": None,
                    "formatted_response": format_error_response(contact_id, f"Unable to analyze hardship data for contact {contact_id}. Please try again or contact support.", "hardship")
                }
            
            analysis = analysis_result.value
            formatted_response = self.hardship_service.format_hardship_response(analysis, hardship_data)
            
            return {
                "contact_id": contact_id,
                "hardship_data": hardship_data,
                "analysis": {
                    "result": analysis.result.value,
                    "confidence": analysis.confidence,
                    "reason": analysis.reason
                },
                "formatted_response": formatted_response
            }
            
        except Exception as e:
            logger.error(f"Error analyzing hardship for contact {contact_id}: {e}")
            from uwbot.utils.validation_responses import format_error_response
            return {
                "contact_id": contact_id,
                "error": str(e),
                "analysis": None,
                "formatted_response": format_error_response(contact_id, f"Error analyzing hardship data for contact {contact_id}. Please try again.", "hardship")
            }
    
    async def get_contact_with_budget_data(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve contact information with budget data using repository.
        
        Args:
            contact_id: The ID of the contact to retrieve
            
        Returns:
            Dictionary containing contact and budget information or None if not found
        """
        # Validate contact ID first
        if not self.validate_contact_id(contact_id):
            raise InvalidContactIDError(f"Contact ID {contact_id} is out of range")
        
        try:
            return await self.repository.fetch_contact_with_budget_data(contact_id)
        except Exception as e:
            logger.error(f"Error retrieving contact budget data for {contact_id}: {e}")
            return None
    
    async def get_contact_budget_analysis(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve budget data and analyze if the client has a positive surplus.
        
        Args:
            contact_id: The ID of the contact to analyze
            
        Returns:
            Dictionary containing budget analysis results or None if contact not found
        """
        try:
            # Get budget data
            budget_data = await self.get_contact_with_budget_data(contact_id)
            
            if not budget_data:
                logger.warning(f"No budget data found for contact {contact_id}")
                return None
            
            # Check if there's any budget data to analyze
            has_budget_data = any([
                budget_data.get('total_net_income', 0) > 0,
                budget_data.get('total_expenses', 0) > 0
            ])
            
            if not has_budget_data:
                logger.info(f"No budget data available for contact {contact_id}")
                from uwbot.utils.validation_responses import format_no_data_response
                return {
                    "contact_id": contact_id,
                    "analysis": {
                        "result": "no_pass",
                        "reason": "No budget data available for analysis"
                    },
                    "formatted_response": format_no_data_response(contact_id, "budget")
                }
            
            # Convert dictionary to Pydantic model for type safety
            budget_data_model = BudgetDataIn(
                contact_id=budget_data['contact_id'],
                total_net_income=budget_data['total_net_income'],
                total_expenses=budget_data['total_expenses']
            )
            
            # Analyze budget validity
            analysis_result = await self.budget_service.analyze_budget_validity(budget_data_model)
            
            if analysis_result.is_error():
                logger.error(f"Budget analysis failed for contact {contact_id}: {analysis_result.error}")
                from uwbot.utils.validation_responses import format_error_response
                return {
                    "contact_id": contact_id,
                    "error": str(analysis_result.error),
                    "analysis": None,
                    "formatted_response": format_error_response(contact_id, f"Unable to analyze budget data for contact {contact_id}. Please try again or contact support.", "budget")
                }
            
            analysis = analysis_result.value
            formatted_response = self.budget_service.format_budget_response(analysis, budget_data_model)
            
            return {
                "contact_id": contact_id,
                "budget_data": budget_data,
                "analysis": {
                    "result": analysis.result.value,
                    "reason": analysis.reason,
                    "total_net_income": analysis.total_net_income,
                    "total_expenses": analysis.total_expenses,
                    "surplus": analysis.surplus
                },
                "formatted_response": formatted_response
            }
            
        except Exception as e:
            logger.error(f"Error analyzing budget for contact {contact_id}: {e}")
            from uwbot.utils.validation_responses import format_error_response
            return {
                "contact_id": contact_id,
                "error": str(e),
                "analysis": None,
                "formatted_response": format_error_response(contact_id, f"Error analyzing budget data for contact {contact_id}. Please try again.", "budget")
            }
    
    async def get_contact_with_hardship_data(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve contact information with hardship data using repository.
        
        Args:
            contact_id: The ID of the contact to retrieve
            
        Returns:
            Dictionary containing contact and hardship information or None if not found
        """
        # Validate contact ID first
        if not self.validate_contact_id(contact_id):
            raise InvalidContactIDError(f"Contact ID {contact_id} is out of range")
        
        try:
            return await self._get_or_fetch_hardship(contact_id)
        except Exception as e:
            logger.error(f"Error retrieving contact hardship data for {contact_id}: {e}")
            return None
    

    
    def format_contact_response(self, contact: Dict[str, Any]) -> str:
        """
        Format hardship analysis results into a user-friendly response.
        
        Args:
            contact: Hardship analysis dictionary from analyze_contact_hardship
            
        Returns:
            Formatted string response
        """
        from uwbot.utils.validation_responses import format_contact_response
        return format_contact_response(contact)
    
    def format_budget_response(self, budget: Dict[str, Any]) -> str:
        """
        Format budget analysis results into a user-friendly response.
        
        Args:
            budget: Budget analysis dictionary from get_contact_budget_analysis
            
        Returns:
            Formatted string response
        """
        from uwbot.utils.validation_responses import format_budget_analysis_response
        return format_budget_analysis_response(budget)
    
    def extract_contact_id_from_message(self, message: str) -> Optional[int]:
        """
        Extract contact ID from user message using various patterns.
        
        Args:
            message: User message text
            
        Returns:
            Contact ID if found and valid, None otherwise
        """
        import re
        
        # Look for patterns like "ID 123", "contact 456", "user 789", etc.
        # Only capture positive numbers (no negative numbers)
        patterns = [
            r'(?:contact|user|id|person)\s+(?:#)?(\d+)',
            r'(\d+)\s+(?:contact|user|id)',
            r'find\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'get\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'look\s+up\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'search\s+for\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'(\d+)',  # Fallback: just look for any positive number
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                try:
                    contact_id = int(match.group(1))
                    # Validate the extracted contact ID
                    if self.validate_contact_id(contact_id):
                        return contact_id
                    else:
                        logger.warning(f"Extracted invalid contact ID from message: {contact_id}")
                        return None
                except (ValueError, IndexError):
                    continue
        
        return None 