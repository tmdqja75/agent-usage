"""Shared helpers for local agent-source adapters."""

from __future__ import annotations

import hashlib

_FINGERPRINT_SEPARATOR = "\x1f"


def make_fingerprint(*parts: str) -> str:
    """Derive a stable, opaque fingerprint from local source identifiers.

    Adapters must never store a source's raw session/event IDs in normalized
    records. Hashing them here keeps the fingerprint unique and stable for
    deduplication while never exposing the identifier it was built from.
    """
    joined = _FINGERPRINT_SEPARATOR.join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
