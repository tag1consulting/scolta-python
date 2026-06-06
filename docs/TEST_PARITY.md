# Test-parity accounting (scolta-php → scolta-python / scolta-django)

This ledger accounts for every `scolta-php` test directory against the ported
Python tests, and **discloses every gap** rather than burying it. It satisfies
the port's rule: regression *intent* must be preserved, not a hand-picked
subset.

## Headline numbers

| Suite | Test files | Test functions | Collected cases |
|---|---|---|---|
| scolta-php (PHPUnit, `*Test.php`) | 82 | **1023 methods** | — |
| scolta-python (pytest) | 42 | 524 functions | **689** |
| scolta-django (pytest-django) | 3 | 42 functions | 42 |
| **Python total** | **45** | **566** | **731** |

Function count is lower than PHP's method count in three areas **by design**, and
genuinely short in a few **disclosed** areas (see Gaps). The three by-design
reductions:

1. **Parametrization** — one Python function expands to many cases
   (`@pytest.mark.parametrize`). E.g. `test_html_parity.py` is 3 functions but
   **54 cases**; the tokenizer golden is 1 function / 29 cases; the stemmer
   corpus is 1 function / 5 languages / **177,505 words**.
2. **Golden-file consolidation** — many PHP per-field structural assertions
   collapse into one *byte-exact* or *structural-exact* comparison that covers
   all fields at once (stronger, not weaker). The Pagefind format/CBOR/merge
   tests are the main example.
3. **PHP-runtime-specific tests** — memory-layout, `serialize()` format, and
   PHP-array-key-semantics assertions are N/A in Python and are replaced by
   behaviour-equivalent tests (or by `ruff`).

## Per-directory ledger

| scolta-php dir | files / methods | Python location | Status |
|---|---|---|---|
| `tests/Util` (MarkdownRenderer) | 1 / 28 | `test_markdown.py` (28) | ✅ 1:1 |
| `tests/Storage` | 1 / 12 | `test_storage.py` (12) | ✅ 1:1 |
| `tests/Config` (FilterFieldDesc, MemoryBudgetConfig) | 2 / 32 | `test_filter_field_descriptions.py` (6) + `test_memory_budget_config.py` (26) | ✅ 1:1 |
| `tests/Http` (AiEndpointHandler, AiControllerTrait) | 2 / 105 | `tests/ai/test_endpoint.py` (102) + `test_controller.py` (3) | ✅ 1:1 |
| `tests/Service` (AiServiceAdapter) | 1 / 19 | `tests/ai/test_service.py` (17) | ✅ 1:1 (2 PHP closure-mock cases folded) |
| `tests/Html` | 2 / 31 | `test_html.py` (32) + `test_html_parity.py` (3 fn / 54 cases) | ✅ exceeds (adds byte parity) |
| `tests/Tokenizer` (CjkBigram) | 1 / 8 | `tests/index/test_tokenizer.py` (CJK cases) | ✅ within tokenizer suite |
| `tests/Environment` | 1 / 6 | `test_environment.py` (8) | ✅ exceeds |
| `tests/Health` | 1 / 10 | `test_health.py` (10) | ✅ 1:1 |
| `tests/Integration` (Pipeline) | 1 / 1 | `tests/index/test_orchestrator.py` + django `scolta_build` test + browser E2E | ✅ exceeds |
| `tests/Index` (CBOR/Delta/Writers/Merger/BuildState/cache/…) | 34 / 381 | `tests/index/*` (160 fn) + golden files | ✅ intent preserved; writer/merge/page-numbering structural assertions consolidated into **byte + structural golden parity** (Phase 5). Memory-regression (PHP `memory_get_usage`) → behaviour tests (`test_memory_budget*`). |
| `tests/Concordance` (Reference + Multilingual) | 11 / 86 | `tests/concordance/test_concordance.py` (4 fn / 40 cases) | ✅ ported vs the **frozen Pagefind-binary reference** (English + 19 languages incl. ar/zh/ja/ko): per-page content Jaccard + fragment-count ±1. **Result: Jaccard = 1.000 every language** (Python content extraction matches the real Pagefind CLI exactly). |
| `tests/Security` (InputValidation, AiErrorHandling) | 2 / 29 | `tests/security/test_security.py` (19) | ✅ ported (HTML/JS injection, pathological sizes/null-bytes/bidi, path-traversal-in-id, endpoint validation, follow-up caps, OpenAI-branch error mapping) |
| `tests/AiProvider/Amazee` | 8 / 54 | `tests/ai/amazee/test_amazee.py` (28) + django `test_amazee_django.py` (11) | ✅ ported (was deferred) + **verified live** |
| `tests/` root (AiClient, DefaultPrompts, ContentExporter, ScoltaConfig, PagefindBinary, SetupCheck, Dto, AssetManifest) | 8 / ~190 | `test_client` (13), `test_prompts` (6), `test_export` (9), `test_config` (13), `test_resolver` (binary, within 10), `test_health` (SetupCheck), `test_content` (8), `test_assets` (4) | ✅ intent preserved (raw count lower: parametrization + the byte-exact `test_assets` allowlist check replaces per-file manifest assertions) |
| `tests/` root: HygieneTest, StructuralIntegrityTest | 2 / ~13 | `ruff` + package layout | ◻️ N/A — PHP-codebase hygiene (no `var_dump`, `declare(strict_types)`, PSR-4 namespacing); the Python equivalent is `ruff` + the package structure |
| `tests/js` (Jest), `tests/E2E` (Playwright) | carried over | stays in scolta-php; **+** `tests/e2e/test_browser_wasm.py` | ✅ carry-over (tests scolta.js/WASM, reused verbatim) + a NEW Python-index browser E2E proving the WASM accepts a Python-built index |

