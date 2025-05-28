from __future__ import annotations

import asyncio, re, textwrap
from typing import AsyncGenerator, Iterator

PARA_RE  = re.compile(r"(?:\r?\n){2,}")          # blank line = paragraph break
END_PUNC = re.compile(r"[.!?][\"')\]]?\s*$")     # end-of-sentence heuristic
TOKEN_RE = re.compile(r"(\s+)")                  # keep whitespace tokens


def _paragraphs(text: str) -> Iterator[str]:
    """Yield paragraphs *including* trailing blank lines."""
    start = 0
    for m in PARA_RE.finditer(text):
        yield text[start : m.end()]
        start = m.end()
    if start < len(text):
        yield text[start:]


async def sentence_chunks(
    text: str,
    *,
    avg_cps: int  = 25,          # “characters / second” target
    throttle: int = 1,           # Teams → 1 update / s
    max_len: int = 400,          # absolute emergency cut-off
) -> AsyncGenerator[str, None]:
    """Sentence- & paragraph-aware streamer that preserves markdown."""
    budget = avg_cps * throttle

    for para in _paragraphs(text):
        buf: list[str] = []
        cur_len = 0

        for tok in TOKEN_RE.split(para):          # keep whitespace tokens
            buf.append(tok)
            cur_len += len(tok)

            flush_now = (
                (cur_len >= budget and END_PUNC.search(tok)) or cur_len >= max_len
            )
            if flush_now:
                yield "".join(buf)
                buf.clear()
                cur_len = 0
                await asyncio.sleep(0)            # cooperative

        if buf:                                  # remainder of the paragraph
            yield "".join(buf)
            await asyncio.sleep(0)

    # final micro-sleep so caller can finish cleanly
    await asyncio.sleep(0)
