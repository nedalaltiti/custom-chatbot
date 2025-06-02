"""
Multi-tenant configuration for HR chatbot supporting different regions/teams.

This module provides tenant-specific configuration including knowledge bases,
features, and regional settings.
"""

import os
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class TenantRegion(Enum):
    """Supported tenant regions."""
    JORDAN = "jordan"
    US = "us"
    # Future: UAE, MEXICO, etc.

@dataclass(frozen=True)
class TenantConfig:
    """Configuration for a specific tenant."""
    region: TenantRegion
    name: str
    knowledge_base_path: str
    embeddings_path: str
    enabled_features: Set[str]
    disabled_features: Set[str]
    hr_support_url: str
    language: str = "en"
    timezone: str = "UTC"
    
    # Regional-specific settings
    currency: str = "USD"
    working_hours: str = "9:00-17:00"
    holidays_calendar: str = "default"
    
    @property
    def supports_noi(self) -> bool:
        """Check if this tenant supports Notice of Investigation."""
        return "noi" in self.enabled_features
    
    @property
    def knowledge_base_dir(self) -> Path:
        """Get the knowledge base directory path."""
        return Path(self.knowledge_base_path)
    
    @property
    def embeddings_dir(self) -> Path:
        """Get the embeddings directory path."""
        return Path(self.embeddings_path)

# Tenant configurations
TENANT_CONFIGS: Dict[TenantRegion, TenantConfig] = {
    TenantRegion.JORDAN: TenantConfig(
        region=TenantRegion.JORDAN,
        name="HR Jordan Team",
        knowledge_base_path="data/knowledge/jordan",
        embeddings_path="data/embeddings/jordan",
        enabled_features={"noi", "resignation", "benefits", "policies", "medical_insurance"},
        disabled_features=set(),
        hr_support_url="https://hrsupport.usclarity.com/support/home",
        language="en",
        timezone="Asia/Amman",
        currency="JOD",
        working_hours="8:00-16:00",
        holidays_calendar="jordan"
    ),
    
    TenantRegion.US: TenantConfig(
        region=TenantRegion.US,
        name="HR US Team", 
        knowledge_base_path="data/knowledge/us",
        embeddings_path="data/embeddings/us",
        enabled_features={"resignation", "benefits", "policies", "medical_insurance", "401k"},
        disabled_features={"noi"},  # US team doesn't use NOI
        hr_support_url="https://hrsupport-us.usclarity.com/support/home",
        language="en",
        timezone="America/New_York",
        currency="USD", 
        working_hours="9:00-17:00",
        holidays_calendar="us"
    )
}

class TenantManager:
    """Enhanced tenant manager with multiple detection methods."""
    
    _current_tenant: Optional[TenantConfig] = None
    _request_context: Dict[str, str] = {}
    
    @classmethod
    def detect_tenant(cls, request=None, headers: Optional[Dict[str, str]] = None) -> TenantConfig:
        """
        Detect tenant using multiple methods in order of preference:
        1. Request header (X-Tenant-Region) - from nginx
        2. Environment variable (TENANT_REGION)
        3. Request context (for testing)
        4. Default to Jordan
        
        Args:
            request: FastAPI request object (optional)
            headers: Dict of headers (optional)
            
        Returns:
            TenantConfig for the detected tenant
        """
        detected_region = None
        
        # Method 1: Check request headers (from nginx)
        if request and hasattr(request, 'headers'):
            tenant_header = request.headers.get('X-Tenant-Region') or request.headers.get('x-tenant-region')
            if tenant_header:
                detected_region = tenant_header.lower()
                logger.debug(f"Tenant detected from request header: {detected_region}")
        
        # Method 2: Check provided headers dict
        if not detected_region and headers:
            tenant_header = headers.get('X-Tenant-Region') or headers.get('x-tenant-region')
            if tenant_header:
                detected_region = tenant_header.lower()
                logger.debug(f"Tenant detected from headers dict: {detected_region}")
        
        # Method 3: Check environment variable
        if not detected_region:
            env_tenant = os.environ.get("TENANT_REGION")
            if env_tenant:
                detected_region = env_tenant.lower()
                logger.debug(f"Tenant detected from environment: {detected_region}")
        
        # Method 4: Check request context (for testing/manual override)
        if not detected_region:
            context_tenant = cls._request_context.get("tenant_region")
            if context_tenant:
                detected_region = context_tenant.lower()
                logger.debug(f"Tenant detected from context: {detected_region}")
        
        # Method 5: Default to Jordan
        if not detected_region:
            detected_region = "jordan"
            logger.debug("Using default tenant: jordan")
        
        # Convert to enum and get config
        try:
            region_enum = TenantRegion(detected_region)
            config = TENANT_CONFIGS[region_enum]
            logger.debug(f"Tenant resolved: {config.name} ({config.region.value})")
            return config
        except (ValueError, KeyError):
            logger.warning(f"Invalid tenant region '{detected_region}', falling back to Jordan")
            return TENANT_CONFIGS[TenantRegion.JORDAN]
    
    @classmethod
    def set_current_tenant(cls, tenant: TenantConfig):
        """Set the current tenant (for testing or manual override)."""
        cls._current_tenant = tenant
        logger.info(f"Current tenant set to: {tenant.name}")
    
    @classmethod
    def get_current_tenant(cls, request=None, headers: Optional[Dict[str, str]] = None) -> TenantConfig:
        """
        Get the current tenant, detecting if not already set.
        
        Args:
            request: FastAPI request object (optional)
            headers: Dict of headers (optional)
            
        Returns:
            TenantConfig for the current tenant
        """
        # Use cached tenant if available and no request context
        if cls._current_tenant and not request and not headers:
            return cls._current_tenant
        
        # Detect tenant from request/environment
        tenant = cls.detect_tenant(request, headers)
        
        # Cache for subsequent calls without request context
        if not request and not headers:
            cls._current_tenant = tenant
            
        return tenant
    
    @classmethod
    @contextmanager
    def tenant_context(cls, region: str):
        """Context manager for temporarily setting tenant region."""
        old_context = cls._request_context.copy()
        cls._request_context["tenant_region"] = region
        
        try:
            yield
        finally:
            cls._request_context = old_context

# Convenience functions (maintain backward compatibility)
def get_current_tenant(request=None, headers: Optional[Dict[str, str]] = None) -> TenantConfig:
    """Get the current tenant configuration."""
    return TenantManager.get_current_tenant(request, headers)

def is_feature_enabled(feature: str, request=None, headers: Optional[Dict[str, str]] = None) -> bool:
    """Check if a feature is enabled for the current tenant."""
    tenant = get_current_tenant(request, headers)
    
    if feature.lower() == "noi":
        return tenant.supports_noi
    
    # Add other feature checks as needed
    return True

def get_knowledge_base_path() -> str:
    """Get the knowledge base path for the current tenant."""
    return get_current_tenant().knowledge_base_path

def get_embeddings_path() -> str:
    """Get the embeddings path for the current tenant."""
    return get_current_tenant().embeddings_path

def get_hr_support_url() -> str:
    """Get the HR support URL for the current tenant."""
    return get_current_tenant().hr_support_url

# FastAPI dependency for request-aware tenant detection
def get_tenant_from_request():
    """FastAPI dependency to get tenant from request headers."""
    def _get_tenant(request):
        return get_current_tenant(request=request)
    return _get_tenant