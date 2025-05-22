# hrbot/api/__main__.py
"""
Package entry-point.

`python -m hrbot.api` ➜ starts Uvicorn with the FastAPI app declared in
`hrbot.api.app`.

All heavyweight initialisation (vector-store warm-up, etc.) is handled by the
lifespan context inside `app.py`, so we only need to start the server.
"""

from __future__ import annotations

import uvicorn
from hrbot.config.settings import settings


def main() -> None:  
    """Boot Uvicorn with sane defaults taken from settings."""
    uvicorn.run(
        "hrbot.api.app:app",          # dotted-path import
        host=getattr(settings, "host", "0.0.0.0"),
        port=getattr(settings, "port", 8000),
        reload=settings.debug,        # hot-reload in dev
        log_level="debug" if settings.debug else "info",
    )


if __name__ == "__main__": 
    main()
