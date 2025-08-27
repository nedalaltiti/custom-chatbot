"""
Adaptive card templates for Teams messages.
"""

from uwbot.infrastructure.cards_brand import BRAND, brand_header

def _list_item(emoji: str, text: str) -> dict:
    return {
        "type": "ColumnSet",
        "spacing": "Small",
        "columns": [
            {"type": "Column", "width": "auto", "items": [{"type": "TextBlock", "text": emoji, "size": "Medium"}]},
            {"type": "Column", "width": "stretch", "items": [{"type": "TextBlock", "text": text, "wrap": True}]}
        ]
    }

def create_welcome_card(user_name: str = "there") -> dict:
    """Elegant, theme-aware welcome card with simplified greeting."""
    header = f"Hi {user_name}"

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            # Large, brand-coloured banner
            brand_header(header),
            {
                "type": "TextBlock",
                "text": (
                    "I'm your Underwriting Assistant! Please provide a valid **contact ID** in the **Underwriting Stage**."
                ),
                "wrap": True,
                "spacing": "Medium",
            },
            {
                "type": "TextBlock",
                "text": "How can I assist you today?",
                "wrap": True,
                "spacing": "Medium",
            },
        ],
        "backgroundColor": BRAND["bg"],
    }