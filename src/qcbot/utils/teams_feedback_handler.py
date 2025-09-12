"""
Teams Feedback Handler Utility for QC Bot

This utility handles Microsoft Teams built-in feedback system requests,
separating the feedback processing logic from the main router.
"""

import logging
from typing import Dict, Any, Optional
from qcbot.services.feedback_service import MemoryEfficientFeedbackService

logger = logging.getLogger(__name__)


class TeamsFeedbackHandler:
    """Handler for Microsoft Teams built-in feedback system."""
    
    def __init__(self, feedback_service: MemoryEfficientFeedbackService):
        self.feedback_service = feedback_service
    
    async def handle_message_execute_action(self, req_value: Dict[str, Any], user_id: str, conv_id: str) -> Dict[str, Any]:
        """
        Handle Teams' Action.Execute events (built-in feedback buttons).
        
        Args:
            req_value: The value payload from the Teams request
            user_id: The user ID
            conv_id: The conversation ID
            
        Returns:
            Empty dict as required by Teams documentation
        """
        try:
            logger.info(f"🔴 TEAMS ACTION.EXECUTE: message/executeAction received")
            logger.info(f"🔴 PAYLOAD: {req_value}")
            
            # This is Teams' Action.Execute from built-in feedback
            # Teams sends this when users interact with native feedback buttons
            # We don't need to process this further as it's just an acknowledgment
            
            return {}
            
        except Exception as e:
            logger.error(f"🔴 Error handling Teams Action.Execute: {e}")
            # Always return empty JSON object to prevent Teams UI errors
            return {}
    
    async def handle_compose_extensions_submit_action(
        self, 
        req_value: Dict[str, Any], 
        user_id: str, 
        conv_id: str
    ) -> Dict[str, Any]:
        """
        Handle Teams' built-in feedback form submissions.
        
        Args:
            req_value: The value payload from the Teams request
            user_id: The user ID
            conv_id: The conversation ID
            
        Returns:
            Empty dict as required by Teams documentation
        """
        try:
            logger.info(f"🔴 TEAMS BUILT-IN FEEDBACK: composeExtensions/submitAction received")
            logger.info(f"🔴 PAYLOAD: {req_value}")
            
            # This is Teams' built-in feedback form submission
            # The payload contains the user's feedback from the form
            
            feedback_data = req_value or {}
            
            # Extract feedback information
            # Teams sends the feedback in various possible formats
            user_feedback = ""
            feedback_category = "general"
            
            # Try to extract the feedback text from various possible fields
            for possible_field in ['feedback', 'comment', 'text', 'data', 'value']:
                if possible_field in feedback_data and feedback_data[possible_field]:
                    user_feedback = str(feedback_data[possible_field]).strip()
                    break
            
            # If no direct feedback text, check nested objects
            if not user_feedback:
                for key, value in feedback_data.items():
                    if isinstance(value, dict):
                        for nested_key in ['feedback', 'comment', 'text']:
                            if nested_key in value and value[nested_key]:
                                user_feedback = str(value[nested_key]).strip()
                                break
                        if user_feedback:
                            break
            
            logger.info(f"🔴 Extracted feedback: '{user_feedback}'")
            
            # Record the feedback in our database if we have content
            if user_feedback:
                try:
                    # Record as general session feedback since it's from Teams' form
                    await self.feedback_service.record_feedback(
                        user_id=user_id,
                        rating=3,  # Default neutral rating for text feedback
                        comment=user_feedback,
                        session_id=conv_id,
                    )
                    logger.info(f"🔴 Recorded Teams built-in feedback: '{user_feedback[:50]}...'")
                except Exception as e:
                    logger.error(f"🔴 Error recording Teams feedback: {e}")
            
            # CRITICAL: Return empty JSON object as per Microsoft Teams documentation
            return {}
            
        except Exception as e:
            logger.error(f"🔴 Error handling Teams built-in feedback: {e}")
            # Always return empty JSON object to prevent Teams UI errors
            return {}
    
    async def handle_builtin_feedback_loop(self, req_value: Dict[str, Any], user_id: str, conv_id: str, reply_to_id: str = None) -> Dict[str, Any]:
        """
        Handle Teams' built-in feedback loop events.
        
        Args:
            req_value: The value payload from the Teams request
            user_id: The user ID
            conv_id: The conversation ID
            reply_to_id: Optional reply to message ID
            
        Returns:
            Empty dict as required by Teams documentation
        """
        try:
            logger.info(f"🔴 TEAMS BUILT-IN FEEDBACK LOOP: feedbackLoop received")
            logger.info(f"🔴 PAYLOAD: {req_value}")
            
            # This is Teams' built-in feedback loop
            # Extract feedback data
            feedback_data = req_value or {}
            
            # Try to extract feedback information
            reaction = None
            feedback_text = ""
            
            if 'feedbackLoop' in feedback_data:
                loop_data = feedback_data.get('feedbackLoop', {})
                reaction = loop_data.get('reaction') or loop_data.get('type')
                feedback_text = loop_data.get('comment', '')
            elif 'reaction' in feedback_data:
                reaction = feedback_data.get('reaction')
                feedback_text = feedback_data.get('comment', '')
            
            # Default if no specific reaction found
            if not reaction:
                reaction = 'like'  # Default assumption for successful invoke
            
            # Normalize reaction
            standardized_feedback = str(reaction).lower()
            if standardized_feedback in ['thumbsup', 'up', '👍', 'positive']:
                standardized_feedback = 'like'
            elif standardized_feedback in ['thumbsdown', 'down', '👎', 'negative']:
                standardized_feedback = 'dislike'
            
            logger.info(f"🔴 Built-in feedback loop: reaction={reaction} -> standardized={standardized_feedback}, text='{feedback_text}'")
            
            # Record the feedback if we have content
            if feedback_text:
                try:
                    # For built-in Teams feedback, try to find a target message
                    # If no specific message is found, we'll record it as general feedback
                    # but this should be rare for built-in feedback
                    await self.feedback_service.record_feedback(
                        user_id=user_id,
                        rating=5 if standardized_feedback == 'like' else 2,  # Convert to rating
                        comment=feedback_text,
                        session_id=conv_id,
                    )
                    logger.info(f"🔴 Recorded built-in feedback loop as general feedback: {standardized_feedback}")
                except Exception as e:
                    logger.error(f"🔴 Error recording built-in feedback loop: {e}")
            
            # CRITICAL: Return empty JSON object as per Microsoft Teams documentation
            return {}
            
        except Exception as e:
            logger.error(f"🔴 Error handling Teams built-in feedback loop: {e}")
            # Always return empty JSON object to prevent Teams UI errors
            return {}
    
    async def handle_message_feedback_submit(self, req_value: Dict[str, Any], user_id: str, conv_id: str, reply_to_id: str = None) -> Dict[str, Any]:
        """
        Handle Teams' message feedback submit events.
        
        Args:
            req_value: The value payload from the Teams request
            user_id: The user ID
            conv_id: The conversation ID
            reply_to_id: Optional reply to message ID
            
        Returns:
            Empty dict as required by Teams documentation
        """
        try:
            logger.info(f"🔴 TEAMS MESSAGE FEEDBACK: message/feedbackSubmit received")
            logger.info(f"🔴 PAYLOAD: {req_value}")
            
            # This is Teams' message-level feedback submission
            # Extract feedback data
            action_value = req_value.get('actionValue', {})
            reaction = action_value.get('reaction')
            feedback_text = ""
            
            # Extract feedback text from JSON string
            feedback_json = action_value.get('feedback', '{}')
            if isinstance(feedback_json, str):
                try:
                    import json
                    feedback_data = json.loads(feedback_json)
                    feedback_text = feedback_data.get('feedbackText', '')
                except:
                    feedback_text = feedback_json
            
            # Normalize reaction
            standardized_feedback = str(reaction).lower()
            if standardized_feedback in ['thumbsup', 'up', '👍', 'positive']:
                standardized_feedback = 'like'
            elif standardized_feedback in ['thumbsdown', 'down', '👎', 'negative']:
                standardized_feedback = 'dislike'
            
            logger.info(f"🔴 Message feedback: reaction={reaction} -> standardized={standardized_feedback}, text='{feedback_text}'")
            
            # For message-level feedback, try to get the target message ID
            target_message_id = None
            if reply_to_id:
                # Try to find bot message that corresponds to this activity ID
                target_message_id = self.feedback_service.get_bot_message_id_from_activity(reply_to_id)
                if target_message_id:
                    logger.info(f"🔴 Found target message via reply_to_id: {reply_to_id} -> {target_message_id}")
            
            # Record the feedback
            if target_message_id:
                try:
                    result = await self.feedback_service.record_builtin_teams_feedback(
                        message_id=target_message_id,
                        feedback=standardized_feedback,
                        feedback_comment=str(feedback_text).strip(),
                        user_id=user_id,
                    )
                    if result:
                        logger.info(f"🔴 Recorded message feedback for message {target_message_id}: {standardized_feedback}")
                    else:
                        logger.warning(f"🔴 Failed to record message feedback for message {target_message_id} - message may not exist in database")
                except Exception as e:
                    logger.error(f"🔴 Error recording message feedback: {e}")
            else:
                logger.info(f"🔴 Message feedback received but no target message found - recording as general feedback")
                # Record as general session feedback if we can't link to specific message
                try:
                    await self.feedback_service.record_feedback(
                        user_id=user_id,
                        rating=5 if standardized_feedback == 'like' else 2,  # Convert to rating
                        comment=feedback_text,
                        session_id=conv_id,
                    )
                    logger.info(f"🔴 Recorded general feedback: {standardized_feedback}")
                except Exception as e:
                    logger.error(f"🔴 Error recording general feedback: {e}")
            
            # CRITICAL: Return empty JSON object as per Microsoft Teams documentation
            return {}
            
        except Exception as e:
            logger.error(f"🔴 Error handling Teams message feedback: {e}")
            # Always return empty JSON object to prevent Teams UI errors
            return {}
