"""Ported from tests/AiProvider/Amazee/* (1:1 intent), mocking the httpx transport."""

import httpx
import pytest

from scolta.ai.amazee import (
    AmazeeAccountUpgrader,
    AmazeeApiException,
    AmazeeBudgetExceededException,
    AmazeeClient,
    AmazeeModelResolver,
    AmazeeTrialProvisioner,
    AutoProvisioner,
    BudgetAwareProviderDecorator,
    ConfigStorage,
    ProvisioningResult,
)


class MemoryStorage(ConfigStorage):
    def __init__(self):
        self._data = None

    def store(self, litellm_token, litellm_api_url, region):
        self._data = {"litellm_token": litellm_token, "litellm_api_url": litellm_api_url, "region": region}

    def load(self):
        return self._data

    def clear(self):
        self._data = None


def _client(routes):
    """routes: dict[(method, path)] -> (status, json_or_None)."""
    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        if key not in routes:
            return httpx.Response(404, json={"detail": "not found"})
        status, body = routes[key]
        return httpx.Response(status, json=body if body is not None else {})

    return AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))


# -- exceptions ---------------------------------------------------------------


def test_api_exception_status_code():
    exc = AmazeeApiException("boom", 503)
    assert exc.get_status_code() == 503
    assert "boom" in str(exc)


def test_budget_exception_message_and_cause():
    cause = RuntimeError("orig")
    exc = AmazeeBudgetExceededException(cause)
    assert "budget has been exceeded" in str(exc).lower()
    assert exc.__cause__ is cause


# -- client: provisioning -----------------------------------------------------


def test_provision_trial_nested_key_format():
    c = _client({("POST", "/auth/generate-trial-access"):
                 (200, {"key": {"litellm_token": "tok", "litellm_api_url": "https://llm.x", "region": "us"}})})
    r = c.provision_trial("a@b.com")
    assert r.success is True
    assert r.litellm_token == "tok"
    assert r.litellm_api_url == "https://llm.x"
    assert r.region == "us"


def test_provision_trial_flat_format_default_region():
    c = _client({("POST", "/auth/generate-trial-access"):
                 (200, {"litellm_token": "t", "litellm_api_url": "https://llm.y"})})
    r = c.provision_trial()
    assert r.litellm_token == "t"
    assert r.region == "default"


def test_provision_trial_missing_creds_raises():
    c = _client({("POST", "/auth/generate-trial-access"): (200, {"key": {"region": "us"}})})
    with pytest.raises(AmazeeApiException, match="missing litellm_token"):
        c.provision_trial()


def test_provision_trial_http_error_includes_detail():
    c = _client({("POST", "/auth/generate-trial-access"): (400, {"detail": "bad email"})})
    with pytest.raises(AmazeeApiException) as ei:
        c.provision_trial()
    assert ei.value.get_status_code() == 400
    assert "bad email" in str(ei.value)


# -- client: upgrade flow -----------------------------------------------------


def test_request_verification_code():
    c = _client({("POST", "/auth/validate-email"): (200, {})})
    c.request_verification_code("a@b.com")  # no exception


def test_sign_in_nested_token():
    c = _client({("POST", "/auth/sign-in"): (200, {"token": {"access_token": "sess"}})})
    assert c.sign_in("a@b.com", "123456") == "sess"


def test_sign_in_flat_token():
    c = _client({("POST", "/auth/sign-in"): (200, {"access_token": "sess2"})})
    assert c.sign_in("a@b.com", "123456") == "sess2"


def test_sign_in_missing_token_raises():
    c = _client({("POST", "/auth/sign-in"): (200, {})})
    with pytest.raises(AmazeeApiException, match="missing session token"):
        c.sign_in("a@b.com", "123456")


def test_list_regions():
    c = _client({("GET", "/regions"): (200, {"regions": [{"id": "us", "name": "US", "url": "https://us"}]})})
    regions = c.list_regions("sess")
    assert regions[0]["id"] == "us"


