"""The two policy invariants, asserted where they are decided.

**A — no default provider.** Nothing ships with an AI provider selected.
``ai_provider`` is empty until somebody chooses one, and while it is empty AI is
off: search still works, no provider is assumed, and Anthropic in particular is
not silently assumed.

**B — Amazee is never auto-enabled.** No Amazee credential is provisioned and no
outbound Amazee call is made on any request, cron, install or activation path
for a site that did not opt in. The one automatic activity permitted is
re-resolving gateway model names against the key already on disk, which only a
site that already connected Amazee can reach.

Every Amazee transport here fails the test if it is called, so an unexpected
outbound call is a hard failure naming the endpoint rather than a swallowed
transport error.

Mirrors ``tests/AiProvider/Amazee/ManualProviderAndOptInTest.php`` in
scolta-php: the three cores share one contract, and this is where Python is held
to it.
"""

from __future__ import annotations

import httpx
import pytest

from scolta.ai.amazee import (
    AmazeeAccountUpgrader,
    AmazeeClient,
    AmazeeConnectionSource,
    AmazeeTrialProvisioner,
    AutoProvisioner,
    ConfigStorage,
    ProvenanceAwareConfigStorage,
)
from scolta.ai.client import AiClient
from scolta.ai.service import AiServiceAdapter
from scolta.config import ScoltaConfig
from scolta.exceptions import ApiKeyMissingException
from scolta.health import HealthChecker


class _MemoryStorage(ConfigStorage):
    """A store with nowhere to record provenance, like a pre-1.2.0 adapter."""

    def __init__(self) -> None:
        self.stored: dict | None = None

    def store(self, litellm_token: str, litellm_api_url: str, region: str) -> None:
        self.stored = {
            "litellm_token": litellm_token,
            "litellm_api_url": litellm_api_url,
            "region": region,
        }

    def load(self) -> dict | None:
        return self.stored

    def clear(self) -> None:
        self.stored = None


class _ProvenanceStorage(ProvenanceAwareConfigStorage):
    """An in-memory store that records provenance, like a real adapter's."""

    def __init__(self) -> None:
        self.stored: dict | None = None
        self.source: AmazeeConnectionSource | None = None

    def store(self, litellm_token: str, litellm_api_url: str, region: str) -> None:
        self.stored = {
            "litellm_token": litellm_token,
            "litellm_api_url": litellm_api_url,
            "region": region,
        }

    def load(self) -> dict | None:
        return self.stored

    def clear(self) -> None:
        self.stored = None
        self.source = None

    def store_connection_source(self, source: AmazeeConnectionSource) -> None:
        self.source = source

    def load_connection_source(self) -> AmazeeConnectionSource | None:
        return self.source


def _fail_on_call_client(attempted: list[str]) -> AmazeeClient:
    def handler(request: httpx.Request) -> httpx.Response:
        attempted.append(request.url.path)
        raise AssertionError(f"no outbound Amazee call expected, got {request.url.path}")

    return AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))


# -- Invariant A: no default provider -----------------------------------------


def test_config_ships_with_no_provider_selected():
    assert ScoltaConfig().ai_provider == ""
    assert ScoltaConfig.from_dict({}).ai_provider == ""


def test_an_already_chosen_provider_is_preserved():
    # Going-forward only: a site that already picked a provider keeps it.
    for chosen in ("anthropic", "openai", "amazee"):
        assert ScoltaConfig.from_dict({"ai_provider": chosen}).ai_provider == chosen


def test_unconfigured_install_makes_no_ai_call_on_any_operation():
    builds = []

    class _Adapter(AiServiceAdapter):
        def _create_client(self):
            builds.append(1)
            raise AssertionError("an AI client was built with no provider selected")

    adapter = _Adapter(ScoltaConfig.from_dict({}))

    for operation in ("expand_query", "summarize", "follow_up"):
        with pytest.raises(ApiKeyMissingException):
            adapter.message_for_operation(operation, "sys", "user", 512)

    assert builds == []


def test_ai_client_refuses_to_assume_a_provider():
    with pytest.raises(ValueError, match="No AI provider selected"):
        AiClient({"api_key": "sk-test"})


def test_health_reports_ai_off_rather_than_assuming_anthropic(tmp_path):
    result = HealthChecker(ScoltaConfig.from_dict({}), str(tmp_path), None, None).check()

    assert result["ai_provider"] == ""
    assert result["ai_provider_selected"] is False
    assert result["ai_configured"] is False
    assert result["ai_usable"] is False


