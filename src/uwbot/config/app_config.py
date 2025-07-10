"""
Multi-App Configuration for Hardship Validation Bot - CI/CD Friendly & Scalable.

This module manages configuration for multiple app registrations within the same Azure AD tenant.
New instances can be added simply by updating the configuration file - no code changes required.

Features:
- Configuration-driven instances (instances.yaml)
- Automatic directory provisioning
- Standardized hostname patterns
- CI/CD friendly deployment

App instance detection priority:
1. Hostname-based detection (from ingress URL patterns)
2. APP_INSTANCE environment variable
3. Default instance from config

To add a new region:
1. Add entry to instances.yaml
2. Create deployment manifest
3. Deploy - directories and configs are auto-created
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class AppConfig:
    """Configuration for the single uwbot instance."""
    name: str
    prompt_dir: Path
    logo_url: Optional[str] = None
    hardship_support_url: str = None

# Single static config for uwbot
_app_config = AppConfig(
    name="UWBot",
    prompt_dir=Path("data/prompts"),
    logo_url=os.environ.get("BOT_LOGO_URL"),
)

def get_app_config() -> AppConfig:
    """Return the single app config for uwbot."""
    return _app_config