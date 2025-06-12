BRAND = {
    "primary": "#003E6B",   # Navy
    "accent":  "#46B2FF",   # Sky
    "bg":      "#F6F9FC",   # Off-white
    # Replace with real hosted logo URL
    "logo_url": "https://media.licdn.com/dms/image/v2/D4E0BAQG0T9_TYmxmIA/company-logo_200_200/company-logo_200_200/0/1711378838842/claritydebtresolutioninc_logo?e=2147483647&v=beta&t=Utk6QkPTBRcH6HSRINip1Em7EWDDX5AVZ1qrPJ7QWmE",
}


def brand_header(title: str, *, size: str = "Medium") -> dict:
    """Header with thin navy bar, logo and title. Works in dark/light themes."""
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
                        "url": BRAND["logo_url"],
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