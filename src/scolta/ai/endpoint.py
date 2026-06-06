"""Framework-agnostic AI endpoint orchestration.

Port of ``Tag1\\Scolta\\Http\\AiEndpointHandler``. Validation, caching,
prompt assembly (language/sort/filter instructions), response parsing and
error handling for the expand-query / summarize / follow-up endpoints. The AI
service is duck-typed: any object with get_expand_prompt / get_summarize_prompt
/ get_follow_up_prompt / message / message_for_operation / conversation works.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re

from ..cache import CacheDriver
from ..exceptions import (
    ApiKeyInvalidException,
    ApiKeyMissingException,
    RateLimitException,
)
from ._intent_blocks import FILTER_INTENT_BLOCK, SORT_INTENT_BLOCK
from .enricher import NullEnricher, PromptEnricher

_FENCE_OPEN = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)
_FENCE_CLOSE = re.compile(r"\s*```$")

_DEFAULT_LOGGER = logging.getLogger("scolta.ai")


def _intdiv(a: int, b: int) -> int:
    """PHP intdiv: integer division truncated toward zero."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


class AiEndpointHandler:
    def __init__(
        self,
        ai_service: object,
        cache: CacheDriver,
        generation: int,
        cache_ttl: int,
        max_follow_ups: int,
        prompt_enricher: PromptEnricher | None = None,
        ai_languages: list[str] | None = None,
        logger: object | None = None,
        ai_expand_query: bool = True,
        ai_summarize: bool = True,
        ai_summary_max_tokens: int = 1024,
        expand_primary_weight: float = 0.5,
        sortable_fields: list[str] | None = None,
        sortable_field_descriptions: dict[str, str] | None = None,
        filter_fields: list[str] | None = None,
        filter_field_descriptions: dict[str, str] | None = None,
    ) -> None:
        self.ai_service = ai_service
        self.cache = cache
        self.generation = generation
        self.cache_ttl = cache_ttl
        self.max_follow_ups = max_follow_ups
        self.prompt_enricher = prompt_enricher or NullEnricher()
        self.ai_languages = ai_languages if ai_languages is not None else ["en"]
        self.logger = logger if logger is not None else _DEFAULT_LOGGER
        self.ai_expand_query = ai_expand_query
        self.ai_summarize = ai_summarize
        self.ai_summary_max_tokens = ai_summary_max_tokens
        self.expand_primary_weight = expand_primary_weight
        self.sortable_fields = sortable_fields or []
        self.sortable_field_descriptions = sortable_field_descriptions or {}
        self.filter_fields = filter_fields or []
        self.filter_field_descriptions = filter_field_descriptions or {}

    # -- expand query -------------------------------------------------------

    def handle_expand_query(self, query: str) -> dict:
        if not self.ai_expand_query:
            return {"ok": False, "status": 404, "error": "Feature disabled"}

        query = query.strip()
        if query == "" or len(query) > 500:
            return {"ok": False, "status": 400, "error": "Invalid query"}

        cache_key = self.cache_key("expand", query)
        if self.cache_ttl > 0:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return {"ok": True, "data": cached}

        try:
            system_prompt = self.prompt_enricher.enrich(
                self.ai_service.get_expand_prompt(), "expand_query", {"query": query}
            )
            system_prompt = self._append_language_instruction(system_prompt, "expand_query")
            system_prompt = self._append_sortable_fields_instruction(system_prompt)
            system_prompt = self._append_filter_fields_instruction(system_prompt)

            response = self.ai_service.message_for_operation(
                "expand_query", system_prompt, "Expand this search query: " + query, 512
            )

            parsed = self._parse_expansion_result(response, query)
            payload = {
                "terms": parsed["terms"],
                "expand_primary_weight": self.expand_primary_weight,
            }
            if parsed["sort_hint"] is not None:
                payload["sort_hint"] = parsed["sort_hint"]
            if parsed["subject_terms"] is not None:
                payload["subject_terms"] = parsed["subject_terms"]
            if parsed["filter_hint"] is not None:
                payload["filter_hint"] = parsed["filter_hint"]

            if self.cache_ttl > 0:
                self.cache.set(cache_key, payload, self.cache_ttl)

            return {"ok": True, "data": payload}
        except ApiKeyMissingException:
            return {
                "ok": True,
                "data": {"terms": [query], "expand_primary_weight": self.expand_primary_weight},
            }
        except ApiKeyInvalidException as exc:
            self.logger.error("Scolta query expansion failed: invalid API key: %s", exc)
            return {"ok": False, "status": 401, "error": "AI API key is invalid or expired"}
        except RateLimitException as exc:
            result = {"ok": False, "status": 429, "error": "AI API rate limit reached"}
            if exc.retry_after is not None:
                result["retry_after"] = exc.retry_after
            return result
        except Exception as exc:  # noqa: BLE001 - mirror PHP catch-all degradation
            self.logger.error("Scolta query expansion failed: %s", exc)
            return {"ok": False, "status": 503, "error": "Query expansion unavailable"}

    # -- summarize ----------------------------------------------------------

    def handle_summarize(self, query: str, context: str) -> dict:
        if not self.ai_summarize:
            return {"ok": False, "status": 404, "error": "Feature disabled"}

        query = query.strip()
        context = context.strip()

        if query == "" or len(query) > 500:
            return {"ok": False, "status": 400, "error": "Invalid query"}
        # Client truncates to 49,000; this is a safety net.
        if context == "" or len(context) > 100000:
            return {"ok": False, "status": 400, "error": "Invalid context"}

        cache_key = self.cache_key("summarize", query, context)
        if self.cache_ttl > 0:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return {"ok": True, "data": cached}

        user_message = f"Search query: {query}\n\nSearch result excerpts:\n{context}"

        try:
            system_prompt = self.prompt_enricher.enrich(
                self.ai_service.get_summarize_prompt(),
                "summarize",
                {"query": query, "context": context},
            )
            system_prompt = self._append_language_instruction(system_prompt, "summarize")

            summary = self.ai_service.message(
                system_prompt, user_message, self.ai_summary_max_tokens
            )
            result = {"summary": summary}

            if self.cache_ttl > 0:
                self.cache.set(cache_key, result, self.cache_ttl)

            return {"ok": True, "data": result}
        except ApiKeyMissingException:
            return {"ok": True, "data": {}}
        except ApiKeyInvalidException as exc:
            self.logger.error("Scolta summarization failed: invalid API key: %s", exc)
            return {"ok": False, "status": 401, "error": "AI API key is invalid or expired"}
        except RateLimitException as exc:
            result = {"ok": False, "status": 429, "error": "AI API rate limit reached"}
            if exc.retry_after is not None:
                result["retry_after"] = exc.retry_after
            return result
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Scolta summarization failed: %s", exc)
            return {"ok": False, "status": 503, "error": "Summarization unavailable"}

    # -- follow up ----------------------------------------------------------

    def handle_follow_up(self, messages: list[dict]) -> dict:
        if not messages or not isinstance(messages, list):
            return {"ok": False, "status": 400, "error": "Messages required"}

        for msg in messages:
            if not msg.get("role") or not msg.get("content"):
                return {"ok": False, "status": 400, "error": "Invalid message format"}
            if msg["role"] not in ("user", "assistant"):
                return {"ok": False, "status": 400, "error": "Invalid role"}

        if messages[-1]["role"] != "user":
            return {"ok": False, "status": 400, "error": "Last message must be from user"}

        follow_ups_so_far = _intdiv(len(messages) - 2, 2)
        if follow_ups_so_far >= self.max_follow_ups:
            return {
                "ok": False,
                "status": 429,
                "error": "Follow-up limit reached",
                "limit": self.max_follow_ups,
            }

        try:
            system_prompt = self.prompt_enricher.enrich(
                self.ai_service.get_follow_up_prompt(), "follow_up", {"messages": messages}
            )
            system_prompt = self._append_language_instruction(system_prompt, "follow_up")

            response = self.ai_service.conversation(system_prompt, messages, 512)
            remaining = self.max_follow_ups - follow_ups_so_far - 1

            return {
                "ok": True,
                "data": {"response": response, "remaining": max(0, remaining)},
            }
        except ApiKeyMissingException:
            return {"ok": True, "data": {"response": "", "remaining": 0}}
        except ApiKeyInvalidException as exc:
            self.logger.error("Scolta follow-up failed: invalid API key: %s", exc)
            return {"ok": False, "status": 401, "error": "AI API key is invalid or expired"}
        except RateLimitException as exc:
            result = {"ok": False, "status": 429, "error": "AI API rate limit reached"}
            if exc.retry_after is not None:
                result["retry_after"] = exc.retry_after
            return result
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Scolta follow-up failed: %s", exc)
            return {"ok": False, "status": 503, "error": "Follow-up unavailable"}

    # -- prompt assembly ----------------------------------------------------

    def _append_language_instruction(self, prompt: str, prompt_type: str) -> str:
        if len(self.ai_languages) <= 1:
            return prompt
        languages = ", ".join(self.ai_languages)
        primary = self.ai_languages[0]
        if prompt_type == "expand_query":
            prompt += (
                f"\n\nReturn expansion terms in the same language as the original query "
                f"if it matches one of these supported languages: {languages}. "
                f"Otherwise return terms in {primary}."
            )
        else:
            prompt += (
                f"\n\nRespond in the same language as the user's query if it matches one "
                f"of these supported languages: {languages}. Otherwise respond in {primary}."
            )
        return prompt

    def _append_sortable_fields_instruction(self, prompt: str) -> str:
        if not self.sortable_fields:
            return prompt
        field_lines = []
        for field in self.sortable_fields:
            desc = self.sortable_field_descriptions.get(field, "")
            field_lines.append(f"- {field}: {desc}" if desc != "" else f"- {field}")
        field_list = "\n".join(field_lines)
        prompt += SORT_INTENT_BLOCK
        return prompt.replace("{FIELD_LIST}", field_list)

    def _append_filter_fields_instruction(self, prompt: str) -> str:
        if not self.filter_fields:
            return prompt
        field_lines = []
        for field in self.filter_fields:
            desc = self.filter_field_descriptions.get(field, "")
            field_lines.append(f"- {field}: {desc}" if desc != "" else f"- {field}")
        field_list = "\n".join(field_lines)
        prompt += FILTER_INTENT_BLOCK
        return prompt.replace("{FILTER_LIST}", field_list)

    # -- response parsing ---------------------------------------------------

    def parse_expansion_response(self, response: str, original_query: str) -> list:
        return self._parse_expansion_result(response, original_query)["terms"]

    def _parse_expansion_result(self, response: str, original_query: str) -> dict:
        cleaned = response.strip()
        cleaned = _FENCE_OPEN.sub("", cleaned)
        cleaned = _FENCE_CLOSE.sub("", cleaned)
        cleaned = cleaned.strip()

        try:
            decoded = json.loads(cleaned)
        except (ValueError, TypeError):
            decoded = None

        if isinstance(decoded, dict) and isinstance(decoded.get("terms"), list):
            terms = decoded["terms"] if len(decoded["terms"]) >= 2 else [original_query]
            return {
                "terms": terms,
                "sort_hint": self._extract_sort_hint(decoded.get("sort")),
                "subject_terms": self._extract_subject_terms(decoded.get("subject_terms")),
                "filter_hint": self._extract_filter_hint(decoded.get("filters")),
            }

        if isinstance(decoded, list) and len(decoded) >= 2:
            return {"terms": decoded, "sort_hint": None, "subject_terms": None, "filter_hint": None}

        return {"terms": [original_query], "sort_hint": None, "subject_terms": None, "filter_hint": None}

    def _extract_subject_terms(self, raw) -> list | None:
        if not isinstance(raw, list):
            return None
        filtered = [v for v in raw if isinstance(v, str) and v != ""]
        return filtered or None

    def _extract_sort_hint(self, raw) -> dict | None:
        if not isinstance(raw, dict):
            return None
        field = raw.get("field")
        direction = raw.get("direction")
        if not isinstance(field, str) or field == "":
            return None
        if direction not in ("asc", "desc"):
            return None
        if not self.sortable_fields or field not in self.sortable_fields:
            return None
        return {"field": field, "direction": direction}

    def _extract_filter_hint(self, raw) -> dict | None:
        if not isinstance(raw, dict) or not raw:
            return None
        validated = {}
        for dimension, value in raw.items():
            if not isinstance(dimension, str) or dimension == "":
                continue
            if not isinstance(value, str) or value == "":
                continue
            if not self.filter_fields or dimension not in self.filter_fields:
                continue
            validated[dimension] = value
        return validated or None

    # -- cache key ----------------------------------------------------------

    def cache_key(self, action: str, *parts: str) -> str:
        hash_input = "|".join(parts).lower()
        digest = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        return f"scolta_{action}_{self.generation}_{digest}"
