# src/hrbot/utils/message.py
"""
Light-weight text helpers that are pure Python / regex based.
"""

import re
from typing import Tuple

# Regex matches one or more greetings + trailing punctuation / spaces
_GREETING_RE = re.compile(
    r"""^(?:\s*
          (hi|hello|hey|h(?:i+)|good\s+(?:morning|afternoon|evening))
          [\s,!.:-]*
        )+                      # ≥1 greeting tokens
        (?P<rest>.*)$           # everything after the greeting(s)
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
