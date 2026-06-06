"""Pick the best Claude models from the LiteLLM proxy (port of AmazeeModelResolver)."""

from __future__ import annotations


class AmazeeModelResolver:
    def __init__(self, client) -> None:
        self.client = client

    def resolve(self, litellm_api_url: str, litellm_token: str) -> dict:
        models = self.client.get_available_models(litellm_api_url, litellm_token)
        names = [
            m["model_name"]
            for m in models
            if isinstance(m, dict) and isinstance(m.get("model_name"), str)
        ]
        return {
            "ai_model": self.pick_highest_version(names, "sonnet"),
            "ai_expansion_model": self.pick_highest_version(names, "haiku"),
        }

    def pick_highest_version(self, names: list[str], family: str) -> str | None:
        best = None
        best_version: list[int] = []
        for name in names:
            if family.lower() not in name.lower():
                continue
            version = self._extract_version(name)
            if self._compare(version, best_version) > 0:
                best = name
                best_version = version
        return best

    @staticmethod
    def _extract_version(name: str) -> list[int]:
        return [int(seg) for seg in name.split("-") if seg.isdigit()]

    @staticmethod
    def _compare(a: list[int], b: list[int]) -> int:
        for i in range(max(len(a), len(b))):
            diff = (a[i] if i < len(a) else 0) - (b[i] if i < len(b) else 0)
            if diff != 0:
                return diff
        return 0