def test_create_private_key():
    c = _client({("POST", "/private-ai-keys"):
                 (200, {"litellm_token": "pk", "litellm_api_url": "https://priv", "region": "eu"})})
    r = c.create_private_key("sess", "eu")
    assert r.success is True
    assert r.litellm_token == "pk"
    assert r.region == "eu"


# -- client: model info / validation ------------------------------------------


def test_get_available_models_returns_data():
    url = "https://llm.x"

    def handler(request):
        if request.url.path == "/model/info":
            return httpx.Response(200, json={"data": [{"model_name": "claude-sonnet-4-6"}]})
        return httpx.Response(404)

    c = AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    models = c.get_available_models(url, "tok")
    assert models == [{"model_name": "claude-sonnet-4-6"}]


def test_get_available_models_empty_on_error():
    c = AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    assert c.get_available_models("https://llm.x", "tok") == []


def test_validate_token_ok_and_failure():
    ok = AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    ok.validate_token("tok", "https://llm.x")  # no exception
    bad = AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    with pytest.raises(AmazeeApiException):
        bad.validate_token("tok", "https://llm.x")


# -- model resolver -----------------------------------------------------------


def test_model_resolver_picks_highest_versions():
    class FakeClient:
        def get_available_models(self, url, token):
            return [
                {"model_name": "claude-sonnet-4-5"},
                {"model_name": "claude-sonnet-4-6"},
                {"model_name": "claude-3-5-haiku-20241022"},
                {"model_name": "claude-haiku-4-5"},
            ]

    resolved = AmazeeModelResolver(FakeClient()).resolve("u", "t")
    assert resolved["ai_model"] == "claude-sonnet-4-6"
    assert resolved["ai_expansion_model"] == "claude-haiku-4-5"


def test_pick_highest_version_none_when_no_match():
    assert AmazeeModelResolver(None).pick_highest_version(["claude-haiku-4-5"], "sonnet") is None


# -- trial provisioner --------------------------------------------------------


def test_provisioner_stores_and_resolves_models():
    routes = {
        ("POST", "/auth/generate-trial-access"):
            (200, {"litellm_token": "tok", "litellm_api_url": "https://llm.x", "region": "us"}),
    }

    def handler(request):
        key = (request.method, request.url.path)
        if key in routes:
            return httpx.Response(*[routes[key][0]], json=routes[key][1])
        if request.url.path == "/model/info":
            return httpx.Response(200, json={"data": [{"model_name": "claude-sonnet-4-6"},
                                                       {"model_name": "claude-haiku-4-5"}]})
        return httpx.Response(404)

    client = AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    storage = MemoryStorage()
    result = AmazeeTrialProvisioner(client, storage, None, AmazeeModelResolver(client)).provision("a@b.com")
    assert result.success is True
    assert result.ai_model == "claude-sonnet-4-6"
    assert result.ai_expansion_model == "claude-haiku-4-5"
    assert storage.load()["litellm_token"] == "tok"


def test_provisioner_skips_existing_provider():
    storage = MemoryStorage()
    p = AmazeeTrialProvisioner(_client({}), storage, has_existing_provider=lambda: True)
    result = p.provision()
    assert result.status == ProvisioningResult.STATUS_SKIPPED_EXISTING_PROVIDER
    assert storage.load() is None  # no API call, nothing stored


# -- account upgrader ---------------------------------------------------------


def test_account_upgrader_flow():
    routes = {
        ("POST", "/auth/validate-email"): (200, {}),
        ("POST", "/auth/sign-in"): (200, {"token": {"access_token": "sess"}}),
        ("GET", "/regions"): (200, {"regions": [{"id": "eu", "name": "EU", "url": "https://eu"}]}),
        ("POST", "/private-ai-keys"): (200, {"litellm_token": "pk", "litellm_api_url": "https://priv", "region": "eu"}),
    }
    client = _client(routes)
    storage = MemoryStorage()
    up = AmazeeAccountUpgrader(client, storage)
    up.request_verification_code("a@b.com")
    sess = up.sign_in("a@b.com", "123456")
    assert sess == "sess"
    assert up.list_regions(sess)[0]["id"] == "eu"
    result = up.upgrade(sess, "eu")
    assert result.success is True
    assert storage.load()["litellm_token"] == "pk"


