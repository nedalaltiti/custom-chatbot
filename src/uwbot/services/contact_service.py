"""
Contact Service for uwbot

Handles database operations for the public.contacts table.
Allows users to query contact information by ID.
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from uwbot.db.models import Contact, ContactUserField
from uwbot.db.session import get_db_session_context
from uwbot.services.hardship_validation_service import HardshipValidationService, HardshipAnalysis
from uwbot.services.budget_validation_service import BudgetValidationService, BudgetAnalysis

logger = logging.getLogger(__name__)

class ContactService:
    """Service for managing contact information from the public.contacts table."""
    
    def __init__(self):
        self.hardship_service = HardshipValidationService()
        self.budget_service = BudgetValidationService()
    
    async def get_contact_by_id(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve hardship data and analyze its validity using the Gemini model.
        This replaces the previous contact lookup functionality.
        
        Args:
            contact_id: The ID of the contact to analyze
            
        Returns:
            Dictionary containing hardship analysis results or None if contact not found
        """
        try:
            # Get hardship data
            hardship_data = await self.get_contact_with_hardship_data(contact_id)
            
            if not hardship_data:
                logger.warning(f"No hardship data found for contact {contact_id}")
                return None
            
            # Check if there's any hardship data to analyze
            has_hardship_data = any([
                hardship_data.get('financial_hardship'),
                hardship_data.get('hardship_description')
            ])
            
            if not has_hardship_data:
                logger.info(f"No hardship data available for contact {contact_id}")
                return {
                    "contact_id": contact_id,
                    "analysis": {
                        "result": "no_pass",
                        "confidence": 0.0,
                        "reason": "No hardship data available for analysis"
                    },
                    "formatted_response": f"❌ Contact {contact_id} does not have hardship validation data. \nNo hardship information has been recorded for this contact."
                }
            
            # Analyze hardship validity
            analysis_result = await self.hardship_service.analyze_hardship_validity(hardship_data)
            
            if analysis_result.is_error():
                logger.error(f"Hardship analysis failed for contact {contact_id}: {analysis_result.error}")
                return {
                    "contact_id": contact_id,
                    "error": str(analysis_result.error),
                    "analysis": None,
                    "formatted_response": f"❌ Contact {contact_id} hardship validation error.\nUnable to analyze hardship data for contact {contact_id}. Please try again or contact support."
                }
            
            analysis = analysis_result.value
            formatted_response = self.hardship_service.format_hardship_response(analysis, hardship_data)
            
            return {
                "contact_id": contact_id,
                "hardship_data": hardship_data,
                "analysis": {
                    "result": analysis.result.value,
                    "confidence": analysis.confidence,
                    "reason": analysis.reason
                },
                "formatted_response": formatted_response
            }
            
        except Exception as e:
            logger.error(f"Error analyzing hardship for contact {contact_id}: {e}")
            return {
                "contact_id": contact_id,
                "error": str(e),
                "analysis": None,
                "formatted_response": f"❌ Contact {contact_id} hardship validation error.\nError analyzing hardship data for contact {contact_id}. Please try again."
            }
    
    async def get_contact_with_budget_data(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve contact information with budget data using the exact query structure provided.
        
        Args:
            contact_id: The ID of the contact to retrieve
            
        Returns:
            Dictionary containing contact and budget information or None if not found
        """
        try:
            async with get_db_session_context() as session:
                # Use the exact query structure you provided
                query = text("""
                    SELECT 
                        contacts.id,
                        contacts.acctid,
                        contacts.del,
                        contacts.iscoapp,
                        contacts.c_type,
                        contacts.leadstatus,
                        sum(case when field_type = 'I' THEN field_val ELSE 0 END) AS total_net_income,
                        sum(case when field_type = 'E' THEN field_val ELSE 0 END) AS total_expenses
                    FROM contacts
                    LEFT JOIN budget_data ON budget_data.contact_id = contacts.id
                    LEFT JOIN budget_fields ON budget_data.field_id = budget_fields.id
                    WHERE contacts.id = :contact_id
                        AND contacts.acctid = 2996
                        AND contacts.c_type = 20588
                        AND contacts.del = 'f'
                        AND contacts.iscoapp = 0
                        AND contacts.leadstatus = 134774
                    GROUP BY contacts.id, contacts.acctid, contacts.del, contacts.iscoapp, contacts.c_type, contacts.leadstatus
                """)
                
                result = await session.execute(query, {"contact_id": contact_id})
                row = result.fetchone()
                
                if row:
                    return {
                        "contact_id": row.id,
                        "acctid": row.acctid,
                        "del_flag": getattr(row, 'del'),
                        "iscoapp": row.iscoapp,
                        "c_type": row.c_type,
                        "leadstatus": row.leadstatus,
                        "total_net_income": float(row.total_net_income or 0),
                        "total_expenses": float(row.total_expenses or 0),
                    }
                else:
                    logger.info(f"Contact with ID {contact_id} not found or doesn't meet criteria")
                    return None
                    
        except SQLAlchemyError as e:
            logger.error(f"Database error while retrieving contact budget data {contact_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error while retrieving contact budget data {contact_id}: {e}")
            return None
    
    async def get_contact_budget_analysis(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve budget data and analyze if the client has a positive surplus.
        
        Args:
            contact_id: The ID of the contact to analyze
            
        Returns:
            Dictionary containing budget analysis results or None if contact not found
        """
        try:
            # Get budget data
            budget_data = await self.get_contact_with_budget_data(contact_id)
            
            if not budget_data:
                logger.warning(f"No budget data found for contact {contact_id}")
                return None
            
            # Check if there's any budget data to analyze
            has_budget_data = any([
                budget_data.get('total_net_income', 0) > 0,
                budget_data.get('total_expenses', 0) > 0
            ])
            
            if not has_budget_data:
                logger.info(f"No budget data available for contact {contact_id}")
                return {
                    "contact_id": contact_id,
                    "analysis": {
                        "result": "no_pass",
                        "confidence": 0.0,
                        "reason": "No budget data available for analysis"
                    },
                    "formatted_response": f"❌ Contact {contact_id} does not have budget validation data.\nNo budget information has been recorded for this contact."
                }
            
            # Analyze budget validity
            analysis_result = await self.budget_service.analyze_budget_validity(budget_data)
            
            if analysis_result.is_error():
                logger.error(f"Budget analysis failed for contact {contact_id}: {analysis_result.error}")
                return {
                    "contact_id": contact_id,
                    "error": str(analysis_result.error),
                    "analysis": None,
                    "formatted_response": f"❌ Contact {contact_id} budget validation error.\nUnable to analyze budget data for contact {contact_id}. Please try again or contact support."
                }
            
            analysis = analysis_result.value
            formatted_response = self.budget_service.format_budget_response(analysis, budget_data)
            
            return {
                "contact_id": contact_id,
                "budget_data": budget_data,
                "analysis": {
                    "result": analysis.result.value,
                    "confidence": analysis.confidence,
                    "reason": analysis.reason,
                    "total_net_income": analysis.total_net_income,
                    "total_expenses": analysis.total_expenses,
                    "surplus": analysis.surplus
                },
                "formatted_response": formatted_response
            }
            
        except Exception as e:
            logger.error(f"Error analyzing budget for contact {contact_id}: {e}")
            return {
                "contact_id": contact_id,
                "error": str(e),
                "analysis": None,
                "formatted_response": f"❌ Contact {contact_id} budget validation error.\nError analyzing budget data for contact {contact_id}. Please try again."
            }
    
    async def get_contact_with_hardship_data(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve contact information with hardship data using the exact query structure provided.
        
        Args:
            contact_id: The ID of the contact to retrieve
            
        Returns:
            Dictionary containing contact and hardship information or None if not found
        """
        try:
            async with get_db_session_context() as session:
                # Use the exact query structure you provided
                query = text("""
                    SELECT contacts.id,
                           contacts.acctid,
                           contacts.del as del_flag,
                           contacts.iscoapp,
                           contacts.c_type,
                           contacts.leadstatus,
                           financial_hardship.f_string as financial_hardship,
                           hardship_description.f_string as hardship_description
                    FROM contacts
                    LEFT JOIN contacts_userfields financial_hardship ON contacts.id = financial_hardship.contact_id AND financial_hardship.custom_id = 322256
                    LEFT JOIN contacts_userfields hardship_description ON contacts.id = hardship_description.contact_id AND hardship_description.custom_id = 322271
                    WHERE contacts.id = :contact_id
                """)
                
                result = await session.execute(query, {"contact_id": contact_id})
                row = result.fetchone()
                
                if row:
                    return {
                        "contact_id": row.id,
                        "acctid": row.acctid,
                        "del": row.del_flag,
                        "iscoapp": row.iscoapp,
                        "c_type": row.c_type,
                        "leadstatus": row.leadstatus,
                        "financial_hardship": row.financial_hardship,
                        "hardship_description": row.hardship_description,
                    }
                else:
                    logger.info(f"Contact with ID {contact_id} not found")
                    return None
                    
        except SQLAlchemyError as e:
            logger.error(f"Database error while retrieving contact hardship data {contact_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error while retrieving contact hardship data {contact_id}: {e}")
            return None
    
    async def get_contact_combined_validation(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve both hardship and budget data and analyze them together.
        
        Args:
            contact_id: The ID of the contact to analyze
            
        Returns:
            Dictionary containing combined hardship and budget analysis results
        """
        try:
            # Get both hardship and budget data
            hardship_data = await self.get_contact_with_hardship_data(contact_id)
            budget_data = await self.get_contact_with_budget_data(contact_id)
            
            # Check if we have any data at all
            has_hardship_data = hardship_data and any([
                hardship_data.get('financial_hardship'),
                hardship_data.get('hardship_description')
            ])
            
            has_budget_data = budget_data and any([
                budget_data.get('total_net_income', 0) > 0,
                budget_data.get('total_expenses', 0) > 0
            ])
            
            if not has_hardship_data and not has_budget_data:
                logger.warning(f"No hardship or budget data found for contact {contact_id}")
                return {
                    "contact_id": contact_id,
                    "hardship_analysis": None,
                    "budget_analysis": None,
                    "combined_result": "no_data",
                    "formatted_response": f"❌ Contact {contact_id} does not have hardship or budget validation data.\nNo validation information has been recorded for this contact."
                }
            
            # Analyze hardship if data exists
            hardship_analysis = None
            if has_hardship_data:
                hardship_result = await self.hardship_service.analyze_hardship_validity(hardship_data)
                if not hardship_result.is_error():
                    hardship_analysis = hardship_result.value
                else:
                    logger.error(f"Hardship analysis failed for contact {contact_id}: {hardship_result.error}")
            
            # Analyze budget if data exists
            budget_analysis = None
            if has_budget_data:
                budget_result = await self.budget_service.analyze_budget_validity(budget_data)
                if not budget_result.is_error():
                    budget_analysis = budget_result.value
                else:
                    logger.error(f"Budget analysis failed for contact {contact_id}: {budget_result.error}")
            
            # Determine combined result
            combined_result = self._determine_combined_result(hardship_analysis, budget_analysis)
            
            # Format combined response
            formatted_response = self._format_combined_response(
                contact_id, hardship_data, budget_data, hardship_analysis, budget_analysis, combined_result
            )
            
            return {
                "contact_id": contact_id,
                "hardship_data": hardship_data,
                "budget_data": budget_data,
                "hardship_analysis": {
                    "result": hardship_analysis.result.value if hardship_analysis else "no_data",
                    "confidence": hardship_analysis.confidence if hardship_analysis else 0.0,
                    "reason": hardship_analysis.reason if hardship_analysis else "No hardship data available"
                } if hardship_analysis else None,
                "budget_analysis": {
                    "result": budget_analysis.result.value if budget_analysis else "no_data",
                    "confidence": budget_analysis.confidence if budget_analysis else 0.0,
                    "reason": budget_analysis.reason if budget_analysis else "No budget data available",
                    "total_net_income": budget_analysis.total_net_income if budget_analysis else 0.0,
                    "total_expenses": budget_analysis.total_expenses if budget_analysis else 0.0,
                    "surplus": budget_analysis.surplus if budget_analysis else 0.0
                } if budget_analysis else None,
                "combined_result": combined_result,
                "formatted_response": formatted_response
            }
            
        except Exception as e:
            logger.error(f"Error performing combined validation for contact {contact_id}: {e}")
            return {
                "contact_id": contact_id,
                "error": str(e),
                "hardship_analysis": None,
                "budget_analysis": None,
                "combined_result": "error",
                "formatted_response": f"❌ Contact {contact_id} validation error.\nError analyzing validation data for contact {contact_id}. Please try again."
            }
    
    def _determine_combined_result(self, hardship_analysis, budget_analysis) -> str:
        """
        Determine the combined validation result based on both hardship and budget analyses.
        
        Returns:
            "pass" - Both validations pass or at least one passes with strong confidence
            "no_pass" - Both validations fail or insufficient data
            "mixed" - One passes, one fails (needs manual review)
            "no_data" - No data available for either validation
        """
        has_hardship = hardship_analysis is not None
        has_budget = budget_analysis is not None
        
        # If no data for either, return no_data
        if not has_hardship and not has_budget:
            return "no_data"
        
        # If only one type of data available, use that result
        if has_hardship and not has_budget:
            return hardship_analysis.result.value
        elif has_budget and not has_hardship:
            return budget_analysis.result.value
        
        # Both analyses available - determine combined result
        hardship_result = hardship_analysis.result.value
        budget_result = budget_analysis.result.value
        
        # If both pass, overall result is pass
        if hardship_result == "pass" and budget_result == "pass":
            return "pass"
        
        # If both fail, overall result is no_pass
        if hardship_result == "no_pass" and budget_result == "no_pass":
            return "no_pass"
        
        # Mixed results - one passes, one fails
        # For mixed results, we lean toward "pass" if the passing validation has high confidence
        if hardship_result == "pass" and hardship_analysis.confidence >= 0.8:
            return "pass"
        elif budget_result == "pass" and budget_analysis.confidence >= 0.8:
            return "pass"
        else:
            return "mixed"
    
    def _format_combined_response(
        self, 
        contact_id: int, 
        hardship_data: Dict[str, Any], 
        budget_data: Dict[str, Any],
        hardship_analysis, 
        budget_analysis, 
        combined_result: str
    ) -> str:
        """
        Format combined hardship and budget analysis into a comprehensive response.
        """
        response_parts = []
        
        # Header
        response_parts.append(f"# 📊 **Combined Validation Analysis for Contact {contact_id}**\n")
        
        # Overall result
        if combined_result == "pass":
            response_parts.append("## ✅ **OVERALL RESULT: PASS**\n")
        elif combined_result == "no_pass":
            response_parts.append("## ❌ **OVERALL RESULT: NO PASS**\n")
        elif combined_result == "mixed":
            response_parts.append("## ⚠️ **OVERALL RESULT: MIXED** (Requires Manual Review)\n")
        else:
            response_parts.append("## ❓ **OVERALL RESULT: NO DATA**\n")
        
        # Hardship Analysis Section
        response_parts.append("### 🔍 **Hardship Validation**\n")
        if hardship_analysis:
            hardship_status = "✅ PASS" if hardship_analysis.result.value == "pass" else "❌ NO PASS"
            response_parts.append(f"**Status:** {hardship_status}\n")
            response_parts.append(f"**Confidence:** {hardship_analysis.confidence * 100:.1f}%\n")
            response_parts.append(f"**Reason:** {hardship_analysis.reason}\n")
        else:
            response_parts.append("**Status:** No hardship data available\n")
        
        # Budget Analysis Section
        response_parts.append("### 💰 **Budget Validation**\n")
        if budget_analysis:
            budget_status = "✅ PASS" if budget_analysis.result.value == "pass" else "❌ NO PASS"
            response_parts.append(f"**Status:** {budget_status}\n")
            response_parts.append(f"**Confidence:** {budget_analysis.confidence * 100:.1f}%\n")
            response_parts.append(f"**Reason:** {budget_analysis.reason}\n")
            
            # Show budget data
            income_formatted = f"${budget_analysis.total_net_income:,.2f}"
            expenses_formatted = f"${budget_analysis.total_expenses:,.2f}"
            surplus_formatted = f"${budget_analysis.surplus:,.2f}"
            
            response_parts.append("**Budget Details:**\n")
            response_parts.append(f"• Total Net Income: **{income_formatted}**\n")
            response_parts.append(f"• Total Expenses: **{expenses_formatted}**\n")
            response_parts.append(f"• Surplus/Deficit: **{surplus_formatted}**\n")
        else:
            response_parts.append("**Status:** No budget data available\n")
        
        # Summary and Recommendation
        response_parts.append("### 📋 **Summary & Recommendation**\n")
        
        if combined_result == "pass":
            response_parts.append("✅ **RECOMMENDATION: APPROVE**\n")
            response_parts.append("This client shows positive indicators in both hardship and budget validation.\n")
            response_parts.append("**Action:** Can be shown to agents for further processing.\n")
        elif combined_result == "no_pass":
            response_parts.append("❌ **RECOMMENDATION: REJECT**\n")
            response_parts.append("This client shows negative indicators in both hardship and budget validation.\n")
            response_parts.append("**Action:** Should not be shown to agents.\n")
        elif combined_result == "mixed":
            response_parts.append("⚠️ **RECOMMENDATION: MANUAL REVIEW**\n")
            response_parts.append("This client shows mixed results - one validation passes while the other fails.\n")
            response_parts.append("**Action:** Requires manual review by a supervisor before proceeding.\n")
        else:
            response_parts.append("❓ **RECOMMENDATION: INSUFFICIENT DATA**\n")
            response_parts.append("No validation data is available for this contact.\n")
            response_parts.append("**Action:** Contact may need additional data collection.\n")
        
        return "\n".join(response_parts)
    
    def format_contact_response(self, contact: Dict[str, Any]) -> str:
        """
        Format hardship analysis results into a user-friendly response.
        
        Args:
            contact: Hardship analysis dictionary from get_contact_by_id
            
        Returns:
            Formatted string response
        """
        if not contact:
            return "❌ No hardship data found for that contact ID."
        
        # If there's a formatted response already provided, use it
        if contact.get('formatted_response'):
            return contact['formatted_response']
        
        # If there's an error, return the error message
        if contact.get('error'):
            return f"❌ Error analyzing hardship data: {contact['error']}"
        
        contact_id = contact.get('contact_id', 'Unknown')
        
        # Check if there's hardship data available
        hardship_data = contact.get('hardship_data', {})
        financial_hardship = hardship_data.get('financial_hardship', '')
        hardship_description = hardship_data.get('hardship_description', '')
        
        has_hardship_data = any([financial_hardship, hardship_description])
        
        if not has_hardship_data:
            return f"❌ Contact {contact_id} does not have hardship validation data.\n No hardship information has been recorded for this contact."
        
        # If there's analysis data, format it with organized structure
        analysis = contact.get('analysis')
        if analysis:
            result = analysis.get('result', 'unknown')
            confidence = analysis.get('confidence', 0.0)
            reason = analysis.get('reason', 'No reason provided')
            
            # Format confidence as percentage with one decimal place
            confidence_percent = f"{confidence * 100:.1f}%"
            
            # Build organized response
            response_parts = []
            
            # Header with status icon
            if result == 'pass':
                response_parts.append(f"✅ Contact {contact_id} has hardship validation data")
            else:
                response_parts.append(f"❌ Contact {contact_id} hardship validation failed")
            
            # Hardship information section - removed details, only show reason
            
            # Analysis results section
            response_parts.append("")
            response_parts.append("Validation Analysis:")
            response_parts.append(f"• Result: {result.upper()}")
            response_parts.append(f"• Confidence: {confidence_percent}")
            response_parts.append(f"• Reason: {reason}")
            
            # Summary statement
            if result == 'pass':
                response_parts.append("")
                response_parts.append("The hardship validation data is available for this contact.")
            else:
                response_parts.append("")
                response_parts.append("The hardship validation data requires review or additional information.")
            
            return "\n".join(response_parts)
        
        return "❌ Unable to format hardship analysis results. Please try again."
    
    def format_budget_response(self, budget: Dict[str, Any]) -> str:
        """
        Format budget analysis results into a user-friendly response.
        
        Args:
            budget: Budget analysis dictionary from get_contact_budget_analysis
            
        Returns:
            Formatted string response
        """
        if not budget:
            return "❌ No budget data found for that contact ID."
        
        # If there's a formatted response already provided, use it
        if budget.get('formatted_response'):
            return budget['formatted_response']
        
        # If there's an error, return the error message
        if budget.get('error'):
            return f"❌ Error analyzing budget data: {budget['error']}"
        
        contact_id = budget.get('contact_id', 'Unknown')
        
        # Check if there's budget data available
        budget_data = budget.get('budget_data', {})
        total_net_income = budget_data.get('total_net_income', 0)
        total_expenses = budget_data.get('total_expenses', 0)
        
        has_budget_data = any([total_net_income > 0, total_expenses > 0])
        
        if not has_budget_data:
            return f"❌ Contact {contact_id} does not have budget validation data.\nNo budget information has been recorded for this contact."
        
        # If there's analysis data, format it with organized structure
        analysis = budget.get('analysis')
        if analysis:
            result = analysis.get('result', 'unknown')
            confidence = analysis.get('confidence', 0.0)
            reason = analysis.get('reason', 'No reason provided')
            surplus = analysis.get('surplus', 0)
            
            # Format currency values
            income_formatted = f"${total_net_income:,.2f}"
            expenses_formatted = f"${total_expenses:,.2f}"
            surplus_formatted = f"${surplus:,.2f}"
            confidence_percent = f"{confidence * 100:.1f}%"
            
            # Build organized response
            response_parts = []
            
            # Header with status icon
            if result == 'pass':
                response_parts.append(f"✅ Contact {contact_id} has a **positive budget surplus**")
            else:
                response_parts.append(f"❌ Contact {contact_id} has a **negative budget surplus**")
            
            # Budget information section
            response_parts.append("")
            response_parts.append("**Budget Analysis:**")
            response_parts.append(f"• Total Net Income: **{income_formatted}**")
            response_parts.append(f"• Total Expenses: **{expenses_formatted}**")
            response_parts.append(f"• Surplus/Deficit: **{surplus_formatted}**")
            
            # Analysis results section
            response_parts.append("")
            response_parts.append("**Validation Result:**")
            response_parts.append(f"• Status: **{result.upper()}**")
            response_parts.append(f"• Confidence: **{confidence_percent}**")
            response_parts.append(f"• Reason: {reason}")
            
            # Summary statement
            if result == 'pass':
                response_parts.append("")
                response_parts.append("✅ **PASS** - This client shows a positive surplus and can be shown to agents.")
            else:
                response_parts.append("")
                response_parts.append("❌ **NO PASS** - This client shows a negative surplus and should not be shown to agents.")
            
            return "\n".join(response_parts)
        
        return "❌ Unable to format budget analysis results. Please try again."
    
    def extract_contact_id_from_message(self, message: str) -> Optional[int]:
        """
        Extract contact ID from user message using various patterns.
        
        Args:
            message: User message text
            
        Returns:
            Contact ID if found, None otherwise
        """
        import re
        
        # Look for patterns like "ID 123", "contact 456", "user 789", etc.
        patterns = [
            r'(?:contact|user|id|person)\s+(?:#)?(\d+)',
            r'(\d+)\s+(?:contact|user|id)',
            r'find\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'get\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'look\s+up\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'search\s+for\s+(?:contact|user)\s+(?:#)?(\d+)',
            r'(\d+)',  # Fallback: just look for any number
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue
        
        return None 