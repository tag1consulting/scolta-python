# Maintaining scolta-python

The Python binding: a Pagefind index builder plus an AI proxy. Published on PyPI as `scolta`.

Everything true of more than one Scolta repo lives in
[scolta-core/MAINTAINING.md](https://github.com/tag1consulting/scolta-core/blob/main/MAINTAINING.md):
the version rules, the release order, the fleet checks, the rules every repo shares. How the browser
bundle is copied and checked is in
[scolta-core/ASSETS.md](https://github.com/tag1consulting/scolta-core/blob/main/ASSETS.md).

**What it is.** The Python binding, a faithful port of `scolta-php`. It depends on `scolta-core` (the
vendored WASM). `scolta-django` depends on this.

**Where the version lives.** `src/scolta/__init__.py` `__version__`, and only there. `pyproject.toml`
declares `dynamic = ["version"]` and reads it through `[tool.hatch.version]`, so the package metadata and
`scolta.__version__` cannot drift apart. Set one place, not two.

**Where it publishes.** PyPI, as `scolta` (a flat namespace: ownership is shown by the PyPI org, not a
name prefix). To confirm: `pip install scolta` in a clean venv resolves the new version.

**CI checks.** `test` (ruff lint, `ruff format --check`, and pytest across Python 3.10 to 3.13, with
Chromium installed so the browser E2E runs rather than skipping), `Build & validate dist artifacts`
(`uv build`, `uvx twine check dist/*`, then `scripts/validate-dist.py` for content and size), and
`JS tests (Jest)` for the shared JS suite under `tests/js`. The `test` job also checks out scolta-core so
the prompt-text identity gate runs against the real `src/prompts.rs` instead of skipping.

**On release day.** Release this before scolta-django. There is no release workflow, so a tag
publishes nothing: rehearse on TestPyPI (`uv build` → `uvx twine check dist/*` → upload → install in a
clean venv), then upload for real with `twine upload dist/*` by hand. CI's `dist` job is the only gate in
front of that upload, and it runs on every pull request.

**Watch out for.**

- This package carries the browser bundle at `src/scolta/assets/` and re-vendors it with
  `python scripts/vendor_assets.py` from a sibling `../scolta-php` checkout. The copy is fail-closed by
  extension allowlist, so a `.sha256`, `.d.ts` or `.map` can never ship. Never hand-edit an asset here.
- Nothing checks that copy against scolta-php. Unlike scolta-drupal and scolta-wp there is no
  `assets-in-sync` job, so a stale bundle goes unnoticed until someone looks.
- The Snowball stemmers under `src/scolta/index/snowball/` are vendored, not a dependency, because
  no published `snowballstemmer` release reproduces Pagefind's `pagefind_stem` byte for byte. Regenerate
  them with `scripts/generate-stemmers.sh` against the pinned crate; the stemmer parity tests guard it.
- `PyICU` is an optional `[icu]` extra, mirroring `ext-intl` being a Composer "suggest" in scolta-php.
  Without it the tokenizer falls back to a mapping, exactly as PHP does.
