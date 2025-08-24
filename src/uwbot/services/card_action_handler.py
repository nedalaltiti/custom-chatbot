"""
Card Action Handler Service

This service handles adaptive card actions and submissions,
separating the card action processing logic from the main router.
"""

import logging
from typing import Dict, Any
from uwbot.infrastructure.cards import create_feedback_card
from uwbot.infrastructure.teams_adapter import TeamsAdapter
from uwbot.services.feedback_service import FeedbackService
from uwbot.services.feedback_card_tracker import FeedbackCardTracker

logger = logging.getLogger(__name__)


class CardActionHandler:
    """Handler for adaptive card actions and submissions."""
    
    def __init__(self, feedback_service: FeedbackService, teams_adapter: TeamsAdapter):
        self.feedback_service = feedback_service
        self.teams_adapter = teams_adapter
    
    async def handle_submit_rating(
        self, 
        req_value: Dict[str, Any], 
        conv_id: str, 
        service_url: str,
        feedback_card_tracker: FeedbackCardTracker,
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle submit_rating action from feedback card."""
        try:
            raw = req_value.get("rating")
            rating = int(raw) if str(raw).isdigit() else None

            logger.info(f"Processing submit_rating action - rating: {rating}, conversation: {conv_id}")

            if rating:
                # Preserve existing comment content when updating card
                existing_comment = req_value.get("comment", "").strip()
                
                # Create new card with selected rating
                card = create_feedback_card(
                    selected_rating=rating,
                    interactive=True,
                    existing_comment=existing_comment
                )
                
                # Get existing card activity ID
                old_act_id = feedback_card_tracker.get_feedback_card_id(conv_id)
                logger.info(f"Found existing feedback card activity ID: {old_act_id}")
                
                if old_act_id:
                    # Delete the old card first
                    try:
                        await self.teams_adapter.delete_activity(service_url, conv_id, old_act_id)
                        logger.info(f"Deleted old feedback card {old_act_id}")
                    except Exception as delete_error:
                        logger.warning(f"Failed to delete old feedback card: {delete_error}")
                
                # Send new card with selected rating
                new_act = await self.teams_adapter.send_card(service_url, conv_id, card)
                if new_act:
                    feedback_card_tracker.track_feedback_card(conv_id, new_act)
                    logger.info(f"Sent new feedback card with rating {rating} and activity ID: {new_act}")
                else:
                    logger.error(f"Failed to send new feedback card for conversation {conv_id}")

                # Remember we showed the stars
                state["feedback_shown"] = True
                state["awaiting_feedback"] = False 
                
        except Exception as e:
            logger.error(f"Error processing submit_rating: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")

        return {"text": ""}
    
    async def handle_dismiss_feedback(
        self, 
        conv_id: str, 
        service_url: str,
        feedback_card_tracker: FeedbackCardTracker,
        user_id: str,
        typing_sent: bool,
        _clear_user_session
    ) -> Dict[str, Any]:
        """Handle dismiss_feedback action from feedback card."""
        try:
            # Send typing indicator before response (only if not already sent)
            if not typing_sent:
                await self.teams_adapter.send_typing(service_url, conv_id)
            
            await self.teams_adapter.send_message(
                service_url, conv_id,
                "No problem! Feel free to reach out anytime you need validation assistance."
            )
            
            # Remove current feedback card and end session
            feedback_card_tracker.remove_feedback_card(conv_id)
            await _clear_user_session(user_id)
            
        except Exception as e:
            logger.error(f"Error processing dismiss_feedback: {e}")
        
        return {"text": ""}
    
    async def handle_submit_feedback(
        self, 
        req_value: Dict[str, Any], 
        conv_id: str, 
        service_url: str,
        feedback_card_tracker: FeedbackCardTracker,
        user_id: str,
        state: Dict[str, Any],
        typing_sent: bool,
        _clear_user_session
    ) -> Dict[str, Any]:
        """Handle submit_feedback action from feedback card."""
        try:
            raw = req_value.get("rating")
            rating = int(raw) if str(raw).isdigit() else 3
            comment = (req_value.get("comment") or "").strip()
            
            # Also check for comment in nested structures
            if not comment:
                comment = (req_value.get("commentValue") or "").strip()
            if not comment:
                # Check if comment is in a nested data structure
                for key, value in req_value.items():
                    if isinstance(value, str) and len(value.strip()) > 0 and key.lower() in ['comment', 'feedback', 'text', 'message']:
                        comment = value.strip()
                        break
            
            logger.info(f"Processing feedback submission - user: {user_id}, rating: {rating}, comment: '{comment}', conversation: {conv_id}")

            # Persist the feedback
            await self.feedback_service.record_feedback(
                user_id=user_id,
                rating=rating,
                comment=comment,
                session_id=conv_id,
            )

            # Replace the card with a non-interactive "submitted" card
            submitted_card = {
                "type": "AdaptiveCard",
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "version": "1.3",
                "body": [
                    {
                        "type": "TextBlock",
                        "text": "✅ Feedback submitted – thank you!",
                        "weight": "Bolder",
                        "size": "Medium"
                    }
                ]
            }
            
            # Get existing card activity ID
            old_act_id = feedback_card_tracker.remove_feedback_card(conv_id)
            logger.info(f"Removed feedback card tracking, activity ID: {old_act_id}")
            
            if old_act_id:
                # Delete the old card first
                try:
                    await self.teams_adapter.delete_activity(service_url, conv_id, old_act_id)
                    logger.info(f"Deleted old feedback card {old_act_id}")
                except Exception as delete_error:
                    logger.warning(f"Failed to delete old feedback card: {delete_error}")
                
                # Send new "submitted" card
                new_act = await self.teams_adapter.send_card(service_url, conv_id, submitted_card)
                if new_act:
                    logger.info(f"Sent new 'submitted' feedback card with activity ID: {new_act}")
                else:
                    logger.error(f"Failed to send new 'submitted' feedback card for conversation {conv_id}")
            else:
                logger.warning(f"No feedback card activity ID found for conversation {conv_id}")

            state["feedback_shown"] = True
            state["awaiting_feedback"] = False 
            
            # End session immediately after feedback submission
            await _clear_user_session(user_id)
            
        except Exception as e:
            logger.error(f"Error processing submit_feedback: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Always send a success response to prevent "Unable to reach app" errors
            try:
                # Send typing indicator before fallback message (only if not already sent)
                if not typing_sent:
                    await self.teams_adapter.send_typing(service_url, conv_id)
                await self.teams_adapter.send_message(service_url, conv_id, "Thank you for your feedback!")
            except Exception as send_error:
                logger.error(f"Failed to send fallback message: {send_error}")

        return {"text": ""}
    
    async def handle_message_reply_feedback(
        self, 
        req_value: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle message_reply_feedback action from feedback card."""
        action_value = req_value.get("actionValue", {})
        message_id = action_value.get("messageId")
        feedback_comment = action_value.get("feedbackComment", "")
        standardized_feedback = action_value.get("feedback", "").lower()

        if message_id and standardized_feedback:
            # Record the message reply feedback
            try:
                success = await self.feedback_service.record_message_reply_feedback(
                    message_id=int(message_id),
                    feedback=standardized_feedback,
                    feedback_comment=str(feedback_comment).strip(),
                    reaction=str(action_value)
                )
                
                if success:
                    logger.info(f"Successfully recorded message reply feedback: message_id={message_id}, feedback={standardized_feedback}")
                else:
                    logger.error("Failed to record message reply feedback in database")
                    
            except Exception as e:
                logger.error(f"Error recording message reply feedback: {e}")

        return {"text": ""} 