# -- auto provisioner ---------------------------------------------------------


def test_auto_provisioner_skips_with_explicit_key():
    storage = MemoryStorage()
    assert AutoProvisioner.ensure_ai_available(storage, has_explicit_api_key=True) is False
    assert storage.load() is None


def test_auto_provisioner_skips_when_already_provisioned():
    storage = MemoryStorage()
    storage.store("t", "u", "r")
    assert AutoProvisioner.ensure_ai_available(storage) is False


def test_auto_provisioner_provisions_and_reports_models():
    def handler(request):
        if request.url.path == "/auth/generate-trial-access":
            return httpx.Response(200, json={"litellm_token": "tok", "litellm_api_url": "https://llm.x", "region": "us"})
        if request.url.path == "/model/info":
            return httpx.Response(200, json={"data": [{"model_name": "claude-sonnet-4-6"}]})
        return httpx.Response(404)

    client = AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    storage = MemoryStorage()
    reported = {}
    ok = AutoProvisioner.ensure_ai_available(
        storage, on_models_resolved=lambda m, e: reported.update({"m": m, "e": e}), client=client
    )
    assert ok is True
    assert storage.load()["litellm_token"] == "tok"
    assert reported["m"] == "claude-sonnet-4-6"


def test_auto_provisioner_returns_false_on_api_error():
    client = AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500, json={}))))
    assert AutoProvisioner.ensure_ai_available(MemoryStorage(), client=client) is False


# -- auto provisioner: reprovision() — the expired-key recovery entry point ----


def test_reprovision_replaces_stored_credentials():
    # Unlike ensure_ai_available(), stored credentials must NOT short-circuit:
    # they are known-bad (expired/revoked) when this path runs.
    def handler(request):
        if request.url.path == "/auth/generate-trial-access":
            return httpx.Response(
                200,
                json={"key": {"litellm_token": "new-tok", "litellm_api_url": "https://trial.amazee.ai", "region": "eu-west"}},
            )
        if request.url.path == "/model/info":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404)

    client = AmazeeClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    storage = MemoryStorage()
    storage.store("expired-tok", "https://trial.amazee.ai", "eu-west")

    assert AutoProvisioner.reprovision(storage, client=client) is True
    assert storage.load()["litellm_token"] == "new-tok"


def test_reprovision_returns_false_on_api_error():
    client = AmazeeClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(500, json={"detail": "Server error."}))
        )
    )
    storage = MemoryStorage()
    storage.store("expired-tok", "https://trial.amazee.ai", "eu-west")

    assert AutoProvisioner.reprovision(storage, client=client) is False
    # The known-bad credentials are already cleared — correct, an empty store
    # lets ensure_ai_available() retry on the next lazy-init pass.
    assert storage.load() is None


# -- budget decorator ---------------------------------------------------------


class _FakeAi:
    def __init__(self, exc=None, result="ok"):
        self.exc = exc
        self.result = result

    def message(self, *a, **k):
        if self.exc:
            raise self.exc
        return self.result

    def conversation(self, *a, **k):
        if self.exc:
            raise self.exc
        return self.result


def test_budget_decorator_passes_through():
    d = BudgetAwareProviderDecorator(_FakeAi(result="hi"))
    assert d.message("s", "u") == "hi"


def test_budget_decorator_converts_budget_error():
    d = BudgetAwareProviderDecorator(_FakeAi(exc=RuntimeError("Budget has been exceeded!")))
    with pytest.raises(AmazeeBudgetExceededException):
        d.message("s", "u")


def test_budget_decorator_walks_cause_chain():
    inner = RuntimeError("Budget has been exceeded!")
    outer = RuntimeError("rate limited")
    outer.__cause__ = inner
    d = BudgetAwareProviderDecorator(_FakeAi(exc=outer))
    with pytest.raises(AmazeeBudgetExceededException):
        d.conversation("s", [])


def test_budget_decorator_reraises_other_errors():
    d = BudgetAwareProviderDecorator(_FakeAi(exc=RuntimeError("network down")))
    with pytest.raises(RuntimeError, match="network down"):
        d.message("s", "u")
