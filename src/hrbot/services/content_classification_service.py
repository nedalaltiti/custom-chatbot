"""
Content Classification Service for intelligent conversation flow analysis.

Enhanced with smart feedback timing and NOI response handling.
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
    CONTINUE_INFORMATIONAL = "continue_informational"  # Informational response (NOI, policies) - no feedback
    CONTINUE_REDIRECTED = "continue_redirected"  # Off-topic but redirected to HR
    END_NATURAL = "end_natural"                  # Natural conversation ending
    END_SATISFIED = "end_satisfied"              # User got what they needed
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
    feedback_timing: str = "immediate"  # "immediate", "delayed", "none"

class ContentClassificationService:
    """
    Intelligent conversation flow analysis using LLM with smart feedback timing.
    """
    
    def __init__(self, llm_service: Optional[GeminiService] = None):
        """Initialize the content classification service."""
        self.llm_service = llm_service or GeminiService()
        
    async def analyze_conversation_flow(
        self, 
        user_message: str, 
        conversation_context: Optional[str] = None,
        response_type: Optional[str] = None  # "noi", "policy", "standard", etc.
    ) -> ConversationAnalysis:
        """
        Analyze conversation flow with enhanced NOI and informational response handling.
        
        Args:
            user_message: The user's current message
            conversation_context: Previous conversation context
            response_type: Type of response being given (helps with classification)
            
        Returns:
            ConversationAnalysis with smart feedback determination
        """
        try:
            # Special handling for NOI and informational responses
            if response_type == "noi":
                return ConversationAnalysis(
                    flow_type=ConversationFlow.CONTINUE_INFORMATIONAL,
                    confidence=0.95,
                    reason="NOI response - informational, no feedback needed",
                    requires_feedback=False,
                    feedback_timing="none"
                )
            
            # Build enhanced analysis prompt
            prompt = self._build_enhanced_flow_analysis_prompt(user_message, conversation_context)
            
            # Get LLM analysis
            result = await self.llm_service.analyze_messages([prompt])
            
            if result.is_success():
                response = result.unwrap()["response"].strip()
                return self._parse_enhanced_flow_analysis(response, user_message)
            else:
                logger.warning("Flow analysis failed, using safe defaults")
                return self._get_safe_default_analysis()
                
        except Exception as e:
            logger.error(f"Error in conversation flow analysis: {e}")
            return self._get_safe_default_analysis()
    
    def _build_enhanced_flow_analysis_prompt(self, user_message: str, conversation_context: Optional[str] = None) -> str:
        """Build an enhanced prompt for smart conversation flow analysis."""
        
        context_section = ""
        if conversation_context:
            context_section = f"""
CONVERSATION CONTEXT:
{conversation_context}

"""
        
        prompt = f"""You are an expert conversation flow analyst for an HR Assistant. Analyze this user message to determine conversation flow and smart feedback timing.

{context_section}USER MESSAGE: "{user_message}"

FLOW CATEGORIES:

**CONTINUE_NORMAL** - Standard HR questions that continue conversation
- Examples: "What's my leave policy?", "How do I submit a request?", "Who is my manager?"
- Single words that could be topics: "noi", "benefits", "policy", "vacation", "insurance"
- HR abbreviations or terms: "NOI", "PTO", "401k", "FMLA", etc.
- Feedback: Delayed (10-15 minutes of inactivity)

**CONTINUE_INFORMATIONAL** - User received informational content (policies, procedures, NOI responses)
- Examples: After explaining policies, providing contact info, giving procedural guidance
- Feedback: None immediately (user likely processing information)

**CONTINUE_REDIRECTED** - Off-topic questions redirected to HR
- Examples: "What's the weather?", "Tell me about sports", "Random non-work question"
- Feedback: None (conversation redirected, not ended)

**END_NATURAL** - Clear conversation ending signals
- Examples: "thanks bye", "goodbye", "that's all I needed", "I'm done", "nothing else"
- Must be clear and unambiguous endings, not potential topics
- Feedback: Immediate (user is satisfied and leaving)

