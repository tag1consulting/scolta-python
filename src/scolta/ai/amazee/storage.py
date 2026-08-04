"""Credential storage abstraction (port of ConfigStorageInterface)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .connection_source import AmazeeConnectionSource


class ConfigStorage(ABC):
    @abstractmethod
    def store(self, litellm_token: str, litellm_api_url: str, region: str) -> None: ...

    @abstractmethod
    def load(self) -> dict | None:
        """Return {'litellm_token','litellm_api_url','region'} or None."""

    @abstractmethod
    def clear(self) -> None: ...


class ProvenanceAwareConfigStorage(ConfigStorage):
    """A credential store that can also record how the connection was made.

    Kept separate from :class:`ConfigStorage` so existing implementations keep
    working untouched: adopting provenance is opting in to this sub-interface,
    not a change to ``store()``'s signature.

    :class:`AmazeeTrialProvisioner` and :class:`AmazeeAccountUpgrader` record the
    connection source through this interface when the store they were given
    implements it, and skip the record when it does not. A store that does not
    implement it reports no provenance, which is honest: nothing then knows how
    the credentials were obtained.

    Implementations MUST drop the recorded source in ``clear()``, so
    disconnecting does not leave a stale provenance to be paired with the next
    connection.
    """

    @abstractmethod
    def store_connection_source(self, source: AmazeeConnectionSource) -> None:
        """Record which operator action produced the credentials just stored."""

    @abstractmethod
    def load_connection_source(self) -> AmazeeConnectionSource | None:
        """The recorded connection source, or ``None`` when none was recorded.

        ``None`` is the correct answer for credentials stored before provenance
        was recorded, and for a store that has been cleared. Callers must report
        it as "not recorded" and must not substitute a guess.
        """
