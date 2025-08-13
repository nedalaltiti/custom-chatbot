from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field


# ───────── auxiliary sub-models ────────────────────────────────────────────

class TeamsUser(BaseModel):
    """The `from` object in a Teams activity."""
    id: str
    name: Optional[str] = None
    aad_object_id: Optional[str] = Field(None, alias="aadObjectId")
    job_title: Optional[str] = Field(None, alias="jobTitle")
    display_name: Optional[str] = Field(None, alias="displayName")
    email: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class TeamsConversation(BaseModel):
    id: str
    name: Optional[str] = None


class TeamsRecipient(BaseModel):
    id: str
    name: Optional[str] = None


# ───────── main request/response models ────────────────────────────────────

class TeamsMessageRequest(BaseModel):
    """
    Incoming Bot Framework activity as sent by Microsoft Teams.

    Only the fields our bot actually uses are included; the rest are ignored
    thanks to `extra="ignore"`.
    """
    type: str = "message"  # Can be "message", "invoke", etc.
    activity_id: Optional[str] = Field(None, alias="id")
    timestamp: Optional[datetime] = None
    service_url: str = Field(..., alias="serviceUrl")
    name: Optional[str] = None  # For invoke activities like "message/submitAction"
        
    channel_id: str = Field("msteams", alias="channelId")  # Removed Literal restriction
    from_: TeamsUser = Field(..., alias="from")
    conversation: TeamsConversation
    recipient: Optional[TeamsRecipient] = None

    text: Optional[str] = None
    entities: Optional[List[Dict[str, Any]]] = None
    attachments: Optional[List[Dict[str, Any]]] = None

    # If this activity is a reply, Teams gives the parent id in camelCase
    reply_to_id: Optional[str] = Field(None, alias="replyToId")

    # Adaptive-card submit payloads land in `value`
    value: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

        
class TeamsActivityResponse(BaseModel):
    """Outgoing bot activity (we usually set only `type` and `text`)."""
    type: str = "message"
    text: str


class FeedbackRequest(BaseModel):
    user_id: str
    rating: int
    suggestion: Optional[str] = "" 