## Gaps (disclosed, not hidden)

These PHP tests are **not** ported (or only partially), with the reason and the
mitigating coverage:

1. **`tests/Concordance` Wikipedia corpora — PARTIAL.** The English + 19-language
   multilingual concordance is now ported (`tests/concordance/`, Jaccard = 1.000
   vs the real Pagefind binary). `corpus-wiki` is now ported too (19 languages, Wikipedia prose). **Not
   ported:** `corpus-wiki-extended` (additional scale of the same shape).
2. **`tests/Documentation` — ConfigReferenceDocTest now ported.**
   `docs/CONFIG_REFERENCE.md` + `test_documentation.py` enforce config/doc
   parity. `ArchitectureAccuracyTest` stays N/A (guards a PHP-specific
   architecture doc).
3. **`tests/Benchmark` (1 / 6) — NOT ported.** Throughput/timing benchmarks;
   environment-dependent and not correctness gates. Correctness of the indexer
   pipeline is covered by the build/merge/cache tests.
4. **`tests/LargeContent` (1 / 4) — PARTIAL.** Large-corpus scale/memory
   behaviour. Covered behaviourally by the orchestrator chunking, resume, and
   token-cache tests; the multi-thousand-page stress fixture is not reproduced.
5. **`AmazeeProvisionCommand` / `AmazeeSettingsController` / budget middleware
   (Laravel-only adapter glue)** — the Django equivalents are the
   `scolta_amazee_provision` command, the `AmazeeAccountUpgrader` API, the
   `DjangoAiService` budget hook, and the web upgrade UI (the
   `scolta_django.amazee_views` JSON endpoints + the Alpine.js
   `amazee_settings.html` page, mirroring the Laravel settings view) — all
   tested.

## Deferred by design (out of scope per the port spec)

- **True segment-level incremental index maintenance** — does not exist in
  scolta-php either; PHP rewrites the whole `pagefind/` and atomic-swaps. The
  Python port matches that behaviour + the token cache.
- **`TokenTest::testTokenUsesLessMemoryThanEquivalentArray`** — a PHP
  memory-layout regression (final readonly class vs 3-key array). N/A to Python;
  replaced by `test_token.py::test_token_is_slotted`.
