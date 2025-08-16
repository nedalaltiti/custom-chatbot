from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Document:
    page_content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def sha256(self) -> str:
        """Stable fingerprint used by `VectorStore` to avoid re-embedding."""
        return hashlib.sha256(self.page_content.encode("utf-8")).hexdigest()