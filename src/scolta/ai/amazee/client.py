"""HTTP client for the Amazee.ai control plane (port of ``AmazeeClient``, httpx)."""

from __future__ import annotations

import httpx

from .exceptions import AmazeeApiException
from .results import ProvisioningResult, UpgradeResult

DEFAULT_BASE_URL = "https://api.amazee.ai"
_TIMEOUT = 15


class AmazeeClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, http_client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = http_client if http_client is not None else httpx.Client()

    def provision_trial(self, email: str = "") -> ProvisioningResult:
        body = self._post("/auth/generate-trial-access", {"email": email})
        creds = body["key"] if isinstance(body.get("key"), dict) else body
        token = creds.get("litellm_token")
        api_url = creds.get("litellm_api_url")
        region = creds.get("region", "default")
        if not isinstance(token, str) or token == "" or not isinstance(api_url, str) or api_url == "":
            raise AmazeeApiException(
                "Amazee.ai trial provisioning response missing litellm_token or litellm_api_url."
            )
        return ProvisioningResult.make_success(token, api_url, region)

    def request_verification_code(self, email: str) -> None:
        self._post("/auth/validate-email", {"email": email})

    def sign_in(self, email: str, code: str) -> str:
        body = self._post("/auth/sign-in", {"email": email, "code": code})
        token_field = body.get("token")
        if isinstance(token_field, dict):
            session_token = token_field.get("access_token")
        else:
            session_token = token_field if token_field is not None else body.get("access_token")
        if not isinstance(session_token, str) or session_token == "":
            raise AmazeeApiException("Amazee.ai sign-in response missing session token.")
        return session_token

    def list_regions(self, session_token: str) -> list:
        body = self._get("/regions", session_token)
        return body.get("regions", body) if isinstance(body, dict) else body

    def create_private_key(self, session_token: str, region_id: str) -> UpgradeResult:
        body = self._post("/private-ai-keys", {"region_id": region_id}, session_token)
        token = body.get("litellm_token")
        api_url = body.get("litellm_api_url")
        region = body.get("region", region_id)
        if not isinstance(token, str) or token == "" or not isinstance(api_url, str) or api_url == "":
            raise AmazeeApiException(
                "Amazee.ai private key creation response missing litellm_token or litellm_api_url."
            )
        return UpgradeResult.make_success(token, api_url, region)

    def get_available_models(self, litellm_api_url: str, litellm_token: str) -> list:
        url = litellm_api_url.rstrip("/") + "/model/info"
        try:
            response = self._http.get(
                url,
                headers={"Authorization": f"Bearer {litellm_token}", "Accept": "application/json"},
                timeout=_TIMEOUT,
            )
            if not (200 <= response.status_code < 300):
                return []
            body = response.json()
            data = body.get("data")
            return data if isinstance(data, list) else []
        except (httpx.HTTPError, ValueError):
            return []

    def validate_token(self, litellm_token: str, litellm_api_url: str) -> None:
        url = litellm_api_url.rstrip("/") + "/auth/me"
        try:
            response = self._http.get(
                url,
                headers={"Authorization": f"Bearer {litellm_token}", "Accept": "application/json"},
                timeout=_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise AmazeeApiException(f"Amazee.ai token validation request failed: {exc}") from exc
        if not (200 <= response.status_code < 300):
            raise AmazeeApiException(
                f"Amazee.ai token validation failed with HTTP {response.status_code}.",
                response.status_code,
            )

    # -- internal --

    def _post(self, path: str, payload: dict, bearer: str | None = None) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if bearer is not None:
            headers["Authorization"] = f"Bearer {bearer}"
        try:
            response = self._http.post(self.base_url + path, json=payload, headers=headers, timeout=_TIMEOUT)
        except httpx.HTTPError as exc:
            raise AmazeeApiException(f"Amazee.ai API request to {path} failed: {exc}") from exc
        return self._decode(path, response)

    def _get(self, path: str, bearer: str | None = None) -> dict:
        headers = {"Accept": "application/json"}
        if bearer is not None:
            headers["Authorization"] = f"Bearer {bearer}"
        try:
            response = self._http.get(self.base_url + path, headers=headers, timeout=_TIMEOUT)
        except httpx.HTTPError as exc:
            raise AmazeeApiException(f"Amazee.ai API request to {path} failed: {exc}") from exc
        return self._decode(path, response)

    @staticmethod
    def _decode(path: str, response: httpx.Response) -> dict:
        status = response.status_code
        text = response.text
        if not (200 <= status < 300):
            message = f"Amazee.ai API returned HTTP {status} for {path}."
            try:
                data = response.json()
                if isinstance(data, dict) and data.get("detail"):
                    message += " " + str(data["detail"])
                elif isinstance(data, dict) and data.get("message"):
                    message += " " + str(data["message"])
            except ValueError:
                pass
            raise AmazeeApiException(message, status)
        if text == "":
            return {}
        try:
            return response.json() or {}
        except ValueError as exc:
            raise AmazeeApiException(
                f"Amazee.ai API returned malformed JSON from {path}: {exc}", status
            ) from exc
