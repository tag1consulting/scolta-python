# Changelog

All notable changes to scolta-python are documented here.

## [Unreleased]

Initial port of `scolta-php` to Python (work in progress).

### Phase 0 — scaffold
- `pyproject.toml` (hatchling, Python >=3.10), package skeleton, README,
  CLAUDE.md (porting conventions), asset inventory recorded.

### Phase 1 — leaf types, config, util
- `config.ScoltaConfig` — full port of `ScoltaConfig` incl. presets, `from_dict`
  (preset-then-override, None-skip, locked `expansion_per_term_top_k`, PHP-bool
  coercion) and the JS/browser/AI export shapes.
- `content` — `ContentItem` (URL normalization, `clone_with`), `TrackerRecord`,
  `ContentSource` ABC.
- `markdown.render` — direct port of `MarkdownRenderer` (XSS-safe, broken-link
  salvage).
- `storage` — `StorageDriver` ABC + `FilesystemDriver` (stream-wrapper guard).
- `cache` — `CacheDriver` ABC, `NullCacheDriver`, `InMemoryCacheDriver`.
- `provider.AiResponse`, `exceptions` (ApiKeyMissing/Invalid, RateLimit).
- Tests: 73 passing (markdown 30, storage 12, config 14, content 8,
  filter-field-descriptions 7, cache 2). ruff clean.

### Phase 2 — AI client and endpoint handler
- `ai/client.AiClient` — Anthropic + OpenAI-compatible transports on httpx
  (base_url path completion for proxy/Ollama/LiteLLM; 401/429/5xx -> typed
  exceptions; malformed-JSON guard).
- `ai/prompts` — `DefaultPrompts` port; expand/summarize/follow-up templates
  extracted verbatim from the PHP source for byte-fidelity; `resolve`/`get_template`.
- `ai/endpoint.AiEndpointHandler` — expand/summarize/follow-up orchestration:
  validation, generation-scoped sha256 cache keys, response parsing (code-fence
  strip, object/array formats, sort/subject/filter hint extraction), language /
  SORT INTENT / FILTER INTENT prompt assembly (intent blocks extracted verbatim),
  follow-up cap (PHP intdiv semantics), graceful degradation + error mapping.
- `ai/service.AiServiceAdapter` — dual-path routing, prompt resolution, lazy
  client, budget-exception hook.
- `ai/enricher` (PromptEnricher/NullEnricher) and `ai/controller.AiControllerMixin`
  (AiControllerTrait port).
- Tests: +143 (endpoint 80, service 19, client 13, prompts 6, controller 3,
  plus doubles). Total 216 passing, ruff clean.

### Phase 3 — content export and HTML cleaning (Parity Gate #1)
- `html.py` — faithful regex/string port of `HtmlCleaner` + `PagefindHtmlBuilder`
  (NOT a DOM parser; reproduces PHP `strip_tags` / `html_entity_decode` /
  non-`/u` `\s` semantics, including nbsp survival and ENT_HTML5 `&apos;`).
- `export.py` — `ContentExporter` (URL->path mapping, min-content filter,
  collision detection, manifest, disk export).
- **Parity gate passed byte-for-byte** against the real PHP classes: golden file
  generated from scolta-php (20 recipe fixtures ×2, 20 edge-case units, 14
  builder cases) and asserted by `test_html_parity.py`. Regenerable via
  `parity/html_harness.php`.
- Tests: +102 (html units 32, html parity 54, export 16). Total 318 passing,
  ruff clean.

