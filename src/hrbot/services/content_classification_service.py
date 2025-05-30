"""
Content Classification Service for intelligent conversation flow analysis.

This service analyzes user messages to determine when conversation-ending feedback
should be triggered, using LLM intelligence rather than hardcoded patterns.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
from hrbot.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)

class ConversationFlow(Enum):
    """Conversation flow classifications."""
    CONTINUE_NORMAL = "continue_normal"          # Normal HR conversation continues
    CONTINUE_REDIRECTED = "continue_redirected"  # Off-topic but redirected to HR
    END_NATURAL = "end_natural"                  # Natural conversation ending
    END_SAFETY_INTERVENTION = "end_safety"       # Safety concern requiring intervention
    END_VIOLATION = "end_violation"              # Policy violation requiring guidance

@dataclass
class ConversationAnalysis:
    """Result of conversation flow analysis."""
    flow_type: ConversationFlow
    confidence: float
    reason: str
    requires_feedback: bool
    feedback_message: Optional[str] = None
    should_escalate: bool = False

class ContentClassificationService:
    """
    Intelligent conversation flow analysis using LLM.
    
    Determines when conversations should end and appropriate feedback should be sent,
    using contextual understanding rather than keyword matching.
    """
    
    def __init__(self, llm_service: Optional[GeminiService] = None):
        """Initialize the content classification service."""
        self.llm_service = llm_service or GeminiService()
        
    async def analyze_conversation_flow(
        self, 
        user_message: str, 
        conversation_context: Optional[str] = None
    ) -> ConversationAnalysis:
        """
        Analyze if the user's message indicates the conversation should end
        and if feedback should be collected.
        
        Args:
            user_message: The user's current message
            conversation_context: Previous conversation context
            
        Returns:
            ConversationAnalysis with flow determination
        """
        try:
            # Build analysis prompt
            prompt = self._build_flow_analysis_prompt(user_message, conversation_context)
            
            # Get LLM analysis
            result = await self.llm_service.analyze_messages([prompt])
            
            if result.is_success():
                response = result.unwrap()["response"].strip()
                return self._parse_flow_analysis(response, user_message)
            else:
                logger.warning("Flow analysis failed, using safe defaults")
                return self._get_safe_default_analysis()
                
        except Exception as e:
            logger.error(f"Error in conversation flow analysis: {e}")
            return self._get_safe_default_analysis()
    
    def _build_flow_analysis_prompt(self, user_message: str, conversation_context: Optional[str] = None) -> str:
        """Build a focused prompt for conversation flow analysis."""
        
        context_section = ""
        if conversation_context:
            context_section = f"""
CONVERSATION CONTEXT:
{conversation_context}

"""
        
        prompt = f"""You are an expert conversation flow analyst for an HR Assistant. Analyze whether this user message indicates the conversation should continue or end, and whether feedback should be collected.

{context_section}USER MESSAGE: "{user_message}"

ANALYSIS GUIDELINES:

**CONTINUE_NORMAL** - HR-related questions that keep conversation going
- Examples: "What's my leave policy?", "How do I submit a request?", "Who is my manager?"

**CONTINUE_REDIRECTED** - Off-topic questions that get redirected but conversation continues  
- Examples: "Do you know about naruto?", "What's the weather?", "Tell me a joke"
- These get redirected to HR topics but don't end the conversation

**END_NATURAL** - Clear signals user wants to end conversation
- Examples: "thanks", "bye", "that's all I needed", "goodbye", "nothing else"
- User is satisfied and ready to leave

**END_SAFETY_INTERVENTION** - Safety concerns requiring immediate intervention
- Examples: "I want to hurt myself", "I want to kill myself", "I hate everyone here"
- Conversation ends with safety resources and escalation

**END_VIOLATION** - Inappropriate content requiring policy guidance
- Examples: Harassment, discrimination, inappropriate workplace language
- Conversation ends with policy reminder and HR referral

KEY DECISION FACTORS:
1. **Intent to End**: Does user explicitly want to stop the conversation?
2. **Safety Risk**: Does message indicate self-harm, violence, or crisis?
3. **Policy Violation**: Does message violate workplace communication standards?
4. **Topic Completion**: Has user gotten what they needed and shown satisfaction?

FEEDBACK COLLECTION RULES:
- Send feedback when conversation is ending (END_* categories)
- Don't send feedback for ongoing conversations (CONTINUE_* categories)
- Always send feedback for safety/violation scenarios for improvement

RESPONSE FORMAT:
Flow: [CATEGORY]
Confidence: [0.0-1.0]
Reason: [Brief explanation]
Requires_Feedback: [true/false]
Should_Escalate: [true/false]
Feedback_Message: [Optional message if special feedback needed]

