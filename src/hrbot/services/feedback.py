import logging
import json
import os
from datetime import datetime, timezone
import uuid

logger = logging.getLogger(__name__)

# In production, this should be a database instead of a file
FEEDBACK_FILE = "data/feedback.json"

def _ensure_feedback_file():
    """Make sure the feedback file exists"""
    os.makedirs(os.path.dirname(FEEDBACK_FILE), exist_ok=True)
    if not os.path.exists(FEEDBACK_FILE):
        with open(FEEDBACK_FILE, "w") as f:
            json.dump([], f)

def save_feedback(user_id, session_id, rating, comment="", ):
    """Save user feedback to the JSON file.
    
    Args:
        user_id: The user identifier
        rating: Numeric rating (1-5)
        comment: Optional feedback text
    """
    _ensure_feedback_file()
    
    try:
        # Read existing feedback
        with open(FEEDBACK_FILE, "r") as f:
            try:
                feedback_data = json.load(f)
            except json.JSONDecodeError:
                feedback_data = []
        
        # Add new feedback
        feedback_data.append({
            "id": uuid.uuid4(),
            "bot_name": "hrbot",
            "env": "production",
            "channel": "teams",
            "user_id": user_id,
            "session_id": session_id,
            "rate": rating,
            "feedback_comment": comment,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Write back to file
        with open(FEEDBACK_FILE, "w") as f:
            json.dump(feedback_data, f, indent=2)
            
        logger.info(f"Saved feedback for user {user_id}: {rating}/5")
        return True
    except Exception as e:
        logger.error(f"Error saving feedback: {str(e)}")
        return False

def get_feedback_stats():
    """Get statistics about saved feedback.
    
    Returns:
        dict: Statistics about the feedback
    """
    _ensure_feedback_file()
    
    try:
        # Read existing feedback
        with open(FEEDBACK_FILE, "r") as f:
            try:
                feedback_data = json.load(f)
            except json.JSONDecodeError:
                feedback_data = []
        
        # Count by rating
        counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        total_ratings = 0
        sum_ratings = 0
        
        for entry in feedback_data:
            rating = entry.get("rating")
            if rating in counts:
                counts[rating] += 1
                total_ratings += 1
                sum_ratings += rating
        
        # Calculate average
        average = sum_ratings / total_ratings if total_ratings > 0 else 0
        
        return {
            "total_feedback": total_ratings,
            "average_rating": round(average, 1),
            "feedback_count_by_rating": counts
        }
    except Exception as e:
        logger.error(f"Error getting feedback stats: {str(e)}")
        return {
            "total_feedback": 0,
            "average_rating": 0,
            "feedback_count_by_rating": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        }