def test_key_without_a_provider_is_still_ai_off(tmp_path):
    # The case a coalescing default used to hide: a key set before anybody chose
    # a provider looked like a working Anthropic install.
    config = ScoltaConfig.from_dict({"ai_api_key": "sk-env"})
    result = HealthChecker(config, str(tmp_path), None, None).check()

    assert result["ai_provider"] == ""
    assert result["ai_provider_selected"] is False
    assert result["ai_usable"] is False


# -- Invariant B: Amazee is never auto-enabled --------------------------------


def test_ensure_ai_available_never_mints_and_never_calls_out():
    attempted: list[str] = []
    storage = _MemoryStorage()
    reported: list[tuple[str, str]] = []

    result = AutoProvisioner.ensure_ai_available(
        storage,
        on_models_resolved=lambda m, e: reported.append((m, e)),
        client=_fail_on_call_client(attempted),
        has_resolved_models=lambda: False,
    )

    assert result is False
    assert storage.load() is None
    assert reported == []
    assert attempted == []


def test_ensure_ai_available_with_an_explicit_key_touches_nothing():
    attempted: list[str] = []
    storage = _MemoryStorage()

    assert (
        AutoProvisioner.ensure_ai_available(
            storage, has_explicit_api_key=True, client=_fail_on_call_client(attempted)
        )
        is False
    )
    assert attempted == []
    assert storage.load() is None


def test_self_heal_uses_the_stored_key_and_does_not_mint():
    # The only automatic Amazee activity the policy permits, reachable only for
    # a site whose operator already connected.
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/model/info":
            return httpx.Response(200, json={"data": [{"model_name": "claude-sonnet-4-6"}]})
        raise AssertionError(f"unexpected call to {request.url.path}")

    client = AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    storage = _MemoryStorage()
    storage.store("stored-tok", "https://gateway.amazee.ai", "us-east")

    AutoProvisioner.ensure_ai_available(storage, client=client, has_resolved_models=lambda: False)

    assert paths == ["/model/info"]
    assert storage.load()["litellm_token"] == "stored-tok"


# -- Provenance: recorded at connect time, never guessed ----------------------


def _scripted_client(routes: dict[str, dict], recorded: list[bytes] | None = None) -> AmazeeClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if recorded is not None:
            recorded.append(request.content)
        return httpx.Response(200, json=routes[request.url.path])

    return AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_demo_provision_records_demo_provenance_with_no_email():
    storage = _ProvenanceStorage()
    bodies: list[bytes] = []
    client = _scripted_client(
        {
            "/auth/generate-trial-access": {
                "litellm_token": "demo-tok",
                "litellm_api_url": "https://gateway.amazee.ai",
                "region": "us-east",
            }
        },
        bodies,
    )

    AmazeeTrialProvisioner(client, storage).provision()

    assert storage.load_connection_source() is AmazeeConnectionSource.DEMO
    # No email is sent: trying the demo costs the operator no input.
    assert b'"email": ""' in bodies[0] or b'"email":""' in bodies[0]


def test_account_sign_in_records_account_provenance():
    storage = _ProvenanceStorage()
    storage.store("demo-tok", "https://gateway.amazee.ai", "us-east")
    storage.store_connection_source(AmazeeConnectionSource.DEMO)

    client = _scripted_client(
        {
            "/private-ai-keys": {
                "litellm_token": "account-tok",
                "litellm_api_url": "https://ch.amazee.ai",
                "region": "ch",
            }
        }
    )

    AmazeeAccountUpgrader(client, storage).upgrade("session", "ch")

    assert storage.load_connection_source() is AmazeeConnectionSource.ACCOUNT
    assert storage.load()["litellm_token"] == "account-tok"


def test_provenance_unaware_store_connects_and_records_nothing():
    storage = _MemoryStorage()
    client = _scripted_client(
        {
            "/auth/generate-trial-access": {
                "litellm_token": "tok",
                "litellm_api_url": "https://gateway.amazee.ai",
                "region": "us-east",
            }
        }
    )

    AmazeeTrialProvisioner(client, storage).provision()

    assert storage.load()["litellm_token"] == "tok"
    assert not isinstance(storage, ProvenanceAwareConfigStorage)


def test_clearing_credentials_also_clears_provenance():
    # A stale mark left behind would be paired with the next connection, which
    # is a guess wearing a recorded fact's clothes.
    storage = _ProvenanceStorage()
    storage.store("tok", "https://gateway.amazee.ai", "us-east")
    storage.store_connection_source(AmazeeConnectionSource.DEMO)

    storage.clear()

    assert storage.load_connection_source() is None
    assert storage.load() is None


def test_no_connection_source_label_implies_automatic_provisioning():
    for source in AmazeeConnectionSource:
        for banned in ("auto", "automatic", "free trial"):
            assert banned not in source.value.lower()
            assert banned not in source.label().lower()