### Phase 4 — tokenizer and stemmer (Parity Gate #2, deepest risk)
- `index/tokenizer.py` — faithful port of `Tokenizer` (Pagefind `splitting.rs`
  boundaries): `regex` `\p{L}\p{N}\p{Emoji_Presentation}` word pattern with
  apostrophe contractions, NFD→strip-Mn→NFC diacritic normalization (matches
  PHP's ICU transliterator), hyphen + camelCase compound splitting, and
  CJK/Hiragana/Katakana/Hangul bigram tokenization. (Python str is code-point
  based, so PHP's byte/char offset bookkeeping and `textIsAscii` fast-path are
  omitted without affecting output.)
- `index/stemmer.py` — `Stemmer` over `snowballstemmer` (14 languages, memoized).
- `index/token.py` — `Token` (frozen slots dataclass).
- **Parity gate passed byte-for-byte:** 29-case tokenizer golden from the real
  PHP `Tokenizer` (incl. emoji, German ß preservation, katakana `ピ→ヒ`
  normalization, mixed-CJK, contractions, real recipe prose) via
  `parity/tokenizer_harness.php`; and the **full 177,505-word stemmer corpus**
  (en/fr/de/es/ru) reproduced with **0 mismatches** — `snowballstemmer` matches
  `wamania/php-stemmer` exactly.
- New runtime dep: `regex` (for Unicode property classes the stdlib `re` lacks).
- Tests: +71 (tokenizer 25 + 29 golden, stemmer 13 + 5 corpus, token 2).
  Total 389 passing, ruff clean.

### Phase 5 — CBOR / delta / inverted-index / format writers (Parity Gate #3)
- `index/cbor.py` (canonical CBOR, UTF-8 byte lengths), `index/delta_encoder.py`,
  `index/supported_versions.py`, `index/inverted_index_builder.py`
  (title weight 50 / body 25, 200-position cap, word-sequential positions,
  variants), `index/format_writer.py` (PagefindFormatWriter, 0-based remap +
  chunking), `index/streaming_format_writer.py` (StreamingFormatWriter, the
  primary writer), shared helpers in `index/_pf_common.py`, and a test-only
  CBOR decoder (`tests/support/cbor_decoder.py`).
- **Parity gate passed:** (a) controlled alphabetic-only corpus is BYTE-EXACT
  vs the real PHP writer (fragment JSON + pf_index/filter/meta CBOR
  uncompressed payloads, hashes/filenames, chunking); (b) recipe corpus is
  STRUCTURALLY exact (both writers, fed the PHP-built index to isolate them).
- **Findings / tolerances (documented in tests):**
  - Term order is lexicographic (canonical Rust-Pagefind/WASM order); PHP
    `sort()` SORT_REGULAR is non-transitive on numeric tokens, so chunk
    partitioning differs while per-word postings are identical.
  - `wamania/php-stemmer` diverges from canonical Snowball on `adding`→`ad`
    and `paste`/`pasted`→`past`; Python matches the canonical reference +
    rust-stemmers (the shared WASM), so Python is the correct side.
- Tests: +129 in tests/index/ (cbor 22, delta 12, versions 11, builder 12,
  format parity 4, plus the Phase-4 tokenizer/stemmer). Total 447 passing,
  ruff clean.

### Phase 6 — build pipeline + Phase 7 — token cache
- Build pipeline: `build_intent` (BuildIntent/Factory), `build_result`
  (BuildResult/StatusReport), `progress`, `memory_budget`, `memory_telemetry`
  (RSS/cgroup-aware, behaviour-matched), `chunk_io` (v2 chunk format, msgpack
  records, crc32/hmac), `merger` (N-way heap merge + recursive pre-merge),
  `build_state` (flock lock, atomic manifest, resume), `coordinator`,
  `orchestrator` (prepare→chunk-loop→merge→write→atomic-swap→verify with
  memory-yield/resume), `indexer` (PythonIndexer facade), and
  `memory_budget_config`.
- Token cache ("maintain the index"): `page_word_cache`, `timestamp_manifest`,
  `cached_reference`. **Hazard fixed:** cross-build caches live in their own
  `state/cache/` subdir, so a fresh-build `cleanup()` (transient files only,
  never subdirs) can never evict them — proven by the efficiency tests.
- Efficiency proven (Phase 7): no-change rebuild re-tokenizes **0** pages;
  one-page edit re-tokenizes **1**; deleted page leaves the index. Build
  resume-after-interruption produces a byte-structurally identical index to an
  uninterrupted build; multi-chunk == single-chunk.
- Internal formats use msgpack (Python-native, no parity constraint); the
  Phase-1-deferred MemoryBudgetConfigTest is now ported.
- Tests: +77. Total 524 passing, ruff clean.
