"""
Dynamic prompt loader for QC bot.

Loads prompts from the QC-specific directory.
"""

import os
import sys
import importlib.util
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from qcbot.config.app_config import get_current_app_config

logger = logging.getLogger(__name__)

# Cache for loaded prompt modules
_prompt_cache: Dict[str, Any] = {}


def load_prompt_module() -> Any:
    """
    Load the prompt module for QC bot.
    
    Returns:
        The loaded prompt module
    """
    # Get QC app config (standalone)
    from qcbot.config.app_config import get_current_app_config
    app_config = get_current_app_config()
    
    cache_key = "qc"
    
    # Check cache first
    if cache_key in _prompt_cache:
        logger.debug(f"Using cached prompt module for {cache_key}")
        return _prompt_cache[cache_key]
    
    # Try to load app-specific prompt
    prompt_path = app_config.prompt_dir / "prompt.py"
    
    if prompt_path.exists():
        logger.info(f"Loading app-specific prompt from {prompt_path}")
        try:
            # Load the module dynamically
            spec = importlib.util.spec_from_file_location(
                f"prompt_{cache_key}", 
                prompt_path
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                _prompt_cache[cache_key] = module
                return module
        except Exception as e:
            logger.error(f"Failed to load app-specific prompt: {e}")
    
    # Fallback to default prompt module
    logger.info(f"Using default prompt module for {cache_key}")
    try:
        from qcbot.core.rag import prompt as default_prompt
        _prompt_cache[cache_key] = default_prompt
        return default_prompt
    except ImportError as e:
        logger.error(f"Failed to load default prompt module: {e}")
        raise


def get_base_system() -> str:
    """Get BASE_SYSTEM prompt for QC bot."""
    module = load_prompt_module()
    return getattr(module, 'BASE_SYSTEM', '')


def get_flow_rules() -> str:
    """Get FLOW_RULES prompt for QC bot."""
    module = load_prompt_module()
    return getattr(module, 'FLOW_RULES', '')


def get_template() -> str:
    """Get TEMPLATE prompt for QC bot."""
    module = load_prompt_module()
    return getattr(module, 'TEMPLATE', '')


def build_prompt(parts: Dict[str, Any]) -> str:
    """
    Build the final prompt using QC-specific prompt module.
    
    Args:
        parts: Dictionary containing system, context, history, and query
        
    Returns:
        Complete prompt optimized for QC bot
    """
    module = load_prompt_module()
    
    # Use the module's build function if available
    if hasattr(module, 'build'):
        return module.build(parts)
    
    # Otherwise, build manually
    template = get_template()
    base_system = get_base_system()
    flow_rules = get_flow_rules()
    
    return template.format(
        system=parts.get("system", base_system),
        flow_rules=flow_rules,
        context=parts.get("context", ""),
        history=parts.get("history", ""),
        query=parts.get("query", ""),
    )


def clear_prompt_cache():
    """Clear the prompt module cache."""
    global _prompt_cache
    _prompt_cache.clear()
    logger.info("Cleared prompt module cache") 