**END_SATISFIED** - User explicitly satisfied with response
- Examples: "that helps, thanks", "exactly what I needed", "perfect, goodbye"
- Must include clear satisfaction + ending signals
- Feedback: Immediate (positive ending)

**END_SAFETY_INTERVENTION** - Safety concerns (NEVER classify single words as safety issues)
- Examples: Clear statements about self-harm, violence threats, crisis situations
- Must be explicit and unambiguous, not just containing keywords
- Feedback: Immediate (for monitoring and improvement)

**END_VIOLATION** - Policy violations
- Examples: Harassment, inappropriate content, discrimination
- Feedback: Immediate (for tracking)

CRITICAL CLASSIFICATION RULES:

1. **SINGLE WORDS OR SHORT PHRASES**: Almost always CONTINUE_NORMAL
   - "noi" → CONTINUE_NORMAL (could be asking about Notice of Investigation)
   - "benefits" → CONTINUE_NORMAL (asking about benefits)
   - "policy" → CONTINUE_NORMAL (asking about policies)
   - "quit" → CONTINUE_NORMAL (could be asking about resignation process)
   - "kill myself" → CONTINUE_NORMAL (could be expressing frustration, asking about workload)

2. **WHEN TO END**: Only when user CLEARLY and EXPLICITLY signals completion
   - "nothing else" + clear context they're done
   - "bye" or "goodbye" 
   - "that's all, thanks"
   - "I'm all set"

3. **CONSERVATIVE APPROACH**: When in doubt, choose CONTINUE
   - Better to help someone unnecessarily than miss someone who needs help
   - Ambiguous messages should always continue

4. **CONTEXT MATTERS**: Consider if this could be:
   - A new question/topic
   - An abbreviation (NOI, PTO, etc.)
   - An expression of frustration that needs support
   - A request for information

SMART FEEDBACK TIMING RULES:
- **IMMEDIATE**: Only for crystal clear endings with satisfaction signals
- **DELAYED**: Standard help provided, user might have follow-ups
- **NONE**: Informational responses, redirects, ongoing conversations

RESPONSE FORMAT:
Flow: [CATEGORY]
Confidence: [0.0-1.0]
Reason: [Brief explanation]
Requires_Feedback: [true/false]
Feedback_Timing: [immediate/delayed/none]
Should_Escalate: [true/false]

Example for "noi":
Flow: CONTINUE_NORMAL
Confidence: 0.90
Reason: Single word that could be asking about Notice of Investigation - continue conversation
Requires_Feedback: false
Feedback_Timing: delayed
Should_Escalate: false

