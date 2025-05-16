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
    """Create a feedback card with a 5-star rating control.

    Args:
        selected_rating: The star that is currently selected (1-5). Stars up to
            this number will be rendered as filled (⭐). Others remain outline (☆).
    """

    def star_text(star_idx: int) -> str:
        """Return the correct star emoji for a given index."""
        return "⭐" if star_idx <= selected_rating else "☆"

    # Build 5 columns, one per star
    columns = []
    for i in range(1, 6):
        columns.append({
            "type": "Column",
            "width": "auto",
            "items": [{
                "type": "ActionSet",
                "actions": [{
                    "type": "Action.Submit",
                    "title": star_text(i),
                    "data": {
                        "rating": i,
                        "action": "submit_rating"
                    },
                    # Make the star a bit larger for better UX
                    "style": "default"
                }]
            }]
        })

    # Main card structure
    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
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
                "columns": columns
            },
            {
                "type": "Input.Text",
                "id": "comment",
                "placeholder": "Any suggestions for improvement? (optional)",
                "isMultiline": True
            }
        ],
        "actions": [
            # Left button – Later
            {
                "type": "Action.Submit",
                "title": "Later",
                "data": {
                    "action": "dismiss_feedback"
                }
            },
            # Right button – Provide Feedback
            {
                "type": "Action.Submit",
                "title": "Provide Feedback",
                "style": "positive",
                "data": {
                    "action": "submit_feedback",
                    "rating": selected_rating if selected_rating else 0
                }
            }
        ]
    }

    return card 