from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional
import time
import logging
from datetime import datetime
from uwbot.services.message_service import MessageService
from uwbot.services.session_tracker import session_tracker
from uwbot.utils.di import get_contact_validation_uc
from uwbot.config.settings import settings
from uwbot.config.app_config import get_app_config

logger = logging.getLogger(__name__)
router = APIRouter()

# Debug endpoint models
class DebugChatRequest(BaseModel):
    text: str
    user_id: str = "debug-user"
    app_instance: Optional[str] = None  # Optional app instance (jo/us)

class DebugChatResponse(BaseModel):
    user_message: str
    bot_response: str
    processing_time: float
    app_instance: str
    bot_name: str

class ContactQueryRequest(BaseModel):
    contact_id: int = Field(ge=1, le=999_999_999)
    user_id: str = "debug-user"

class ContactQueryResponse(BaseModel):
    contact_id: int
    contact_info: Optional[dict] = None
    response: str
    success: bool
    processing_time: float

@router.post("/contact", response_model=ContactQueryResponse)
async def debug_contact_query(
    req: ContactQueryRequest,
    contact_service = Depends(get_contact_validation_uc)
):
    """Debug endpoint for testing hardship validation data check."""
    start_time = time.time()
    
    # Check hardship validation data
    hardship_result = await contact_service.analyze_contact_hardship(req.contact_id)
    hardship_response = contact_service.format_contact_response(hardship_result)
    
    processing_time = time.time() - start_time
    
    return ContactQueryResponse(
        contact_id=req.contact_id,
        contact_info=hardship_result,
        response=hardship_response,
        success=hardship_result is not None,
        processing_time=round(processing_time, 2)
    )

@router.post("/chat", response_model=DebugChatResponse)
async def debug_chat(
    req: DebugChatRequest,
    contact_service = Depends(get_contact_validation_uc)
):
    """Debug endpoint that returns hardship validation check response for testing."""
    import time
    start_time = time.time()
    
    # Determine app instance and config
    app_instance = req.app_instance or None
    if app_instance:
        app_config = get_app_config()
    else:
        app_config = get_app_config()
    bot_name = app_config.name
    
    try:
        # Create a session ID for this debug conversation
        session_id = session_tracker.get(req.user_id)
        
        # Initialize services
        message_service = MessageService()
        
        # Save user message to database
        user_msg_id = await message_service.add_message(
            bot_name=bot_name,
            env="development",
            channel="debug",  # Using 'debug' channel to distinguish from teams
            user_id=req.user_id,
            session_id=session_id,
            role="user",
            text=req.text,
            intent=None,
            reply_to_id=None,
        )
        
        # Check if message contains contact ID
        contact_id = contact_service.extract_contact_id_from_message(req.text)
        
        processing_time = time.time() - start_time
        
        if contact_id:
            # Check hardship validation data
            result = await contact_service.analyze_contact_hardship(contact_id)
            bot_response = contact_service.format_contact_response(result)
            
            # Save bot response to database
            await message_service.add_message(
                bot_name=bot_name,
                env="development", 
                channel="debug",
                user_id=req.user_id,
                session_id=session_id,
                role="bot",
                text=bot_response,
                intent="validation",
                reply_to_id=user_msg_id,
            )
        else:
            # No contact ID found
            from uwbot.utils.validation_responses import format_debug_help_message
            bot_response = format_debug_help_message()
            
            # Save bot response to database
            await message_service.add_message(
                bot_name=bot_name,
                env="development",
                channel="debug", 
                user_id=req.user_id,
                session_id=session_id,
                role="bot",
                text=bot_response,
                intent="help",
                reply_to_id=user_msg_id,
            )
        
        return DebugChatResponse(
            user_message=req.text,
            bot_response=bot_response,
            processing_time=round(processing_time, 2),
            app_instance=app_config.instance_id,
            bot_name=bot_name
        )
            
    except Exception as e:
        logger.error(f"Debug chat error: {e}")
        processing_time = time.time() - start_time
        return DebugChatResponse(
            user_message=req.text,
            bot_response=f"Error: {str(e)}",
            processing_time=round(processing_time, 2),
            app_instance=app_config.instance_id,
            bot_name=bot_name
        )

 