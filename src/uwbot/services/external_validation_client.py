"""
External Validation API Client

This service calls an external validation API instead of using local validation services.
It provides a clean interface for validation requests while delegating the actual
validation logic to an external service.
"""

import logging
import httpx
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from uwbot.utils.result import Result, Success, Error

logger = logging.getLogger(__name__)

class ValidationRequest(BaseModel):
    """Request model for external validation API."""
    contact_id: int = Field(..., ge=1, le=99_999_999_999)
    user_id: Optional[str] = None
    user_name: Optional[str] = None

class ExternalValidationClient:
    """Client for calling external validation API."""
    
    def __init__(self, api_base_url: str, timeout: float = 30.0):
        """
        Initialize the external validation client.
        
        Args:
            api_base_url: Base URL of the external validation API
            timeout: Request timeout in seconds
        """
        self.api_base_url = api_base_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
        logger.info(f"ExternalValidationClient initialized with API URL: {self.api_base_url}")
    
    async def validate_combined(self, contact_id: int, user_id: Optional[str] = None, user_name: Optional[str] = None) -> Result[Dict[str, Any]]:
        """
        Perform combined validation using external API.
        
        Args:
            contact_id: The contact ID to validate
            user_id: Optional user ID for tracking
            user_name: Optional user name for tracking
            
        Returns:
            Result containing validation response
        """
        try:
            url = f"{self.api_base_url}/api/validation/combined"
            payload = ValidationRequest(
                contact_id=contact_id,
                user_id=user_id,
                user_name=user_name
            )
            
            logger.info(f"Calling external validation API for contact {contact_id}")
            response = await self.client.post(url, json=payload.dict())
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"External validation successful for contact {contact_id}")
                return Success(result)
            elif response.status_code == 422:
                error_msg = f"Invalid contact ID: {contact_id}"
                logger.warning(f"External validation failed - invalid contact ID: {contact_id}")
                return Error(error_msg)
            else:
                error_msg = f"External API error: {response.status_code} - {response.text}"
                logger.error(f"External validation API error: {response.status_code} - {response.text}")
                return Error(error_msg)
                
        except httpx.TimeoutException:
            error_msg = f"External validation API timeout after {self.timeout}s"
            logger.error(error_msg)
            return Error(error_msg)
        except httpx.ConnectError:
            error_msg = "Failed to connect to external validation API"
            logger.error(error_msg)
            return Error(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error calling external validation API: {str(e)}"
            logger.error(error_msg)
            return Error(error_msg)
    
    
    async def get_contact_data(self, contact_id: int) -> Result[Dict[str, Any]]:
        """
        Get contact data from external API.
        
        Args:
            contact_id: The contact ID to retrieve data for
            
        Returns:
            Result containing contact data
        """
        try:
            url = f"{self.api_base_url}/api/validation/contact/{contact_id}"
            
            logger.info(f"Calling external API to get contact data for {contact_id}")
            response = await self.client.get(url)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"External contact data retrieval successful for contact {contact_id}")
                return Success(result)
            elif response.status_code == 422:
                error_msg = f"Invalid contact ID: {contact_id}"
                logger.warning(f"External contact data retrieval failed - invalid contact ID: {contact_id}")
                return Error(error_msg)
            else:
                error_msg = f"External API error: {response.status_code} - {response.text}"
                logger.error(f"External contact data API error: {response.status_code} - {response.text}")
                return Error(error_msg)
                
        except httpx.TimeoutException:
            error_msg = f"External contact data API timeout after {self.timeout}s"
            logger.error(error_msg)
            return Error(error_msg)
        except httpx.ConnectError:
            error_msg = "Failed to connect to external contact data API"
            logger.error(error_msg)
            return Error(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error calling external contact data API: {str(e)}"
            logger.error(error_msg)
            return Error(error_msg)
    
    async def health_check(self) -> Result[Dict[str, Any]]:
        """
        Check health of external validation API.
        
        Returns:
            Result containing health status
        """
        try:
            url = f"{self.api_base_url}/api/validation/health"
            
            logger.info("Calling external validation API health check")
            response = await self.client.get(url)
            
            if response.status_code == 200:
                result = response.json()
                logger.info("External validation API health check successful")
                return Success(result)
            else:
                error_msg = f"External API health check failed: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return Error(error_msg)
                
        except httpx.TimeoutException:
            error_msg = f"External validation API health check timeout after {self.timeout}s"
            logger.error(error_msg)
            return Error(error_msg)
        except httpx.ConnectError:
            error_msg = "Failed to connect to external validation API for health check"
            logger.error(error_msg)
            return Error(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error calling external validation API health check: {str(e)}"
            logger.error(error_msg)
            return Error(error_msg)
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
        logger.info("ExternalValidationClient HTTP client closed") 