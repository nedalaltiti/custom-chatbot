"""
Card Action Handler Service

This service handles adaptive card actions and submissions,
separating the card action processing logic from the main router.
"""

import logging
from typing import Dict, Any, Optional
from uwbot.infrastructure.cards import create_feedback_card
from uwbot.infrastructure.teams_adapter import TeamsAdapter
from uwbot.services.feedback_service import FeedbackService

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
        feedback_cards: Dict[str, str],
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle submit_rating action from feedback card."""
        try:
            raw = req_value.get("rating")
            rating = int(raw) if str(raw).isdigit() else None

            if rating:
                # Preserve existing comment content when updating card
                existing_comment = req_value.get("comment", "").strip()
                
                # Highlight stars, keep the "Provide Feedback" button with preserved comment
                card = create_feedback_card(
                    selected_rating=rating,
                    interactive=True,
                    existing_comment=existing_comment
                )
                act_id = feedback_cards.get(conv_id)
                if act_id:
                    # Update the existing card instead of creating a new one
                    await self.teams_adapter.update_card(service_url, conv_id, act_id, card)
                    logger.info(f"Updated existing feedback card for conversation {conv_id} with rating {rating}")
                else:
                    # Only create new card if no existing card found
                    logger.warning(f"No existing feedback card found for conversation {conv_id}, creating new one")
                    new_act = await self.teams_adapter.send_card(service_url, conv_id, card)
                    if new_act:
                        feedback_cards[conv_id] = new_act

                # Remember we showed the stars
                state["feedback_shown"] = True
                state["awaiting_feedback"] = False 
                
        except Exception as e:
            logger.error(f"Error processing submit_rating: {e}")

        return {"text": ""}
    
    async def handle_dismiss_feedback(
        self, 
        conv_id: str, 
        service_url: str,
        feedback_cards: Dict[str, str],
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
            feedback_cards.pop(conv_id, None)
            _clear_user_session(user_id)
            
        except Exception as e:
            logger.error(f"Error processing dismiss_feedback: {e}")
        
        return {"text": ""}
    
    async def handle_submit_feedback(
        self, 
        req_value: Dict[str, Any], 
        conv_id: str, 
        service_url: str,
        feedback_cards: Dict[str, str],
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
            
            logger.info(f"Processing feedback submission - user: {user_id}, rating: {rating}, comment: '{comment}'")

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
            act_id = feedback_cards.pop(conv_id, None)
            if act_id:
                await self.teams_adapter.update_card(service_url, conv_id, act_id, submitted_card)

            state["feedback_shown"] = True
            state["awaiting_feedback"] = False 
            
            # End session immediately after feedback submission
            _clear_user_session(user_id)
            
        except Exception as e:
            logger.error(f"Error processing submit_feedback: {e}")
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
                    
                    # Send appropriate thank you message based on feedback
                    # NO thank you message for message-level feedback
                    # Message-level feedback should be silent and non-disruptive
                    
                else:
                    logger.error("Failed to record message reply feedback in database")
                    # NO acknowledgment for message-level feedback, even on database failure
                    
            except Exception as e:
                logger.error(f"Error recording message reply feedback: {e}")
                # NO acknowledgment for message-level feedback, even on error

        return {"text": ""} 