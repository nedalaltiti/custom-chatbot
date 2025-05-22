from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class TeamsFrom(BaseModel):
    id: str
    name: Optional[str] = None
    aad_object_id: Optional[str] = Field(None, alias="aadObjectId")
    job_title: Optional[str] = Field(None, alias="jobTitle")
    display_name: Optional[str] = Field(None, alias="displayName")
    email: Optional[str] = Field(None, alias="email")
    
    class Config:
        allow_population_by_field_name = True
        allow_population_by_alias      = True

class TeamsConversation(BaseModel):
    id: str
    name: Optional[str] = None

class TeamsRecipient(BaseModel):
    id: str
    name: Optional[str] = None

class TeamsMessageRequest(BaseModel):
    """Model for incoming Teams messages."""
    type: str = "message"
    id: Optional[str] = None
    timestamp: Optional[str] = None
    serviceUrl: str
    channelId: str = "msteams"
    from_: TeamsFrom = Field(..., alias="from")
    conversation: Dict[str, Any]
    recipient: Optional[TeamsRecipient] = None
    text: Optional[str] = None
    entities: Optional[list] = None
    attachments: Optional[list] = None
    value: Optional[Dict[str, Any]] = None
    
    class Config:
        populate_by_name = True
        
class TeamsActivityResponse(BaseModel):
    """Model for outgoing Teams responses."""
    type: str = "message"
    text: str

class FeedbackRequest(BaseModel):
    user_id: str
    rating: int
    suggestion: Optional[str] = "" 