from __future__ import annotations

from uuid import uuid4


def new_id(prefix: str) -> str:
    """Return a readable, globally unique identifier."""
    clean = prefix.strip().lower().replace(" ", "-")
    if not clean:
        raise ValueError("identifier prefix cannot be empty")
    return f"{clean}_{uuid4().hex}"
