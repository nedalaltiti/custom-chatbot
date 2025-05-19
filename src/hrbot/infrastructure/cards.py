"""
Adaptive card templates for Teams messages.
"""

def create_welcome_card(user_name="there"):
    """Create a welcome card for new users."""
    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.3",
        "body": [
            {
                "type": "TextBlock",
                "size": "Medium",
                "weight": "Bolder",
                "text": f"Welcome, {user_name}!"
            },
            {
                "type": "TextBlock",
                "text": "I'm your HR Assistant! I can help you with questions about:",
                "wrap": True
            },
            {
                "type": "FactSet",
                "facts": [
                    {
                        "title": "🗓️",
                        "value": "Time off and leave policies"
                    },
                    {
                        "title": "💰",
                        "value": "Benefits and compensation"
                    },
                    {
                        "title": "📝",
                        "value": "HR processes and procedures"
                    },
                    {
                        "title": "🎓",
                        "value": "Learning and development"
                    }
                ]
            },
            {
                "type": "TextBlock",
                "text": "How can I assist you today?",
                "wrap": True
            }
        ]
    }

def create_feedback_card(selected_rating: int = 0):
    """Create a feedback card rendered as a single horizontal row of 1-5 stars.

    • Each star is a Column with a TextBlock (⭐ or ☆) and a selectAction so it
      behaves like a button but has *no* default Teams border.
    • When a user taps a star we send `Action.Submit` with `action=submit_rating` &
      the chosen rating value. The router will re-render this same card with the
      selected stars filled.
    """

    def star_column(idx: int) -> dict:
        filled = idx <= selected_rating
        return {
            "type": "Column",
            "width": "auto",
            # The Column itself is clickable
            "selectAction": {
                "type": "Action.Submit",
                "data": {"action": "submit_rating", "rating": idx}
            },
            "items": [{
                "type": "TextBlock",
                "text": "⭐" if filled else "☆",
                "weight": "Bolder",
                "size": "ExtraLarge",
                "horizontalAlignment": "Center"
            }]
        }

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.3",
        "body": [
            {
                "type": "TextBlock",
                "size": "Medium",
                "weight": "Bolder",
                "text": "We value your feedback!"
            },
            {
                "type": "TextBlock",
                "text": "How would you rate your experience with our HR Assistant?",
                "wrap": True
            },
            {
                "type": "ColumnSet",
                "horizontalAlignment": "Center",
                "spacing": "Medium",
                "columns": [star_column(i) for i in range(1, 6)]
            },
            {
                "type": "Input.Text",
                "id": "comment",
                "placeholder": "Any suggestions for improvement? (optional)",
                "isMultiline": True
            }
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "Later",
                "data": {"action": "dismiss_feedback"}
            },
            {
                "type": "Action.Submit",
                "title": "Provide Feedback",
                "style": "positive",
                "data": {"action": "submit_feedback", "rating": selected_rating or 0}
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