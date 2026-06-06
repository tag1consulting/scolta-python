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

### Phase 8 — resolver, binary path, health, environment, assets
- `index/resolver.py` (IndexerResolver: auto/unknown→python; binary→binary or
  fall back to python with a logged notice), `pagefind.py` (PagefindBinary
  resolver chain + `--version` probe + status + download target),
  `environment.py` (HostingDetector/Constraints/Environment, env-var based),
  `health.py` (HealthChecker + SetupCheck, adapted to Python).
- **Asset vendoring**: the WASM/JS/CSS bundle is copied verbatim from
  `scolta-php/assets/` into `src/scolta/assets/` via a **fail-closed extension
  allowlist** (`scripts/vendor_assets.py`) — only `.wasm/.js/.css/.pagefind`
  ship; `.sha256/.d.ts/.map` can never leak. 8 runtime files vendored; the
  format writers now copy the Pagefind runtime into built indexes.
- **Release Gate #3 (indexer URL parity)**: the Python indexer stores
  `data.url == canonical item.url` (asserted by joining on stable id, never by
  URL) and the export path mirrors the canonical URL so the binary path yields
  identical URLs; no stale `/{id}.html` artifacts.
- Tests: +34 (resolver/binary 11, environment 8, health 11, assets 4,
  url-parity 2 — plus the allowlist fail-closed check). Total 558 passing,
  ruff clean.

### Amazee.ai auto-provisioning subsystem (previously deferred)
- `ai/amazee/` — full port of the Amazee.ai managed-gateway subsystem on httpx:
  `AmazeeClient` (trial provisioning, email-OTP upgrade flow, model info, token
  validation), `AmazeeModelResolver` (highest Sonnet/Haiku), `AmazeeTrialProvisioner`,
  `AmazeeAccountUpgrader`, `AutoProvisioner` (idempotent first-request guard),
  `BudgetAwareProviderDecorator` (429 budget → `AmazeeBudgetExceededException`),
  `ConfigStorage` ABC, result/exception DTOs.
- Tests: +28 (client nested/flat formats, upgrade flow, model resolver,
  provisioner skip/store, auto-provisioner idempotency, budget cause-chain).
  Total 586 passing, ruff clean.

### Phase 11 — browser WASM E2E
- `tests/e2e/test_browser_wasm.py` — builds an index from the recipe fixtures
  with the Python indexer, serves it, and drives the real `pagefind.js` +
  `wasm.en.pagefind` in headless Chromium (Playwright). Asserts queries return
  the expected pages ("eggplant"→eggplant-parmigiana + related; "noodles"→6
  dishes; "spicy tofu"→mapo-tofu; nonsense→0). **Proves the shared WASM accepts
  and correctly searches a Python-built index.** Skips gracefully when Chromium
  isn't installed.
- Verified live end-to-end too: anonymous Amazee trial provisioning → real query
  expansion + Claude summary through the LiteLLM endpoint, via both the binding
  and the Django adapter.
- Tests: +1. Total 587 passing, ruff clean.

### Test-parity hardening
- `docs/TEST_PARITY.md` — full per-directory ledger (scolta-php → Python),
  disclosing every gap.
- **Closed the Concordance gap:** `tests/concordance/test_concordance.py` runs
  the Python indexer against the committed **frozen Pagefind-binary reference**
  (English + 19 languages incl. ar/zh/ja/ko) via per-page content Jaccard +
  fragment-count ±1. Result: **Jaccard = 1.000 for every language** — the Python
  indexer's content extraction matches the real Pagefind CLI exactly.
- **Closed the Security gap:** `tests/security/test_security.py` (HTML/JS
  injection, pathological sizes / null bytes / bidi, path-traversal-in-id,
  endpoint validation, follow-up caps, OpenAI-branch error mapping).
- Tests: +59. Total 646 passing, ruff clean.

### JS release-gate tests
- Ported `scolta-php`'s `tests/js/` Jest suite (asset paths adapted to the
  `src/scolta/assets/` layout) plus the `result-count-baseline.json` fixture, and
  added a `js-tests` CI job (Node 20: `npm ci` + `npm test` in `tests/js`). The
  suite runs the byte-identical `scolta.js` that scolta-python ships, closing two
  required user-visible regression families: the **result-count baseline**
  (sub-word frequency guard / expansion-merge — pins per-query result counts
  within a tolerance band) and **AI-citation URL grounding** (summary context
  builders and result-card renderer cite canonical `meta.url`, not the raw
  fragment `url`).
