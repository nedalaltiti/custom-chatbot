"""
Helpers for breaking a long LLM answer into visible, human-friendly
chunks that respect Teams’ 1-request-per-second throttling.

The key rule: **every chunk you yield must be *appended* to the overall
buffer** – the adapter will prepend whatever has already been shown
so far before sending the next typing update.
"""

from __future__ import annotations

import asyncio
import re
from typing import AsyncGenerator


async def sentence_chunks(
    text: str,
    *,
    min_len: int = 25,
    max_len: int = 120,
) -> AsyncGenerator[str, None]:
    """
    Yield chunks that (1) finish a sentence if possible and
    (2) are big enough that we don’t spam the API faster than 1 Hz.

    ─ `min_len`  – don’t release a chunk until the buffer holds at least
                   this many characters **and** ends with . ? or !.
    ─ `max_len`  – hard-flush if we exceed this length without finding a
                   sentence boundary (very long sentences).
    """
    buf: list[str] = []

    def flush() -> str | None:
        if not buf:
            return None
        out = " ".join(buf) + " "
        buf.clear()
        return out

    for word in text.split():
        buf.append(word)

        too_long = sum(len(w) + 1 for w in buf) >= max_len
        ends_sentence = re.search(r"[.?!]$", buf[-1])

        if (too_long or (ends_sentence and
                         sum(len(w)+1 for w in buf) >= min_len)):
            out = flush()
            if out is not None:
                yield out
                await asyncio.sleep(0)        # co-operative multitask

    # tail
    out = flush()
    if out is not None:
        yield out
        await asyncio.sleep(0)
