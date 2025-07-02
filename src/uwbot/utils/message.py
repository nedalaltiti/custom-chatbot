# src/hrbot/utils/message.py
"""
Light-weight text helpers that are pure Python / regex based.
"""

import re
from typing import Tuple

# Regex matches one or more greetings + trailing punctuation / spaces
_GREETING_RE = re.compile(
    r"""^(?:\s*
          (hi+|hello+|hey+|h(?:i{2,})|good\s+(?:morning|afternoon|evening))
          [\s,!.:-]*
        )+                      # ≥1 greeting tokens
        (?P<rest>.*)$           # everything after the greeting(s)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Simple pattern to detect if message is ONLY a greeting (including extended ones)
_PURE_GREETING_RE = re.compile(
    r"""^
        \s*
        (hi{1,10}|hello{1,5}|hey{1,5}|good\s+(?:morning|afternoon|evening))
        [\s,!.:-]*
        $
    """,
    re.IGNORECASE | re.VERBOSE,
)

def split_greeting(msg: str) -> Tuple[bool, str]:
    """
    Returns (greet_only, remainder).

    greet_only → the message contained nothing but a greeting.
    """
    m = _GREETING_RE.match(msg.strip())
    if not m:
        return False, msg
    remainder = m.group("rest").strip()
    return remainder == "", remainder

def is_pure_greeting(msg: str) -> bool:
    """
    Check if message is ONLY a greeting (including extended ones like "hiiii", "heyy").
    
    This is more reliable than split_greeting for determining if we should just 
    acknowledge without additional helper text.
    
    Examples:
    - "hi" → True
    - "hiiii" → True  
    - "heyy" → True
    - "hello!!!" → True
    - "hi, how are you?" → False
    - "hey there" → False
    - "hey, what about leaves?" → False
    """
    return bool(_PURE_GREETING_RE.match(msg.strip()))
