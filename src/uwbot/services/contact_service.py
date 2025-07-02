"""
Contact Service for uwbot

Handles database operations for the public.contacts table.
Allows users to query contact information by ID.
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from uwbot.db.models import Contact
from uwbot.db.session import get_db_session_context

logger = logging.getLogger(__name__)

class ContactService:
    """Service for managing contact information from the public.contacts table."""
    
    def __init__(self):
        pass
    
    async def get_contact_by_id(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve contact information by ID from the public.contacts table.
        
        Args:
            contact_id: The ID of the contact to retrieve
            
        Returns:
            Dictionary containing contact information or None if not found
        """
        try:
            async with get_db_session_context() as session:
                # Query the public.contacts table
                stmt = select(Contact).where(Contact.id == contact_id)
                result = await session.execute(stmt)
                contact = result.scalar_one_or_none()
                
                if contact:
                    return {
                        "id": contact.id,
                        "first_name": contact.firstname,
                        "last_name": contact.lastname,
                    }
                else:
                    logger.info(f"Contact with ID {contact_id} not found")
                    return None
                    
        except SQLAlchemyError as e:
            logger.error(f"Database error while retrieving contact {contact_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error while retrieving contact {contact_id}: {e}")
            return None
    
    async def search_contacts_by_name(self, name: str, limit: int = 10) -> list[Dict[str, Any]]:
        """
        Search contacts by first name or last name (case-insensitive).
        
        Args:
            name: Name to search for
            limit: Maximum number of results to return
            
        Returns:
            List of matching contacts
        """
        try:
            async with get_db_session_context() as session:
                # Search in both firstname and lastname fields
                search_term = f"%{name}%"
                stmt = select(Contact).where(
                    (Contact.firstname.ilike(search_term)) | 
                    (Contact.lastname.ilike(search_term))
                ).limit(limit)
                
                result = await session.execute(stmt)
                contacts = result.scalars().all()
                
                return [
                    {
                        "id": contact.id,
                        "firstname": contact.firstname,
                        "lastname": contact.lastname,
                    }
                    for contact in contacts
                ]
                
        except SQLAlchemyError as e:
            logger.error(f"Database error while searching contacts for '{name}': {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error while searching contacts for '{name}': {e}")
            return []
    
    async def get_contact_count(self) -> int:
        """
        Get the total number of contacts in the database.
        
        Returns:
            Total number of contacts
        """
        try:
            async with get_db_session_context() as session:
                stmt = select(Contact)
                result = await session.execute(stmt)
                return len(result.scalars().all())
                
        except SQLAlchemyError as e:
            logger.error(f"Database error while counting contacts: {e}")
            return 0
        except Exception as e:
            logger.error(f"Unexpected error while counting contacts: {e}")
            return 0
    
    def format_contact_response(self, contact: Dict[str, Any]) -> str:
        """
        Format contact information into a user-friendly response.
        
        Args:
            contact: Contact dictionary from get_contact_by_id
            
        Returns:
            Formatted string response
        """
        if not contact:
            return "I couldn't find a contact with that ID. Please check the ID and try again."
        
        response_parts = [f"**Contact Information:**"]
        
        # Format full name
        first_name = contact.get('first_name', '')
        last_name = contact.get('last_name', '')
        if first_name and last_name:
            response_parts.append(f"• **Name:** {first_name} {last_name}")
        elif first_name:
            response_parts.append(f"• **Name:** {first_name}")
        elif last_name:
            response_parts.append(f"• **Name:** {last_name}")
        
        if contact.get('email'):
            response_parts.append(f"• **Email:** {contact['email']}")
        
        if contact.get('phone'):
            response_parts.append(f"• **Phone:** {contact['phone']}")
        
        return "\n".join(response_parts)
    
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