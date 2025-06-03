"""
Utility for getting bot name with app instance suffix.
"""

from hrbot.config.app_config import get_current_app_config

def get_bot_name() -> str:
    """
    Get bot name with app instance suffix.
    
    Returns:
        Bot name like "hrbot-jo" or "hrbot-us"
    """
    try:
        app_config = get_current_app_config()
        return f"hrbot-{app_config.instance_id}"
    except Exception:
        # Fallback to default if app config not available
        return "hrbot"
        
def get_bot_display_name() -> str:
    """
    Get bot display name for UI.
    
    Returns:
        Display name like "HR Bot (Jo)" or "HR Bot (US)"
    """
    try:
        app_config = get_current_app_config()
        return f"HR Bot ({app_config.name})"
    except Exception:
        return "HR Bot" 