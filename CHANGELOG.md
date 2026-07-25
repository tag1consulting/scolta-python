# Changelog

All notable changes to scolta-python are documented here.

## [Unreleased]

### Changed
- **Re-vendored the browser bundle (`src/scolta/assets/js/scolta.js`) from scolta-php: `hideEmptyFacets` facet-visibility opt-out ([scolta-php#239](https://github.com/tag1consulting/scolta-php/pull/239)).** The bundle now hides a facet value whose count is zero for the current query by default (dropping a filter group whose values are all zero); an active value stays visible so it can be unchecked. A site can restore the prior show-disabled behavior by setting `window.scolta.hideEmptyFacets = false`. This package ships the bundle only and inherits the JS default; no Python-side config surface is added. Assets copied verbatim via `scripts/vendor_assets.py`, and the mirrored `tests/js/faceting.test.js` re-synced from scolta-php (only the vendored asset path differs).
- **Re-vendored the browser bundle (`src/scolta/assets/js/scolta.js`) and the bundled scolta-core WASM from scolta-php ([scolta-php#237](https://github.com/tag1consulting/scolta-php/pull/237), [#238](https://github.com/tag1consulting/scolta-php/pull/238), issue [#156](https://github.com/tag1consulting/scolta-php/issues/156)).** Brings specificity-weighted ranking of partial matches (each sub-query weighted by how rare its term is in the corpus), co-occurrence ranking (a document agreeing with several query/expansion terms outranks one matching a single strong term), and the fix that stops the co-occurrence path loading full documents for non-seeding terms — typed words and agreement-only phrase sub-words — deciding their agreement from result ids and joining seeded documents by Pagefind entry id, which removes the discarded loads that had inflated the per-query loaded-document count. Assets are copied verbatim via `scripts/vendor_assets.py`; no behaviour is implemented in this package.

### Fixed
- **Prompt templates re-synced from scolta-core (`src/scolta/ai/prompts.py`).** Picks up expand_query rule 16 (NAMED ENTITY / EVENT → DEFINING DETAILS), which stops identifier/proper-noun queries from being expanded into terms that all keep the entity anchor and therefore match nothing, and the rewritten summarize/follow_up grounding rules, which forbid the model from claiming the collection lacks content it cannot see.
- **Added the prompt-text identity gate this package was missing (`tests/ai/test_prompt_identity.py`).** scolta-php and scolta-node each fail loudly when their hand-maintained copy of the prompt templates drifts from the canonical scolta-core text; scolta-python had no such gate, so its copy could diverge silently while the whole suite stayed green. The gate is a direct port: it resolves scolta-core via `SCOLTA_CORE_PROMPTS` or the sibling checkout, normalizes out the `{DYNAMIC_ANCHORS}` WASM-path token, and asserts byte identity for all three templates. Env set but file missing fails; env unset with no sibling checkout skips.
- **`test_binary_status_unavailable_message` was environment-fragile and, on any
  runner with npx, vacuous (`tests/index/test_resolver.py`).** `PagefindBinary`
  probes its fallback chain (configured path, project-local `.scolta/bin`, `npx
  pagefind`, bare `pagefind` on PATH) by running each candidate's `--version`.
  The test supplied nonexistent configured and project paths but left PATH
  alone, so the `npx pagefind` probe stayed live. That probe is stateful: a
  first invocation can install or cache pagefind as a side effect, so a probe
  that fails once can succeed the next time. `status()` and `resolved_via()`
  each call `resolve()` independently, so the two calls could disagree, and
  `resolved_via()` returned `"npx"` after `status()` had already reported the
  binary unavailable. The Renovate `actions/setup-node` v6 to v7 bump (a commit
  touching only `.github/workflows/ci.yml`) shipped a different npm and flipped
  this on the `test (3.11)` job. The test also wrapped its assertions in `if not
  status["available"]:`, so on a runner where the binary did resolve it asserted
  nothing at all and passed silently. It now points PATH at an empty `tmp_path`,
  which forces both PATH candidates to fail while the absolute configured and
  project paths fail on their own, and the assertions run unconditionally.
  Production code is unchanged; the fallback chain in `src/scolta/pagefind.py`
  is correct.

### Changed
- **Re-vendored the browser bundle (`src/scolta/assets/js/scolta.js`) from scolta-php: Pagefind index chunks are now preloaded while the user types** ([tag1consulting/scolta-php#232](https://github.com/tag1consulting/scolta-php/pull/232), issue [#191](https://github.com/tag1consulting/scolta-php/issues/191)). Scolta runs no search until Enter or the search button, so every submitted search also paid for fetching the alphabetical index chunk(s) for the typed term. The search input now hands the term to `pagefind.preload()` — the chunk-resolution half of a search, which bails out before scoring — so the search that fires on submit finds the chunk already resolved. Guarded by a 150 ms trailing debounce, a 2-character floor, a repeat-term skip, and a feature-detect on `preload` (index builds from Pagefind releases that predate it are unaffected); failures are swallowed, so a cache warm can never break the search box. Copied byte-identically from the canonical source; no Python-side code changed.

### Added
- **Optional `temperature` parameter on `AiClient.message()` and `AiClient.conversation()` (`src/scolta/ai/client.py`).** A trailing `temperature: float | None = None` is threaded through `_send_request()` into both the Anthropic and OpenAI-compatible request builders. When `None` (the default) no `temperature` key is included in the request body and the provider default applies, so existing request bodies are byte-identical to before; when non-`None` it is sent to both provider shapes (the Amazee path proxies through the OpenAI-compatible endpoint and inherits that handling). `AiServiceAdapter.message_for_operation()` now pins `temperature=0.0` for the `expand_query` operation so the same query yields the same expansion terms on every uncached call, while summarize and follow-up keep the provider default. Ported from tag1consulting/scolta-php#230.

## [1.0.1] - 2026-07-10

> **Upgrade note — rebuild required for Danish, Finnish, Italian, or Norwegian
> indexes.** Indexes built with 1.0.0 for Danish, Finnish, Italian, or Norwegian
> content must be rebuilt. The build-time stemmer changed to match Pagefind's
> query-time stemming exactly, so on-disk stems for those languages changed (the
> same caveat scolta-php documented). English/French/German/Spanish/Russian and
> the other shipped languages are unaffected.

### Changed
- Improved handling of expired or revoked Amazee.ai credentials: auth-class
  failures on the AI call are now detected, the AI service degrades cleanly
  (never silently), the site is flagged for admin re-authentication, and AI
  health status more accurately reflects credential state. The model-resolution
  self-heal is unchanged.

### Fixed
- **The stemmer produced query-mismatched stems for Danish, Finnish, Italian, and Norwegian indexes (`src/scolta/index/stemmer.py`).** The build-time stems must match what Pagefind 1.5.0 stems *queries* with at runtime (the crate `pagefind_stem` 1.0.0); a stem Pagefind cannot reproduce at query time is a word nobody can find. The binding depended on `snowballstemmer>=3`, which resolved to 3.1.1, but 3.1.x added apostrophe/elision handling that `pagefind_stem` 1.0.0 does **not** have (Danish/Norwegian/Finnish apostrophe handling, Italian elision stripping). Measured against the 14-language corpus, 3.1.1 diverges from Pagefind on **2,103 words** (it 1,867 / fi 183 / da 35 / no 18), so those indexes silently missed every affected query. The bug went unseen because the parity test only covered 5 languages (en/fr/de/es/ru) — the four divergent ones were mapped and shipped but never verified. No published `snowballstemmer` release reproduces `pagefind_stem` 1.0.0 across all 14 languages either: the 3.0.x line predates the `english.sbl` fixes the crate has (18 English divergences). The stemmers are now **vendored** from the Snowball compiler at the exact mainline commit `pagefind_stem` 1.0.0 was generated from (`019c1bd`, between v3.0.0 and v3.1.0), in `src/scolta/index/snowball/` — matching the crate byte-for-byte over the full corpus (589,069 words, 0 divergences) and mirroring `scolta-php/src/Index/Snowball`. The `snowballstemmer` dependency is removed; a sha256 drift guard (`test_snowball_provenance.py`) pins the vendored source, and the byte-exact corpus parity gate now covers all 14 shipped languages (was 5), so a future stemmer move fails CI loudly. **Existing Danish/Finnish/Italian/Norwegian indexes built with the old stemmer must be rebuilt** — their on-disk stems changed (same caveat scolta-php documented).
- **Amazee credentials stored without resolved model names no longer leave AI permanently broken (`src/scolta/ai/amazee/auto_provisioner.py`).** Storing the credentials and resolving model names are two non-atomic steps (`AmazeeTrialProvisioner.provision()` stores the token+url, then calls `/model/info`). When the model-info call fails, `get_available_models()` swallows the error and returns `[]`, so the `on_models_resolved` gate never fires and no model name is persisted — but `ConfigStorage.load()` requires only token+url, so it reports the credentials as valid. `ensure_ai_available()` then short-circuited on stored credentials on every later request and never re-resolved, so the caller fell back to the dated config default (`claude-sonnet-4-5-20250929`) which the Amazee LiteLLM gateway rejects with HTTP 400 "Invalid model name" — failing AI silently with no self-healing (outside `KeyExpiryRecovery`'s auth-only remit). `ensure_ai_available()` now accepts an optional `has_resolved_models` predicate: when stored credentials exist but the caller reports models are still unresolved, model resolution is re-attempted against the **already-stored key** (credentials are never re-issued) and `on_models_resolved` fires with the result, so the incomplete-setup state self-heals on the next lazy-init pass. Without the predicate the historical no-op is unchanged. A regression test drives the full store → failed-resolution → re-resolve sequence. (The dated-default fallback itself lives in the consuming adapter/demo client construction, which adopts the predicate when it re-vendors.)

### Added
- **`Referer: scolta-python` header on Amazee control-plane requests
  (`src/scolta/ai/amazee/client.py`).** The `_post`/`_get` helpers that hit
  `api.amazee.ai` now send `Referer: scolta-python` so the Amazee backend can
  attribute control-plane traffic to this SDK. Port of @dan2k3k4's
  tag1consulting/scolta-php#203 (issue tag1consulting/scolta-php#202) with the
  package-specific value. The per-tenant LiteLLM calls are unchanged. Covered by
  a test asserting the header on a POST and a GET.
- **CI now builds and validates the PyPI artifacts (`dist` job in
  `ci.yml`).** Publishing is manual and nothing in CI built the sdist/wheel, so
  packaging breakage or cruft was only found at `twine upload` time. The job
  runs `uv build`, `twine check dist/*` (metadata/long-description validity),
  and a new `scripts/validate-dist.py` content gate (runs locally too, after
  `uv build`). The wheel gate asserts every vendored browser runtime asset is
  present (`assets/css/scolta.css`, `assets/js/scolta.js`,
  `assets/pagefind/{pagefind-worker.js,pagefind.js,wasm.en.pagefind,wasm.unknown.pagefind}`,
  `assets/wasm/{scolta_core.js,scolta_core_bg.wasm}`) — the failure mode that
  matters most, a wheel that imports but ships no search UI because
  `vendor_assets.py` was not run — and that nothing lives outside the `scolta`
  package and dist-info (no `tests/`, `__pycache__`, `*.pyc`, or
  `.sha256`/`.d.ts`/`.map` sidecars). The sdist gate asserts a buildable source
  set with no local build-dir junk. Size caps (~2x the measured good artifacts:
  wheel 1.5 MB cap vs ~712 KiB, sdist 4.7 MB cap vs ~2.24 MiB) catch a bloat
  regression. Mirrors the dist-cruft precedent from the scolta-wp 13 MB zip
  incident and the WP.org compliance flags.

### Fixed
- **The sdist no longer ships local-only build directories.** Hatchling's
  source distribution defaulted to "everything on disk except VCS-ignored",
  which pulled `tests/js/node_modules` (61 MB of vendored npm packages,
  including `.idea` IDE files) and `tools/stemmer-golden/target` (Rust build
  artifacts) into the tarball — a 7.9 MB sdist. A new
  `[tool.hatch.build.targets.sdist]` `exclude` list (enumerated, fail-closed)
  prunes those plus caches/IDE/`.pyc` junk, dropping the sdist to ~2.35 MB
  while keeping the full ported test corpus and stemmer fixtures. The wheel was
  already clean (`packages = ["src/scolta"]`).
- **Re-vendored the browser bundle (`scolta.js`/`scolta.css`) from scolta-php
  `main`, picking up three client-side fixes that had not yet reached the
  Python binding.** scolta-php #217 stops the sub-word frequency guard from
  sizing its corpus with a match-all `pagefind.search(null)` (which downloaded
  the entire Pagefind word index — the Athenaeum AI-Overview latency stall);
  the guard now uses a cached-totals `subwordCorpusSize()` helper. scolta-php
  #210 fixes a silent sort drop on unmatched subjects (generic queries like
  "newest posts" now sort unscoped instead of being dropped) and tunes the
  sort-intent prompt. scolta-php #213 adds the auto topic-filter recall guard
  that *offers* a low-recall filter as a dismissable chip instead of applying
  it (the new `.scolta-filter-offer`/`.scolta-filter-apply` CSS). The bundle is
  byte-identical to scolta-php's canonical asset. The JS test mirror
  (`tests/js/`) was re-synced in lockstep — `behavioral.test.js` now asserts
  the guard uses `subwordCorpusSize(activeFilters)` and not
  `pagefindSearch(null`, and `faceting.test.js`,
  `subword-frequency-guard.test.js`, and `result-count-baseline.test.js` track
  the #210/#217 behavior — and the SORT intent prompt block in
  `src/scolta/ai/_intent_blocks.py` was re-synced byte-for-byte to the #210
  canonical text.
- **Configured Pagefind binary paths containing spaces no longer shatter into
  garbage argv (`src/scolta/pagefind.py`).** `_is_executable()` and
  `version()` naively `str.split()` every candidate command before passing it
  to `subprocess.run`, so a configured (or project-local) binary at a path
  with spaces was probed as nonsense and reported unavailable. Commands are
  now argv lists internally: only the known `npx pagefind` constant is split
  (via `shlex.split`, once, as a module constant); configured/local/PATH
  candidates are passed verbatim as single-element argv. New
  `PagefindBinary.resolved_argv()` exposes the executable argv for callers;
  `resolve()` keeps returning the display string.
- **`scripts/vendor_assets.py` no longer accepts a partial source tree or
  leaves stale files vendored.** A missing source subdir was silently
  `continue`d (exit 0, "Vendored N files"), and files deleted upstream stayed
  vendored forever because destinations were never cleared. Each expected
  subdir is now required to exist and to yield at least one allowlisted file
  (otherwise exit non-zero), and each destination subdir is cleared before
  copying so deletions propagate.
- **`FilesystemDriver.move()` survives cross-filesystem moves
  (`src/scolta/storage.py`).** Bare `os.rename` raises `EXDEV` when the state
  and output dirs sit on different filesystems; `shutil.move` falls back to
  copy+delete.
- **The atomic index swap restores the previous index if the final move fails
  (`src/scolta/index/orchestrator.py`).** Previously the old `pagefind/` had
  already been moved aside when the new index failed to move into place,
  leaving the site with no index at all. The swap logic is also deduplicated:
  `IndexBuildOrchestrator._atomic_swap` and `PythonIndexer._atomic_swap` were
  identical copies and now share `orchestrator.atomic_swap()`.
- **`PythonIndexer.process_chunk` honours the configured language.** The fresh
  `BuildIntent` hardcoded `{"language": "en"}` regardless of the `language`
  the indexer was constructed with.
- **Build/finalize catch-alls log the traceback before flattening the failure
  to `str(exc)`** (`orchestrator.py`, `indexer.py`) — reports are unchanged
  (parity-safe), but failures are diagnosable from the `scolta.index` logger
  again.
- **Version split-brain resolved:** `pyproject.toml` pinned `1.0.0` while
  `scolta.__version__` said `1.0.4.dev0`. The project version is now dynamic,
  single-sourced from `src/scolta/__init__.py` via `[tool.hatch.version]`.

### Changed
- **Lint posture:** `ruff format` is now the enforced formatter (CI runs
  `ruff format --check`), so the configured `line-length = 100` is no longer
  dead — it governs code via the formatter. `E501` stays ignored deliberately
  (the remaining over-length lines are parity-sensitive single-line
  prompt/message strings), now documented in `pyproject.toml`. The lint select
  set is extended with `C4`, `SIM`, `RET`, and `RUF`, and CI lints the whole
  tree (`scripts/` included). `PTH` (pathlib migration) was evaluated and
  deferred: ~220 violations across the os.path-idiomatic port, a separate
  mechanical PR if wanted.
- Stale docs refreshed: `CLAUDE.md` no longer claims the shared-JS Jest suite
  lives in scolta-php (it lives here and runs in CI) nor that the Amazee
  subsystem is deferred (it is implemented); `README.md` no longer calls the
  package a work-in-progress port.

### Added
- **PEP 561 `py.typed` marker (`src/scolta/py.typed`).** The package is fully
  annotated but shipped no marker, so downstream type checkers ignored all of
  it. Verified included in the wheel.
- **`ScoltaConfig.to_browser_config(endpoints=...)`** — framework adapters can
  substitute the AI endpoint URLs they actually registered (e.g. Django
  `reverse()` results under a custom `route_prefix`) for the hardcoded
  `/api/scolta/v1/...` defaults; unspecified keys keep their defaults.
- **`ScoltaConfig.from_dict` logs ignored unknown keys** at debug level
  (debug, not warning, because framework adapters pass their whole settings
  dict including adapter-only keys).
- `_proxy()` deduplicated: `index/indexer.py` now imports the
  `index/orchestrator.py` definition instead of carrying an identical copy.
- **Amazee credential auth-failure detection, clean degradation, and truthful
  health (`src/scolta/ai/amazee/key_expiry_recovery.py`,
  `src/scolta/ai/service.py`, `src/scolta/health.py`).** Port of the scolta-php
  fix ([tag1consulting/scolta-php#211](https://github.com/tag1consulting/scolta-php/pull/211));
  semantics match it. Amazee credentials are revoked server-side when their
  lifecycle ends, and the expiry is not announced at issue time (verified
  against the live API: `/auth/generate-trial-access` returns only `created_at`;
  the LiteLLM key's own `expires` is a year out while observed revocation is ~a
  day) — so the only reliable signal is the auth failure on the next inference
  call. Nothing detected it: `AutoProvisioner.ensure_ai_available()` no-ops
  whenever credentials are stored, the expand/summarize graceful-degrade path
  swallowed the failures, and health equated "creds stored" with "AI
  configured". Observed on the django demo 2026-06-09: the key stopped being
  accepted, every LiteLLM call returned 400 `expired_key`, expand silently
  echoed the query and summarize returned `{}` for ~24h while health reported
  `ai_configured: true`. The feature: (1) **`KeyExpiryRecovery`** classifies
  auth-class failures (`ApiKeyInvalidException`, or
  `expired_key`/`invalid_api_key`/auth-error markers anywhere in the exception
  chain — budget-exhaustion errors are explicitly excluded and keep routing to
  `BudgetAwareProviderDecorator`, which owns the budget path). On a detected
  failure it records a cache-backed auth-failure marker (any `CacheDriver`; ages
  out after `AUTH_FAILURE_TTL` so a transient blip clears itself once calls
  succeed) and a persistent upgrade-needed marker (retained until cleared
  explicitly) so the state survives across requests; the stored credentials are
  left untouched and no replacement is requested. Python adaptation: PHP runs
  one short-lived process per request and relies on the platform cache's TTL
  eviction; Python serves from a long-running process and the bundled
  `InMemoryCacheDriver` does not enforce TTLs, so markers store their timestamp
  and the window is checked on read — TTL-enforcing backends (e.g. the Django
  cache) evict the entry as well, and both backend kinds agree on the semantics.
  (2) **`AiServiceAdapter.set_key_expiry_recovery()`** wires detection into all
  three AI call paths (`message`/`conversation`/`message_for_operation`): on an
  auth failure the adapter records the state and lets the request degrade
  gracefully (unexpanded query / no summary) — there is nothing to retry;
  without wiring, behavior is unchanged. (3) **`HealthChecker`** accepts an
  optional cache and reports new `ai_usable` / `ai_auth_failing` fields:
  `ai_configured` still means "credentials present", `ai_usable` additionally
  requires no cached auth-failure marker (recorded at call time — never a live
  API probe per health request), and a configured-but-unusable state now drives
  `status: degraded`. (4) A **persistent operator signal**: adapter admin UIs
  read `KeyExpiryRecovery.is_upgrade_needed()` to prompt the admin to
  re-authenticate (the email verification flow) and call `clear_upgrade_needed()`
  once that succeeds. `BudgetAwareProviderDecorator` also gains the public
  `BUDGET_MESSAGE` constant and the `is_budget_error()` chain-walking classifier
  (the PHP API this depends on); the decorator's own rethrow path now delegates
  to it. Covered by classification tests
  (expired-key/invalid-key/chain-walking/budget-exclusion by message and by
  type), marker-lifecycle tests, adapter graceful-degrade tests, and health
  tests for stored-but-expired credentials.

### Fixed
- **Enforce the modern Snowball stemmer that Pagefind 1.5.0 actually uses, and
  guard it against regression.** Pagefind stems queries at runtime with the crate
  `pagefind_stem`; for Pagefind 1.5.0 (the version the scolta packages bundle)
  that is `pagefind_stem` 1.0.0, published 2026-03-23 — *after* the Snowball 3.0
  (2024) revision — so it emits the modern algorithm (`added`→`add`,
  `organic`→`organic`, `geologist`→`geolog`, `organize`→`organiz`). The dependency
  floor was `snowballstemmer>=2.2`, which does not *enforce* that: it permits the
  pre-3.0 2.x line (`added`→`ad`, …), and an index built that way silently misses
  those queries against a Pagefind 1.5.0 index. The floor is now `>=3`. This also
  supersedes a proposed `snowballstemmer<3` pin, which had the direction backwards
  — it would have pinned the binding to the *old* algorithm under the mistaken
  belief that Pagefind used pre-3.0 Porter2.
- **Re-anchor the stemmer parity test on the Pagefind oracle instead of the
  binding's own output.** The corpus fixtures are now documented and checksummed
  as the output of `pagefind_stem` 1.0.0 itself (a golden generated by the new
  `tools/stemmer-golden` crate, pinned to that exact version), so the full-corpus
  parity test proves the binding matches *Pagefind*, not merely that it matches a
  snapshot of itself. `tests/index/test_stemmer_pagefind_parity.py` locks the
  modern tells, and `tests/index/test_stemmer_provenance.py` plus
  `tests/fixtures/stemmer-corpus/PROVENANCE.md` flag any silent re-baseline of the
  corpus against a different Pagefind stemmer revision.

## [1.0.0] - 2026-06-08

First stable release. A faithful port of `scolta-php` to Python.

### Added
- **No-fabrication guard for unrecognized named entities in the default
  `expand_query` prompt (rule 15).** A behavioral regression run of the merged
  decomposition rules (13/14) found the existing no-fabrication clause too
  narrow: rule 13 forbids inventing *members* to fill a category list, but
  nothing stopped the model from manufacturing authoritative-sounding domain
  detail for a *named entity it does not recognize* (e.g. a fictional medical
  condition expanding to confident clinical terminology — actively harmful in a
  medical/legal/safety context). New rule 15 (UNRECOGNIZED OR UNVERIFIABLE NAMED
  ENTITIES) generalizes the guard: when a query names a specific entity the model
  does not recognize as real and well-known, it must not manufacture members,
  terminology, treatments, or attributes for it, and must expand only with
  generic, neutral phrasings of the surrounding topic ("treatment for Glorptosis"
  → "medical treatment" / "therapy options" / "symptom management"). The rule
  text is byte-identical (modulo JSON escaping) to the line added to
  scolta-php's `DefaultPrompts` and scolta-core's `EXPAND_QUERY`; the prompt
  resolves server-side from this file on the Python/Django stack. Covered by
  `test_expand_query_forbids_fabricating_unverified_entities`.

### Fixed
- **Query expansion and summarization no longer return HTTP 503 on AI failure.**
  Both endpoints are non-essential search enhancements: when the AI provider
  fails for any reason other than a missing key (invalid key, rate limit,
  transport error, malformed response, budget exceeded) the handler previously
  mapped the error to HTTP 503 (`Query expansion unavailable` /
  `Summarization unavailable`). That blocked the search-enhancement path and
  spammed the client console even though search itself still worked. The root
  cause was an over-broad error contract: only the *missing-key* path degraded
  gracefully, while every other provider error 503'd. `handle_expand_query` now
  always degrades to unexpanded search (HTTP 200 with `{"terms": [query], …}`)
  and `handle_summarize` always degrades to "no summary" (HTTP 200 with empty
  data), matching the existing missing-key behavior. The distinct underlying
  error is preserved in the server log so genuine provider/config outages stay
  diagnosable. Follow-up conversations are unchanged (a follow-up *is* the
  request's primary purpose, so its 401/429/503 statuses are retained). Mirrors
  the symmetric change in `scolta-php`.

### Browser-asset re-sync — four shared `scolta.js` render-bug fixes
- Re-vendored `src/scolta/assets/js/scolta.js` byte-identically from the
  canonical `scolta-php/assets/js/scolta.js` ([tag1consulting/scolta-php#199](https://github.com/tag1consulting/scolta-php/pull/199)).
  The browser script is reused verbatim (no Python-side logic), so this is an
  asset-only sync. Fixes carried: (1) **zero-result blank panel** — a search
  with no matches blanked the result panel for the whole asynchronous AI
  query-expansion round-trip (a multi-second blank on a slow endpoint) instead
  of showing "No results found."; it now shows a neutral "Searching…"
  in-progress state during expansion, then the terminal state once it settles;
  (2) **"1 results"** — the count header now pluralizes (`1 result` vs
  `N results`); (3) **doubled quotes** — a quoted-phrase query no longer renders
  as `""merge conflict""`; (4) **AI-summary citation dedup** — `buildLLMContext`
  collapses results sharing a resolved URL so the summarizer no longer cites the
  same source repeatedly. The re-sync also carries scolta-php main's
  previously-unsynced `computeUnionFacetCounts` facet-count fix.
- Updated `tests/js/` to match the synced script: ported the current
  `faceting.test.js` from scolta-php (its source-structure assertions now expect
  the `computeQueryFacetCounts(query, baseFilters, meaningfulTerms, isForcedPhrase)`
  signature + the OR-fallback `computeUnionFacetCounts` union path) and added
  `shared-render-bugs.test.js`, the JSDOM regression suite for the four fixes
  above (each case fails on the pre-fix script). The full Jest suite passes
  (243 passed, 1 skipped).

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
