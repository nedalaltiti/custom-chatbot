"""
Contact Repository for database operations.

This repository holds a single database session and provides data access methods
for contact-related operations. It ensures consistent transactions and efficient
connection pool usage.
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, bindparam, and_, or_, null
from uwbot.db.models import Contact, ContactUserField, BudgetData, BudgetFields
from uwbot.config.settings import settings

logger = logging.getLogger(__name__)

class ContactRepository:
    """Repository for contact-related database operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        # Get field IDs from settings
        self.financial_hardship_id = settings.hardship_fields.financial_hardship_id
        self.hardship_description_id = settings.hardship_fields.hardship_description_id
        
        # Get budget field values from settings
        self.budget_acctid = settings.budget_fields.acctid
        self.budget_c_type = settings.budget_fields.c_type
        self.budget_iscoapp = settings.budget_fields.iscoapp
        self.budget_leadstatus = settings.budget_fields.leadstatus
    
    async def fetch_contact(self, contact_id: int) -> Optional[Contact]:
        """Fetch a single contact by ID with soft-delete filtering."""
        stmt = (
            select(Contact)
            .where(
                and_(
                    Contact.id == bindparam('contact_id'),
                    # Soft-delete filter: not deleted (del IS NULL OR del != true)
                    or_(
                        Contact.del_.is_(null()),
                        Contact.del_ != True
                    )
                )
            )
        )
        
        result = await self.session.execute(stmt, {"contact_id": contact_id})
        return result.scalar_one_or_none()
    
    async def fetch_contact_with_budget_data(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """Fetch contact with budget data using a single query."""
        stmt = (
            select(
                Contact.id,
                Contact.acctid,
                Contact.del_,
                Contact.iscoapp,
                Contact.c_type,
                Contact.leadstatus,
                func.sum(
                    case(
                        (BudgetFields.field_type == 'I', BudgetData.field_val),
                        else_=0
                    )
                ).label('total_net_income'),
                func.sum(
                    case(
                        (BudgetFields.field_type == 'E', BudgetData.field_val),
                        else_=0
                    )
                ).label('total_expenses')
            )
            .select_from(Contact)
            .outerjoin(BudgetData, Contact.id == BudgetData.contact_id)
            .outerjoin(BudgetFields, BudgetData.field_id == BudgetFields.id)
            .where(
                and_(
                    Contact.id == bindparam('contact_id'),
                    # Soft-delete filter
                    or_(
                        Contact.del_.is_(null()),
                        Contact.del_ != True
                    ),
                    # Additional filters from environment variables
                    Contact.acctid == self.budget_acctid,
                    Contact.c_type == self.budget_c_type,
                    Contact.iscoapp == self.budget_iscoapp,
                    Contact.leadstatus == self.budget_leadstatus
                )
            )
            .group_by(
                Contact.id, 
                Contact.acctid, 
                Contact.del_, 
                Contact.iscoapp, 
                Contact.c_type, 
                Contact.leadstatus
            )
        )
        
        result = await self.session.execute(stmt, {"contact_id": contact_id})
        row = result.fetchone()
        
        if row:
            return {
                "contact_id": row.id,
                "acctid": row.acctid,
                "del_flag": row.del_,
                "iscoapp": row.iscoapp,
                "c_type": row.c_type,
                "leadstatus": row.leadstatus,
                "total_net_income": float(row.total_net_income or 0),
                "total_expenses": float(row.total_expenses or 0),
            }
        return None
    
    async def fetch_contact_with_hardship_data(self, contact_id: int) -> Optional[Dict[str, Any]]:
        """Fetch contact with hardship data using separate queries."""
        # First, get the base contact information
        contact = await self.fetch_contact(contact_id)
        if not contact:
            return None
        
        # Get hardship data using separate queries
        financial_hardship_stmt = (
            select(ContactUserField.f_string)
            .where(
                and_(
                    ContactUserField.contact_id == bindparam('contact_id'),
                    ContactUserField.custom_id == self.financial_hardship_id
                )
            )
        )
        
        hardship_description_stmt = (
            select(ContactUserField.f_string)
            .where(
                and_(
                    ContactUserField.contact_id == bindparam('contact_id'),
                    ContactUserField.custom_id == self.hardship_description_id
                )
            )
        )
        
        # Execute both queries
        financial_result = await self.session.execute(financial_hardship_stmt, {"contact_id": contact_id})
        description_result = await self.session.execute(hardship_description_stmt, {"contact_id": contact_id})
        
        financial_hardship = financial_result.scalar_one_or_none()
        hardship_description = description_result.scalar_one_or_none()
        
        return {
            "contact_id": contact.id,
            "acctid": contact.acctid,
            "del": contact.del_,
            "iscoapp": contact.iscoapp,
            "c_type": contact.c_type,
            "leadstatus": contact.leadstatus,
            "financial_hardship": financial_hardship,
            "hardship_description": hardship_description,
        } 