from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
import time
import logging
from hrbot.services.processor import ChatProcessor
from hrbot.services.message_service import MessageService
from hrbot.services.session_tracker import session_tracker
from hrbot.utils.di import get_content_classification_service
from hrbot.config.settings import settings
from hrbot.core.adapters.llm_gemini import LLMServiceAdapter
from hrbot.services.gemini_service import GeminiService
from hrbot.config.app_config import get_instance_manager, get_current_app_config

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
    conversation_flow: str
    confidence: float
    processing_time: float
    app_instance: str
    bot_name: str

# In-memory conversation storage for debug sessions
debug_memories = {}

async def get_or_create_debug_memory(user_id: str) -> dict:
    """Get or create memory for debug user."""
    if user_id not in debug_memories:
        debug_memories[user_id] = {"messages": []}
    return debug_memories[user_id]

@router.post("/chat", response_model=DebugChatResponse)
async def debug_chat(req: DebugChatRequest):
    """Debug endpoint that returns actual AI response for testing."""
    import time
    start_time = time.time()
    
    # Determine app instance and config
    app_instance = req.app_instance or None
    if app_instance:
        app_config = get_instance_manager().get_instance(app_instance)
        if not app_config:
            app_config = get_current_app_config()
    else:
        app_config = get_current_app_config()
    bot_name = app_config.name
    
    try:
        # Create a session ID for this debug conversation
        session_id = session_tracker.get(req.user_id)
        
        # Get conversation context
        memory = await get_or_create_debug_memory(req.user_id)
        conversation_context = None
        if memory["messages"]:
            recent_messages = memory["messages"][-4:]
            conversation_context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_messages])
        
        # Initialize services
        message_service = MessageService()
        chat_processor = ChatProcessor()
        classification_service = get_content_classification_service()
        
        # Analyze conversation flow
        analysis = await classification_service.analyze_conversation_flow(
            user_message=req.text,
            conversation_context=conversation_context,
            response_type="standard"
        )
        
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
        
        # Get AI response
        result = await chat_processor.process_message(
            req.text,
            chat_history=[m["content"] for m in memory["messages"]],
            user_id=req.user_id
        )
        
        processing_time = time.time() - start_time
        
        if result.is_success():
            bot_response = result.unwrap()["response"].strip()
            
            # Save to memory for context
            memory["messages"].append({"role": "user", "content": req.text})
            memory["messages"].append({"role": "ai", "content": bot_response})
            
            # Save bot response to database
            await message_service.add_message(
                bot_name=bot_name,
                env="development", 
                channel="debug",
                user_id=req.user_id,
                session_id=session_id,
                role="bot",
                text=bot_response,
                intent=classification_service.get_message_intent(analysis),
                reply_to_id=user_msg_id,
            )
            
            return DebugChatResponse(
                user_message=req.text,
                bot_response=bot_response,
                conversation_flow=analysis.flow_type.value,
                confidence=analysis.confidence,
                processing_time=round(processing_time, 2),
                app_instance=app_config.instance_id,
                bot_name=bot_name
            )
        else:
            # Even on error, save to memory and database
            error_response = "Sorry, I encountered an error processing your request."
            memory["messages"].append({"role": "user", "content": req.text})
            memory["messages"].append({"role": "ai", "content": error_response})
            
            await message_service.add_message(
                bot_name=bot_name,
                env="development",
                channel="debug", 
                user_id=req.user_id,
                session_id=session_id,
                role="bot",
                text=error_response,
                intent="error",
                reply_to_id=user_msg_id,
            )
            
            return DebugChatResponse(
                user_message=req.text,
                bot_response=error_response,
                conversation_flow="error",
                confidence=0.0,
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
            conversation_flow="error",
            confidence=0.0,
            processing_time=round(processing_time, 2),
            app_instance=app_config.instance_id,
            bot_name=bot_name
        )

@router.post("/clear-memory")
async def clear_debug_memory(user_id: str):
    """Clear debug conversation memory for a user."""
    if user_id in debug_memories:
        del debug_memories[user_id]
    return {"status": "success", "message": f"Cleared memory for user {user_id}"} 