"""Which operator action produced the stored credentials (port of AmazeeConnectionSource)."""

from __future__ import annotations

from enum import Enum


class AmazeeConnectionSource(str, Enum):
    """Which operator action produced the stored Amazee.ai credentials.

    Recorded at the moment a connection is established, never derived
    afterwards. The distinction was previously guessed from whatever local fact
    an adapter had to hand, which is why it was removed outright: both the trial
    provisioner and the account upgrader persist the same three fields through
    :meth:`ConfigStorage.store`, so nothing in the credential store could tell
    them apart. Recording the fact at its source is what makes the distinction
    reportable again.

    Neither case implies anything automatic. Both are reached only by an
    explicit operator action in an admin UI, or by a developer who set
    ``ai_provider`` to ``amazee`` in code and then ran the provisioning path.

    Storage backends opt in by implementing
    :class:`ProvenanceAwareConfigStorage`. A store that does not — and every
    credential persisted before this release — reports no connection source at
    all, which callers must surface as unknown rather than as a guess.
    """

    #: The operator started the free demo, which needs no email and no account.
    #:
    #: One-time per site: the credit it ships with is not renewed. When it runs
    #: out the operator continues by signing in to an account (:attr:`ACCOUNT`).
    DEMO = "demo"

    #: The operator signed in to an amazee.ai account with their email address.
    #:
    #: The email → verification code → region flow creates or attaches the
    #: account and returns its credentials, which are then persisted. Same flow
    #: whether the account is new or already existed, matching amazee.ai's own
    #: ``ai_provider_amazeeio`` module.
    ACCOUNT = "account"

    def label(self) -> str:
        """A short operator-facing name for this connection, in English.

        No label describes a connection as automatic or as provisioned on the
        operator's behalf, because neither is.
        """
        return {
            AmazeeConnectionSource.DEMO: "Amazee.ai demo",
            AmazeeConnectionSource.ACCOUNT: "Amazee.ai account",
        }[self]
