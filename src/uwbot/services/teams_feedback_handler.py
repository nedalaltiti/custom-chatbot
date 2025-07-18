"""
Teams Feedback Handler Service

This service handles Microsoft Teams built-in feedback system requests,
separating the feedback processing logic from the main router.
"""

import logging
from typing import Dict, Any, Optional
from uwbot.services.feedback_service import FeedbackService

logger = logging.getLogger(__name__)


class TeamsFeedbackHandler:
    """Handler for Microsoft Teams built-in feedback system."""
    
    def __init__(self, feedback_service: FeedbackService):
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
        Handle Teams' built-in feedback loop (thumbs up/down buttons).
        
        Args:
            req_value: The value payload from the Teams request
            user_id: The user ID
            conv_id: The conversation ID
            reply_to_id: Optional reply_to_id to link feedback to specific message
            
        Returns:
            Empty dict as required by Teams documentation
        """
        try:
            logger.info(f"🔵 Processing BUILT-IN Teams feedback (message-level)")
            
            # Extract feedback data from Teams message-level feedback format
            reaction = None
            feedback_text = ""
            
            # Teams sends message-level feedback in this format:
            # {'actionName': 'feedback', 'actionValue': {'reaction': 'dislike', 'feedback': '{"feedbackText":"bad"}'}}
            if req_value.get('actionName') == 'feedback' and 'actionValue' in req_value:
                action_value = req_value.get('actionValue', {})
                reaction = action_value.get('reaction')
                
                # Extract feedback text from JSON string
                feedback_json = action_value.get('feedback', '{}')
                if isinstance(feedback_json, str):
                    try:
                        import json
                        feedback_data = json.loads(feedback_json)
                        feedback_text = feedback_data.get('feedbackText', '')
                    except:
                        feedback_text = feedback_json
            
            # Fallback extraction methods
            if not reaction:
                if 'feedbackLoop' in req_value:
                    feedback_data = req_value.get('feedbackLoop', {})
                    reaction = feedback_data.get('reaction') or feedback_data.get('type')
                    feedback_text = feedback_data.get('comment', '')
                elif 'reaction' in req_value:
                    reaction = req_value.get('reaction')
                    feedback_text = req_value.get('comment', '')
            
            # Default if no specific reaction found
            if not reaction:
                reaction = 'like'  # Default assumption for successful invoke
            
            # Normalize reaction
            standardized_feedback = str(reaction).lower()
            if standardized_feedback in ['thumbsup', 'up', '👍', 'positive']:
                standardized_feedback = 'like'
            elif standardized_feedback in ['thumbsdown', 'down', '👎', 'negative']:
                standardized_feedback = 'dislike'
            
            logger.info(f"🔵 Built-in feedback: reaction={reaction} -> standardized={standardized_feedback}, text='{feedback_text}'")
            
            # For built-in Teams feedback, try to get the message they're responding to
            target_message_id = None
            
            # Method 1: Use reply_to_id if available
            if reply_to_id:
                target_message_id = self.feedback_service.get_bot_message_id_from_activity(reply_to_id)
                if target_message_id:
                    logger.info(f"🔵 Found target message via reply_to_id: {reply_to_id} -> {target_message_id}")
            
            # Record the feedback if we have a target message
            if target_message_id:
                try:
                    await self.feedback_service.record_message_reply_feedback(
                        message_id=target_message_id,
                        feedback=standardized_feedback,
                        feedback_comment=str(feedback_text).strip(),
                    )
                    logger.info(f"🔵 Recorded built-in feedback for message {target_message_id}: {standardized_feedback}")
                except Exception as e:
                    logger.error(f"🔴 Error recording built-in feedback: {e}")
            else:
                logger.info(f"🔵 Built-in feedback received but no target message found - recording as general feedback")
                # Record as general session feedback if we can't link to specific message
                try:
                    await self.feedback_service.record_feedback(
                        user_id=user_id,
                        rating=5 if standardized_feedback == 'like' else 2,  # Convert to rating
                        comment=feedback_text,
                        session_id=conv_id,
                    )
                    logger.info(f"🔵 Recorded general feedback: {standardized_feedback}")
                except Exception as e:
                    logger.error(f"🔴 Error recording general feedback: {e}")
            
            # CRITICAL: Return empty JSON object as per Microsoft Teams documentation
            # Teams built-in feedback requires exactly {} as response
            return {}
            
        except Exception as e:
            logger.error(f"🔴 Error handling Teams built-in feedback loop: {e}")
            return {} 