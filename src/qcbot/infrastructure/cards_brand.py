from qcbot.config.app_config import get_current_app_config

BRAND = {
    "primary": "#003E6B",   # Navy
    "accent":  "#46B2FF",   # Sky
    "bg":      "#F6F9FC",   # Off-white
}


def brand_header(title: str, *, size: str = "Medium") -> dict:
    """Header with thin navy bar, logo and title. Works in dark/light themes."""
    app_config = get_current_app_config()
    logo_url = app_config.logo_url 
    return {
        "type": "Container",
        "bleed": True,
        "style": "emphasis",  # Teams picks neutral surface colour and text contrast
        "items": [{
            "type": "ColumnSet",
            "verticalAlignment": "Center",
            "columns": [
                {  # Thin accent bar
                    "type": "Column",
                    "width": "10px",
                    "backgroundColor": BRAND["primary"]
                },
                {  # Logo
                    "type": "Column",
                    "width": "auto",
                    "spacing": "Small",
                    "items": [{
                        "type": "Image",
                        "url": logo_url,
                        "size": "Small",
                        "style": "Person"
                    }]
                },
                {  # Title text
                    "type": "Column",
                    "width": "stretch",
                    "items": [{
                        "type": "TextBlock",
                        "text": title,
                        "weight": "Bolder",
                        "size": size,
                        "wrap": True
                    }]
                }
            ]
        }]
    }