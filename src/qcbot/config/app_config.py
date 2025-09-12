"""
Standalone Configuration for QC Bot.

This module provides simple configuration for the QC chatbot.
The QC bot is standalone and doesn't use multi-instance functionality.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QCAppConfig:
    """Configuration for the QC chatbot."""
    instance_id: str = "qc"
    name: str = "QC Assistant"
    knowledge_base_dir: Path = Path("data/knowledge/qc")
    embeddings_dir: Path = Path("data/embeddings/qc")
    prompt_dir: Path = Path("data/prompts/qc")
    logo_url: Optional[str] = None


# Global QC app config instance
_qc_app_config: Optional[QCAppConfig] = None


def get_qc_app_config() -> QCAppConfig:
    """Get the QC app configuration."""
    global _qc_app_config
    if _qc_app_config is None:
        _qc_app_config = QCAppConfig()
        
        # Ensure directories exist
        _qc_app_config.knowledge_base_dir.mkdir(parents=True, exist_ok=True)
        _qc_app_config.embeddings_dir.mkdir(parents=True, exist_ok=True)
        _qc_app_config.prompt_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"QC App Config initialized: {_qc_app_config.name}")
        logger.info(f"Knowledge base: {_qc_app_config.knowledge_base_dir}")
        logger.info(f"Embeddings: {_qc_app_config.embeddings_dir}")
        logger.info(f"Prompts: {_qc_app_config.prompt_dir}")
    
    return _qc_app_config


# Backward compatibility functions for existing code
def get_current_app_config() -> QCAppConfig:
    """Get the current app configuration (QC bot)."""
    return get_qc_app_config()


def get_current_app_instance() -> str:
    """Get the current app instance ID (always 'qc')."""
    return "qc"


def is_feature_enabled(feature_name: str) -> bool:
    """Always returns False for QC bot (no feature flags)."""
    logger.warning(f"Feature check called for '{feature_name}', but QC bot has no feature flags.")
    return False


def clear_instance_cache() -> None:
    """Clear the cached app config (useful for testing)."""
    global _qc_app_config
    _qc_app_config = None
    logger.debug("Cleared QC app config cache")