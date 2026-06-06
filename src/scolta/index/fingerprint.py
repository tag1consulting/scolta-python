"""Content hashing/fingerprinting for the smart-rebuild cache.

Internal keys only (no cross-language parity); sha256-based.
"""

from __future__ import annotations

import hashlib
import json


def content_hash(item) -> str:
    """Per-item cache key: sha256(url \\0 body_html)."""
    payload = (item.url + "\0" + item.body_html).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compute_fingerprint(items) -> str:
    """Deterministic fingerprint for a set of content items."""
    data = sorted(
        f"{item.id}:{hashlib.sha256(item.body_html.encode('utf-8')).hexdigest()}" for item in items
    )
    return hashlib.sha256(
        ("python-indexer-v1:" + json.dumps(data, separators=(",", ":"))).encode("utf-8")
    ).hexdigest()
