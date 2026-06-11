# scolta-python

AI-powered search with [Pagefind](https://pagefind.app/) — the Python language
binding of [Scolta](https://tag1.com). A faithful port of `scolta-php`.

Scolta is a scoring/ranking/AI layer over Pagefind, a static client-side search
engine. The browser-side scoring engine (`scolta-core` compiled to WebAssembly)
re-ranks Pagefind results and drives an optional LLM tier (query expansion,
summarization, follow-ups). This binding does the server-side work:

- gets content out of the application,
- **builds and maintains a Pagefind-compatible index in-process** (pure-Python
  indexer — no Pagefind binary required at runtime), with an input-side token
  cache so re-indexing after a content edit only re-tokenizes changed pages,
- proxies AI calls (Anthropic native + any OpenAI-compatible endpoint),
- serves the reused WASM/JS/CSS asset bundle and exposes config.

The pure-Python indexer is the **default** (`indexer: auto`). The Pagefind
binary pipeline is ported too but is **opt-in** (`indexer: binary`), with the
same auto-fallback-to-Python-when-the-binary-is-unavailable behaviour as the PHP
binding.

Platform integration for Django/Wagtail lives in the companion `scolta-django`
package.

## Status

Complete port of `scolta-php`, released as 1.0.x. See `CLAUDE.md` for the
porting conventions.

## Requirements

- Python 3.10+
- Optional: `PyICU` (the `[icu]` extra) for higher-quality Unicode diacritic
  normalization in the tokenizer. Without it the tokenizer uses a `strtr`-style
  fallback, exactly as `scolta-php` does without `ext-intl`.

## Development

```sh
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run pytest
uv run ruff check
```
