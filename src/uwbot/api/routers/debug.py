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
    contact_id: int = Field(ge=1, le=99_999_999_999)
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
    external_validation_client = Depends(get_contact_validation_uc)
):
    """Debug endpoint for testing external validation API."""
    start_time = time.time()
    
    # Call external validation API
    validation_result = await external_validation_client.validate_combined(
        contact_id=req.contact_id,
        user_id=req.user_id,
        user_name="debug-user"
    )
    
    if validation_result.is_success():
        contact_info = validation_result.value
        response = contact_info.get('message', 'No response available')
        success = True
    else:
        contact_info = None
        response = f"Error: {validation_result.error}"
        success = False
    
    processing_time = time.time() - start_time
    
    return ContactQueryResponse(
        contact_id=req.contact_id,
        contact_info=contact_info,
        response=response,
        success=success,
        processing_time=round(processing_time, 2)
    )

@router.post("/chat", response_model=DebugChatResponse)
async def debug_chat(
    req: DebugChatRequest,
    external_validation_client = Depends(get_contact_validation_uc)
):
    """Debug endpoint that returns external validation check response for testing."""
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
        contact_id = extract_contact_id_from_message(req.text)
        
        processing_time = time.time() - start_time
        
        if contact_id:
            # Call external validation API
            validation_result = await external_validation_client.validate_combined(
                contact_id=contact_id,
                user_id=req.user_id,
                user_name="debug-user"
            )
            
            if validation_result.is_success():
                bot_response = validation_result.value.get('message', 'No response available')
                intent_type = "validation"
            else:
                # Handle validation error
                error_msg = validation_result.error
                if "Invalid contact ID" in error_msg:
                    from uwbot.utils.validation_responses import format_invalid_contact_id_response
                    bot_response = format_invalid_contact_id_response(contact_id)
                    intent_type = "error"
                else:
                    from uwbot.utils.validation_responses import format_error_response
                    bot_response = format_error_response(contact_id, f"Error validating contact {contact_id}: {error_msg}", "validation")
                    intent_type = "error"
            
            # Save bot response to database
            await message_service.add_message(
                bot_name=bot_name,
                env="development", 
                channel="debug",
                user_id=req.user_id,
                session_id=session_id,
                role="bot",
                text=bot_response,
                intent=intent_type,
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

def extract_contact_id_from_message(message: str) -> Optional[int]:
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
                if 1 <= contact_id <= 99_999_999_999:
                    return contact_id
                else:
                    logger.warning(f"Extracted invalid contact ID from message: {contact_id}")
                    return None
            except (ValueError, IndexError):
                continue
    
    return None

 