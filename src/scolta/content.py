"""Content DTOs and the content-source protocol.

Ports ``Tag1\\Scolta\\Export\\ContentItem``, ``Content\\TrackerRecord`` and
``Content\\ContentSourceInterface``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from urllib.parse import urlsplit


@dataclass
class ContentItem:
    """A single content item to be exported for Pagefind indexing.

    Platform adapters construct these from their native entity/post/model
    objects. The exporter handles cleaning, HTML generation and file writing.

    ``url`` is always stored as a relative path: an absolute URL is stripped to
    path?query#fragment so the index is portable across environments
    (DDEV -> production), matching the PHP constructor's behaviour.
    """

    id: str
    title: str
    body_html: str
    url: str
    date: str
    site_name: str = ""
    language: str = "en"
    filters: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    sortable: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Strip scheme and host so the baked-in URL works on any domain.
        if "://" in self.url:
            parts = urlsplit(self.url)
            url = parts.path or "/"
            if parts.query:
                url += "?" + parts.query
            if parts.fragment:
                url += "#" + parts.fragment
            self.url = url

    def clone_with(self, **overrides) -> ContentItem:
        """Return a copy with specific fields overridden.

        Use this instead of constructing a new ContentItem from scratch when
        modifying an existing item — it carries all fields forward and only
        replaces what is explicitly provided.
        """
        return replace(self, **overrides)


@dataclass(frozen=True)
class TrackerRecord:
    """A single change-tracker record.

    Platform adapters populate their tracker tables with these when content is
    created, updated, or deleted.
    """

    ACTION_INDEX = "index"
    ACTION_DELETE = "delete"

    content_id: str = ""
    content_type: str = ""
    action: str = ACTION_INDEX
    changed_at: datetime | None = None


class ContentSource(ABC):
    """Protocol for platform-specific content sources.

    Each platform adapter implements this to enumerate content from its native
    storage. The indexing pipeline calls these methods; results pass to the
    exporter for HTML generation and Pagefind indexing.
    """

    @abstractmethod
    def get_published_content(self, options: dict | None = None) -> Iterable[ContentItem]:
        """Yield all published content items for full reindexing."""

    @abstractmethod
    def get_changed_content(self) -> Iterable[ContentItem]:
        """Yield only items changed since the last index."""

    @abstractmethod
    def get_deleted_ids(self) -> list[str]:
        """Return IDs of content deleted since the last index."""

    @abstractmethod
    def clear_tracker(self) -> None:
        """Mark all tracked changes as processed after a successful build."""

    @abstractmethod
    def get_total_count(self, options: dict | None = None) -> int:
        """Total count of published content items."""

    @abstractmethod
    def get_pending_count(self) -> int:
        """Count of items pending reindexing."""
