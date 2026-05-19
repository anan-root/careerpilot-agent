"""Stable ID helpers for crawler fallback identifiers."""

from __future__ import annotations

import hashlib


def stable_job_id(prefix: str, *parts: object, length: int = 12) -> str:
    """Build a stable crawler job id from available listing fields."""
    raw = "|".join(str(part or "").strip() for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"
