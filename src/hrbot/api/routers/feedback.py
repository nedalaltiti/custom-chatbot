from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
import logging
from hrbot.services.feedback_service import FeedbackService
from hrbot.services.feedback import save_feedback
from hrbot.config.settings import settings
from typing import Optional
from hrbot.infrastructure.cards import create_feedback_card
from hrbot.infrastructure.teams_adapter import TeamsAdapter

logger = logging.getLogger(__name__)

router = APIRouter()
feedback_service = FeedbackService()
teams_adapter = TeamsAdapter()

class EnhancedFeedbackRequest(BaseModel):
    user_id: str
    rating: int
    comment: Optional[str] = None
    conversation_id: Optional[str] = None
    service_url: Optional[str] = None
    user_name: Optional[str] = None
    job_title: Optional[str] = None
    session_duration: Optional[int] = None
    message_count: Optional[int] = None

@router.post("/")
async def submit_enhanced_feedback(
    feedback: EnhancedFeedbackRequest, 
    background_tasks: BackgroundTasks
):
    """Submit enhanced feedback with detailed context."""
    try:
        logger.info(f"Received enhanced feedback from user {feedback.user_id}: {feedback.rating}/5")
        
        # Save feedback with full context
        success = await feedback_service.record_feedback(
            user_id=feedback.user_id,
            rating=feedback.rating,
            comment=feedback.comment or "",
            conversation_id=feedback.conversation_id,
            user_name=feedback.user_name,
            job_title=feedback.job_title,
            session_duration=feedback.session_duration,
            message_count=feedback.message_count
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save feedback")
        
        # Send thank you message if Teams context provided
        if feedback.service_url and feedback.conversation_id:
            if feedback.rating >= 4:
                message = "Thank you for your positive feedback! We're glad to hear you had a good experience."
            elif feedback.rating == 3:
                message = "Thank you for your feedback. We're always working to improve our services."
            else:
                message = "Thank you for your feedback. We're sorry your experience wasn't better, and we'll work to improve."
                
            background_tasks.add_task(
                teams_adapter.send_message,
                feedback.service_url,
                feedback.conversation_id,
                message
            )
        
        return {"status": "success", "message": "Enhanced feedback recorded"}
        
    except Exception as e:
        logger.error(f"Error processing enhanced feedback: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process feedback: {str(e)}")

@router.post("/card-action")
async def handle_card_action(request: Request):
    """Handle adaptive card actions and submissions for feedback."""
    try:
        # Parse the request body from Teams
        data = await request.json()
        logger.info(f"Received card action: {data}")
        
        # Extract key information
        service_url = data.get("serviceUrl")
        conversation_id = None
        if "conversation" in data:
            conversation_id = data["conversation"].get("id")
        
        user_id = None
        if "from" in data:
            user_id = data["from"].get("id")
        
        # Process based on the action type
        value = data.get("value", {})
        logger.debug(f"Card action value: {value}")
        action_type = value.get("action")
        
        if not service_url or not conversation_id or not user_id:
            logger.error("Missing required fields in card action")
            return {"status": "error", "message": "Missing required fields"}
            
        if action_type == "submit_rating":
            # User clicked on a star - update the card visually to reflect selection
            rating = value.get("rating")
            if rating and isinstance(rating, str) and rating.isdigit():
                rating = int(rating)
            if rating and isinstance(rating, int) and 1 <= rating <= 5:
                logger.info(f"User {user_id} selected rating: {rating}")

                # Build updated card with selected stars highlighted
                updated_card = create_feedback_card(selected_rating=rating)

                # Send updated card (this replaces original visually)
                await teams_adapter.send_card(service_url, conversation_id, updated_card)

                # Acknowledge selection to avoid generic toast feeling impersonal
                await teams_adapter.send_message(
                    service_url,
                    conversation_id,
                    "Great! You selected a {}-star rating. Feel free to add a comment or press \"Provide Feedback\" to submit.".format(rating)
                )

                return {"status": "ok"}
            
        elif action_type == "dismiss_feedback":
            # User clicked "No Later"
            await teams_adapter.send_message(
                service_url, 
                conversation_id, 
                "No problem! Feel free to provide feedback another time."
            )
            return {"status": "ok"}
                
        elif action_type == "submit_feedback":
            # For direct star selection + submission
            rating = value.get("rating")
            
            # Convert rating to int if it's a numeric string
            if isinstance(rating, str) and rating.isdigit():
                rating = int(rating)
            
            # If no rating selected, assume neutral (3)
            if not rating or not isinstance(rating, int) or rating == 0:
                rating = 3  # Neutral default
            
            # Get comments - check both new and old field names
            comments = value.get("comment", value.get("comments", ""))
            
            logger.debug(f"Processing feedback submission - rating: {rating}, comments: '{comments}'")
            
            try:
                # Record the feedback
                logger.info(f"Recording feedback from user {user_id}: rating={rating}, comments='{comments}'")
                feedback_service.record_feedback(user_id, rating, comments)
                
                # Send thank you message based on rating
                if rating >= 4:
                    # Positive response for high ratings
                    await teams_adapter.send_message(
                        service_url, 
                        conversation_id, 
                        "Thank you for your positive feedback! We're glad you had a good experience with our HR Assistant."
                    )
                elif rating <= 2:
                    # Apologetic response for low ratings
                    await teams_adapter.send_message(
                        service_url, 
                        conversation_id, 
                        "Thank you for your feedback. We're sorry your experience wasn't better, and we'll work to improve."
                    )
                else:
                    # Neutral response for middle ratings
                    await teams_adapter.send_message(
                        service_url, 
                        conversation_id, 
                        "Thank you for your feedback. We're always working to improve our services."
                    )
                return {"status": "ok"}
                
            except Exception as e:
                logger.error(f"Error recording feedback: {str(e)}")
                await teams_adapter.send_message(
                    service_url, 
                    conversation_id, 
                    "There was an error processing your feedback. Please try again."
                )
                return {"status": "error", "message": str(e)}
                
        # For any other card actions or fallback
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing card action: {str(e)}")
        return {"status": "error", "message": str(e)} 
    