Analyze the message:"""
        
        return prompt
    
    def _parse_enhanced_flow_analysis(self, response: str, user_message: str) -> ConversationAnalysis:
        """Parse the enhanced LLM flow analysis response."""
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
            reason = result.get('reason', 'Flow analyzed using enhanced analysis')
            requires_feedback = result.get('requires_feedback', 'false').lower() == 'true'
            feedback_timing = result.get('feedback_timing', 'delayed').lower()
            should_escalate = result.get('should_escalate', 'false').lower() == 'true'
            
            # Map to enum
            try:
                flow_type = ConversationFlow(flow_str.lower())
            except ValueError:
                flow_type = ConversationFlow.CONTINUE_NORMAL
            
            logger.debug(f"Enhanced flow analysis for '{user_message[:30]}...': {flow_type.value} (confidence: {confidence}, timing: {feedback_timing})")
            
            return ConversationAnalysis(
                flow_type=flow_type,
                confidence=confidence,
                reason=reason,
                requires_feedback=requires_feedback,
                feedback_timing=feedback_timing,
                should_escalate=should_escalate
            )
            
        except Exception as e:
            logger.error(f"Error parsing enhanced flow analysis response: {e}")
            return self._get_safe_default_analysis()
    
    def _get_safe_default_analysis(self) -> ConversationAnalysis:
        """Return a safe default analysis when parsing fails."""
        return ConversationAnalysis(
            flow_type=ConversationFlow.CONTINUE_NORMAL,
            confidence=0.5,
            reason="Default analysis due to parsing failure",
            requires_feedback=False,
            feedback_timing="delayed"
        )
    
    def get_response_message(self, analysis: ConversationAnalysis) -> Optional[str]:
        """Get appropriate response message based on flow analysis."""
        
        if analysis.flow_type == ConversationFlow.END_SAFETY_INTERVENTION:
            return (
                "I'm concerned about your message. If you're experiencing thoughts of self-harm, "
                "please reach out to a mental health professional or crisis hotline immediately. "
                "For workplace support, you can contact our HR team: https://hrsupport.usclarity.com/support/home"
            )
        
        elif analysis.flow_type == ConversationFlow.END_VIOLATION:
            return (
                "I notice your message contains content that may not be appropriate for our workplace environment. "
                "For work-related concerns, please submit them through our HR Support portal: "
                "https://hrsupport.usclarity.com/support/home"
            )
        
        elif analysis.flow_type == ConversationFlow.CONTINUE_REDIRECTED:
            return (
                "I'm here to help with HR and workplace-related questions. "
                "Is there anything work-related I can assist you with?"
            )
        
        elif analysis.flow_type == ConversationFlow.END_NATURAL:
            return "Thank you for using our HR Assistant! Have a great day!"
        
        elif analysis.flow_type == ConversationFlow.END_SATISFIED:
            return "Glad I could help! Feel free to reach out anytime."
        
        else:
            return None  # Use standard HR assistant response
    
    def should_end_conversation(self, analysis: ConversationAnalysis) -> bool:
        """Return *True* only when we are highly confident the user is ending.

        Rules
        -----
        • **END_NATURAL / END_SATISFIED** ⇒ end only when confidence ≥ 0.8
        • **END_VIOLATION** ⇒ we *never* auto-end; we give guidance but keep
          the thread open in case the user wants to clarify.
        • Safety-intervention and informational/redirect cases never end.
        """

        if analysis.flow_type in {ConversationFlow.END_NATURAL, ConversationFlow.END_SATISFIED}:
            return analysis.confidence >= 0.8

        # keep session for all other cases (safety, violation, informational…)
        return False
    
    def should_send_feedback(self, analysis: ConversationAnalysis) -> bool:
        """Collect immediate feedback only on **high-confidence** clean endings."""

        if not (analysis.requires_feedback and analysis.feedback_timing == "immediate"):
            return False

        # Only when we truly end the conversation
        return self.should_end_conversation(analysis)
    
    def should_schedule_delayed_feedback(self, analysis: ConversationAnalysis) -> bool:
        """Determine if feedback should be scheduled for later."""
        return (analysis.flow_type == ConversationFlow.CONTINUE_NORMAL and
                analysis.feedback_timing == "delayed")
    
    def get_feedback_delay_minutes(self, analysis: ConversationAnalysis) -> int:
        """Get the delay in minutes for scheduled feedback."""
        if analysis.feedback_timing == "delayed":
            return 10  # 10 minutes of inactivity
        return 0
    
    def get_feedback_type(self, analysis: ConversationAnalysis) -> str:
        """Get the type of feedback to collect."""
        if analysis.flow_type == ConversationFlow.END_SAFETY_INTERVENTION:
            return "safety"
        elif analysis.flow_type == ConversationFlow.END_VIOLATION:
            return "violation"
        elif analysis.flow_type in [ConversationFlow.END_NATURAL, ConversationFlow.END_SATISFIED]:
            return "standard"
        else:
            return "standard"
    
    def get_message_intent(self, analysis: ConversationAnalysis) -> str:
        """Get the intent to record for message logging."""
        if analysis.flow_type == ConversationFlow.END_SAFETY_INTERVENTION:
            return "safety_concern"
        elif analysis.flow_type == ConversationFlow.END_VIOLATION:
            return "violation"
        elif analysis.flow_type in [ConversationFlow.END_NATURAL, ConversationFlow.END_SATISFIED]:
            return "END"
        elif analysis.flow_type == ConversationFlow.CONTINUE_REDIRECTED:
            return "off_topic"
        elif analysis.flow_type == ConversationFlow.CONTINUE_INFORMATIONAL:
            return "informational"
        else:
            return "CONTINUE"