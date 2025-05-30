import os
import logging
from typing import Dict, Optional, List
from hrbot.infrastructure.teams_adapter import TeamsAdapter
from hrbot.utils.result import Result, Success, Error
logger = logging.getLogger(__name__)
# Define the NOI link
NOI_LINK = 'https://usclarity.sharepoint.com/sites/HRJordan/Lists/Notice%20of%20Investigation%20NOI/AllItems.aspx?ct=1742897751496&or=Teams%2DHL&LOF=1'
DEFAULT_NO_TITLE = "No title"
class NOIAccessChecker:
    """
    Checks if users have access to submit a Notice of Investigation (NOI)
    based on their job title retrieved from Microsoft Graph API.
    """
    _MANAGERIAL_KEYWORDS_LOWERCASE: List[str] = ['chief', 'manager', 'supervisor', 'director']
    _NOI_KEYWORDS_LOWERCASE: List[str] = ['noi', 'notice of investigation', 'violation']
    def __init__(self):
        """Initialize the NOI access checker with TeamsAdapter."""
        self.teams_adapter = TeamsAdapter()
        logger.info("NOI Access Checker initialized with TeamsAdapter")
    def is_managerial_position(self, title: Optional[str]) -> bool:
        """
        Check if a job title is considered a managerial position.
        Args:
            title: The user's job title
        Returns:
            True if the title contains managerial keywords, False otherwise
        """
        if not title or title == DEFAULT_NO_TITLE or title == "Unknown":
            logger.debug(f"No valid job title ('{title}') provided, considered non-managerial.")
            return False
        title_lower = title.lower()
        for keyword in self._MANAGERIAL_KEYWORDS_LOWERCASE:
            if keyword in title_lower:
                logger.info(f"Managerial position detected: job title '{title}' contains '{keyword}'.")
                return True
        logger.info(f"Job title '{title}' is not a managerial position.")
        return False
    async def get_user_title(self, user_id: str) -> str: 
        """
        Get a user's job title from Microsoft Graph API using TeamsAdapter.
        Args:
            user_id: The user's Azure AD Object ID
        Returns:
            The user's job title or 'No title' if not found/error.
        """
        if not user_id or user_id == "anonymous":
            logger.warning("Empty or anonymous user ID provided to get_user_title.")
            return DEFAULT_NO_TITLE
        logger.info(f"Getting job title for user with Azure AD Object ID: {user_id}")
        
        try:
            # Use TeamsAdapter to get the user profile
            profile = await self.teams_adapter.get_user_profile(user_id)
            job_title = profile.get("jobTitle", DEFAULT_NO_TITLE)
            
            # If job title is empty, use default
            if not job_title:
                job_title = DEFAULT_NO_TITLE
                
            logger.info(f"Retrieved job title for user {user_id}: '{job_title}'")
            return job_title
        
        except Exception as e:
            logger.error(f"Exception in NOIAccessChecker.get_user_title: {str(e)}", exc_info=True)
            return DEFAULT_NO_TITLE
    async def check_access(self, user_id: str, job_title: Optional[str] = None) -> Dict:
        """
        Check if a user has access to submit a Notice of Investigation.
        Args:
            user_id: The user's Azure AD Object ID
            job_title: Optional pre-fetched job title
        Returns:
            dict: A response containing the user's job title and access status
        """
        # Use provided job title if available, otherwise fetch from Teams
        current_job_title = job_title if job_title else await self.get_user_title(user_id)
        
        logger.info(f"Checking NOI access for user '{user_id}' with job title: '{current_job_title}'")
        has_access = self.is_managerial_position(current_job_title)
        if has_access:
            response_message = (
                f'Your current position is: {current_job_title}\n\n'
                f'As a managerial employee, you have access to submit a Notice of Investigation. '
                f'Here\'s the link:\n\n{NOI_LINK}'
            )
        else:
            response_message = (
                f'Your current position is: {current_job_title}\n\n'
                'You do not have direct access to submit a Notice of Investigation. \n\n'
                'Please contact your direct manager for assistance.'
            )
        return {
            'has_access': has_access,
            'job_title': current_job_title,
            'response': response_message
        }
    @staticmethod
    def is_noi_related(message: str) -> bool:
        """
        Check if a message is related to NOI requests.
        Args:
            message: The message to check
        Returns:
            bool: True if the message is NOI-related, False otherwise
        """
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in NOIAccessChecker._NOI_KEYWORDS_LOWERCASE)