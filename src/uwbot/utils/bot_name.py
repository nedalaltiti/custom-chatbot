"""
Utility for getting bot name with app instance suffix.
"""

from uwbot.config.app_config import get_app_config

def get_bot_name() -> str:
    """
    Get bot name with app instance suffix.
    
    Returns:
        Bot name like "UWBot"
    """
    app_config = get_app_config()
    return app_config.name

def get_bot_display_name() -> str:
    """
    Get bot display name for UI.
    
    Returns:
        Display name like "UWBot"
    """
    app_config = get_app_config()
    return app_config.name 