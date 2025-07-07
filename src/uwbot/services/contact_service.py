"""
Contact Service for uwbot

Handles database operations for the public.contacts table.
Allows users to query contact information by ID.
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from uwbot.db.models import Contact, ContactUserField
from uwbot.db.session import get_db_session_context
from uwbot.services.hardship_validation_service import HardshipValidationService, HardshipAnalysis

logger = logging.getLogger(__name__)

class ContactService:
    """Service for managing contact information from the public.contacts table."""
    
    def __init__(self):
        self.hardship_service = HardshipValidationService()
    
    async def get_contact_by_id(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve hardship data and analyze its validity using the Gemini model.
        This replaces the previous contact lookup functionality.
        
        Args:
            contact_id: The ID of the contact to analyze
            
        Returns:
            Dictionary containing hardship analysis results or None if contact not found
        """
        try:
            # Get hardship data
            hardship_data = await self.get_contact_with_hardship_data(contact_id)
            
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
                return {
                    "contact_id": contact_id,
                    "analysis": {
                        "result": "no_pass",
                        "confidence": 0.0,
                        "reason": "No hardship data available for analysis"
                    },
                    "formatted_response": f"No hardship data found for contact {contact_id}. Please ensure hardship information has been provided."
                }
            
            # Analyze hardship validity
            analysis_result = await self.hardship_service.analyze_hardship_validity(hardship_data)
            
            if analysis_result.is_error():
                logger.error(f"Hardship analysis failed for contact {contact_id}: {analysis_result.error}")
                return {
                    "contact_id": contact_id,
                    "error": str(analysis_result.error),
                    "analysis": None,
                    "formatted_response": f"Unable to analyze hardship data for contact {contact_id}. Please try again or contact support."
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
            return {
                "contact_id": contact_id,
                "error": str(e),
                "analysis": None,
                "formatted_response": f"Error analyzing hardship data for contact {contact_id}. Please try again."
            }
    
    async def get_contact_with_hardship_data(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve contact information with hardship data using the exact query structure provided.
        
        Args:
            contact_id: The ID of the contact to retrieve
            
        Returns:
            Dictionary containing contact and hardship information or None if not found
        """
        try:
            async with get_db_session_context() as session:
                # Use the exact query structure you provided
                query = text("""
                    SELECT contacts.id,
                           contacts.acctid,
                           contacts.del as del_flag,
                           contacts.iscoapp,
                           contacts.c_type,
                           contacts.leadstatus,
                           financial_hardship.f_string as financial_hardship,
                           hardship_description.f_string as hardship_description
                    FROM contacts
                    LEFT JOIN contacts_userfields financial_hardship ON contacts.id = financial_hardship.contact_id AND financial_hardship.custom_id = 322256
                    LEFT JOIN contacts_userfields hardship_description ON contacts.id = hardship_description.contact_id AND hardship_description.custom_id = 322271
                    WHERE contacts.id = :contact_id
                """)
                
                result = await session.execute(query, {"contact_id": contact_id})
                row = result.fetchone()
                
                if row:
                    return {
                        "contact_id": row.id,
                        "acctid": row.acctid,
                        "del": row.del_flag,
                        "iscoapp": row.iscoapp,
                        "c_type": row.c_type,
                        "leadstatus": row.leadstatus,
                        "financial_hardship": row.financial_hardship,
                        "hardship_description": row.hardship_description,
                    }
                else:
                    logger.info(f"Contact with ID {contact_id} not found")
                    return None
                    
        except SQLAlchemyError as e:
            logger.error(f"Database error while retrieving contact hardship data {contact_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error while retrieving contact hardship data {contact_id}: {e}")
            return None
    
    def format_contact_response(self, contact: Dict[str, Any]) -> str:
        """
        Format hardship analysis results into a user-friendly response.
        
        Args:
            contact: Hardship analysis dictionary from get_contact_by_id
            
        Returns:
            Formatted string response
        """
        if not contact:
            return "No hardship data found for that contact ID. Please ensure hardship information has been provided."
        
        # If there's a formatted response already provided, use it
        if contact.get('formatted_response'):
            return contact['formatted_response']
        
        # If there's an error, return the error message
        if contact.get('error'):
            return f"Error analyzing hardship data: {contact['error']}"
        
        # If there's analysis data, format it
        analysis = contact.get('analysis')
        if analysis:
            result = analysis.get('result', 'unknown')
            confidence = analysis.get('confidence', 0.0)
            reason = analysis.get('reason', 'No reason provided')
            
            # Format confidence as percentage with one decimal place
            confidence_percent = f"{confidence * 100:.1f}%"
            
            response_parts = [
                f"Financial Hardship Analysis for Contact {contact.get('contact_id', 'Unknown')}",
                f"Result: {result.upper()}",
                f"Confidence: {confidence_percent}",
                f"Reason: {reason}"
            ]
            
            return "\n".join(response_parts)
        
        return "Unable to format hardship analysis results. Please try again."
    
    def extract_contact_id_from_message(self, message: str) -> Optional[int]:
        """
        Extract contact ID from user message using various patterns.
        
        Args:
            message: User message text
            
        Returns:
            Contact ID if found, None otherwise
        """
        import re
        
        # Look for patterns like "ID 123", "contact 456", "user 789", etc.
        patterns = [
            r'(?:contact|user|id|person)\s+(?:#)?(\d+)',
            r'(\d+)\s+(?:contact|user|id)',
            r'find\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'get\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'look\s+up\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'search\s+for\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'(\d+)',  # Fallback: just look for any number
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue
        
        return None 