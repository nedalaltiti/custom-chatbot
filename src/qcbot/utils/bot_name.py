"""
Utility for getting QC bot name.
"""

from qcbot.config.app_config import get_current_app_config

def get_bot_name() -> str:
    """
    Get QC bot name.
    
    Returns:
        Bot name "qcbot"
    """
    return "qcbot"
        
def get_bot_display_name() -> str:
    """
    Get QC bot display name for UI.
    
    Returns:
        Display name "QC Assistant"
    """
    try:
        app_config = get_current_app_config()
        return app_config.name
    except Exception:
        return "QC Assistant" 