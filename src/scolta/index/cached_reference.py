"""CachedContentReference marker (port, 1:1).

Yielded by gatherers for entities unchanged since the last build: carries the
metadata needed to rebuild a chunk entry from cached token data, without
loading the entity body.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CachedContentReference:
    entity_key: str
    content_hash: str
    id: str
    url: str
    date: str
    site_name: str
    language: str
    filters: dict
    sortable: dict = field(default_factory=dict)