Example:
Flow: END_SAFETY_INTERVENTION
Confidence: 0.95
Reason: Message contains explicit self-harm language requiring immediate safety intervention
Requires_Feedback: true
Should_Escalate: true
Feedback_Message: Safety concern noted for follow-up

Now analyze the user message:"""
        
        return prompt
    
    def _parse_flow_analysis(self, response: str, user_message: str) -> ConversationAnalysis:
        """Parse the LLM flow analysis response."""
        try:
            lines = response.strip().split('\n')
            result = {}
            
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    result[key.strip().lower()] = value.strip()
            
            # Extract analysis details
            flow_str = result.get('flow', 'CONTINUE_NORMAL').upper()
            confidence = float(result.get('confidence', '0.5'))
            reason = result.get('reason', 'Flow analyzed using default analysis')
            requires_feedback = result.get('requires_feedback', 'false').lower() == 'true'
            should_escalate = result.get('should_escalate', 'false').lower() == 'true'
            feedback_message = result.get('feedback_message', None)
            
            # Map to enum
            try:
                flow_type = ConversationFlow(flow_str.lower())
            except ValueError:
                flow_type = ConversationFlow.CONTINUE_NORMAL
            
            logger.debug(f"Flow analysis for '{user_message[:30]}...': {flow_type.value} (confidence: {confidence})")
            
            return ConversationAnalysis(
                flow_type=flow_type,
                confidence=confidence,
                reason=reason,
                requires_feedback=requires_feedback,
                feedback_message=feedback_message,
                should_escalate=should_escalate
            )
            
        except Exception as e:
            logger.error(f"Error parsing flow analysis response: {e}")
            return self._get_safe_default_analysis()
    
    def _get_safe_default_analysis(self) -> ConversationAnalysis:
        """Return a safe default analysis when parsing fails."""
        return ConversationAnalysis(
            flow_type=ConversationFlow.CONTINUE_NORMAL,
            confidence=0.5,
            reason="Default analysis due to parsing failure",
            requires_feedback=False
        )
    
    def get_response_message(self, analysis: ConversationAnalysis) -> Optional[str]:
        """Get an appropriate response message based on flow analysis."""
        
        if analysis.flow_type == ConversationFlow.END_SAFETY_INTERVENTION:
            return (
                "I'm concerned about your message. If you're experiencing thoughts of self-harm, "
                "please reach out to a mental health professional or crisis hotline immediately. "
                "For workplace support, you can contact our HR team: https://hrsupport.usclarity.com/support/home"
            )
        
        elif analysis.flow_type == ConversationFlow.END_VIOLATION:
            return (
                "I notice your message contains content that may not be appropriate for our workplace environment. "
                "If you have work-related concerns, please submit them through our HR Support portal: "
                "https://hrsupport.usclarity.com/support/home"
            )
        
        elif analysis.flow_type == ConversationFlow.CONTINUE_REDIRECTED:
            return (
                "I'm designed to help with HR and workplace-related questions. "
                "For assistance with work matters, feel free to ask! "
                "Is there anything HR-related I can help you with?"
            )
        
        elif analysis.flow_type == ConversationFlow.END_NATURAL:
            return "Thank you for using our HR Assistant!"
        
        else:
            return None  # Use standard HR assistant response
    
    def should_end_conversation(self, analysis: ConversationAnalysis) -> bool:
        """Determine if conversation should end based on analysis."""
        return analysis.flow_type.value.startswith('end_')
    
    def should_send_feedback(self, analysis: ConversationAnalysis) -> bool:
        """Determine if feedback should be collected."""
        return analysis.requires_feedback and self.should_end_conversation(analysis)
    
    def get_feedback_type(self, analysis: ConversationAnalysis) -> str:
        """Get the type of feedback to collect."""
        if analysis.flow_type == ConversationFlow.END_SAFETY_INTERVENTION:
            return "safety"
        elif analysis.flow_type == ConversationFlow.END_VIOLATION:
            return "violation"
        elif analysis.flow_type == ConversationFlow.END_NATURAL:
            return "standard"
        else:
            return "standard"
    
    def get_message_intent(self, analysis: ConversationAnalysis) -> str:
        """Get the intent to record for message logging."""
        if analysis.flow_type == ConversationFlow.END_SAFETY_INTERVENTION:
            return "safety_concern"
        elif analysis.flow_type == ConversationFlow.END_VIOLATION:
            return "violation"
        elif analysis.flow_type == ConversationFlow.END_NATURAL:
            return "END"
        elif analysis.flow_type == ConversationFlow.CONTINUE_REDIRECTED:
            return "off_topic"
        else:
            return "CONTINUE" 