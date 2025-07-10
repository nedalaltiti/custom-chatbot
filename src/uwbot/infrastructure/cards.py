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
                    "I'm your Validation Assistant 👋. I can help you check if contacts have hardship validation data and analyze their financial hardship claims."
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


def create_feedback_card(selected_rating: int = 0, *, interactive: bool = True, existing_comment: str = "", message_id: int | None = None):
    """Create a feedback card rendered as a single horizontal row of 1-5 stars.
    • Each star is a Column with a TextBlock (⭐ or ☆) and a selectAction so it
      behaves like a button but has *no* default Teams border.
    • When a user taps a star we send `Action.Submit` with `action=submit_rating` &
      the chosen rating value. The router will re-render this same card with the
      selected stars filled.
    • existing_comment: Preserves user's typed comment content when updating the card
    • message_id: Associates feedback with a specific message
    """

    def star_column(idx: int) -> dict:
        filled = idx <= selected_rating
        return {
            "type": "Column", "width": "auto",
            "selectAction": {"type": "Action.Submit",
                             "data": {"action": "submit_rating", "rating": idx}},
            "items": [{
                "type": "TextBlock",
                "text": "★",  # solid star
                "weight": "Bolder",
                "size": "ExtraLarge",
                "horizontalAlignment": "Center",
                "color": "Accent" if filled else "Default"
            }]
        }

    # Comment input with preserved value
    comment_input = {
        "type": "Input.Text",
        "id": "comment",
        "placeholder": "Any suggestions for improvement? (optional)",
        "isMultiline": True
    }
    
    # Preserve existing comment if provided
    if existing_comment:
        comment_input["value"] = existing_comment

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "backgroundColor": BRAND["bg"],
        "body": [
            brand_header("We value your feedback"),
            {
                "type": "TextBlock",
                "text": "How would you rate your experience with our Validation Assistant?",
                "wrap": True
            },
            {
                "type": "ColumnSet",
                "horizontalAlignment": "Center",
                "spacing": "Medium",
                "columns": [star_column(i) for i in range(1, 6)]
            },
            comment_input
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "Submit Feedback",
                "style": "positive",
                "data": {
                    "action": "submit_feedback",
                    "rating": selected_rating or 0,
                    **({"messageId": message_id} if message_id else {})
                }
            }
        ]
    }

    return card

def create_reaction_card(action_prefix: str = "react") -> dict:
    """Return an inline reaction bar with copy / like / dislike.

    action_prefix lets the caller namespace the action if needed.
    """

    def icon(col, icon_char, action):
        return {
            "type": "Column",
            "width": "auto",
            "selectAction": {
                "type": "Action.Submit",
                "data": {"action": f"{action_prefix}_{action}"}
            },
            "items": [{
                "type": "TextBlock",
                "text": icon_char,
                "size": "Large",
                "horizontalAlignment": "Center"
            }]
        }

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.3",
        "body": [{
            "type": "ColumnSet",
            "horizontalAlignment": "Left",
            "spacing": "None",
            "columns": [
                icon("c", "\U0001F4CB", "copy"),
                icon("u", "\U0001F44D", "like"),
                icon("d", "\U0001F44E", "dislike")
            ]
        }]
    } 