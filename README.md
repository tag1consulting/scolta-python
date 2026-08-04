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

## Selecting an AI provider is always manual

Scolta ships with **no AI provider selected**. `ai_provider` is empty until
somebody sets it, and while it is empty AI features are simply off: search
works, no provider is assumed, and Anthropic in particular is not silently
assumed. There is no default anywhere.

A developer sets `ai_provider` in code or settings; in `scolta-django` an
operator picks one in the admin. Both are explicit acts. This is a
going-forward rule: a site that already persisted a provider keeps it, and
nothing rewrites an existing value.

**Amazee.ai is never enabled on its own.** No credential is provisioned and no
outbound Amazee call is made on a request, cron, install or activation path for
a site that has not opted in. `AutoProvisioner.ensure_ai_available()` — whose
name predates the policy — establishes nothing: it only re-resolves gateway
model names against a key already on disk, which is reachable only for a site
that already connected. A connection is established solely by an explicit call
to `AmazeeTrialProvisioner.provision()` (the free demo, no email required) or
`AmazeeAccountUpgrader` (the email → verification code → region flow that
attaches an amazee.ai account). Amazee support is email-only, mirroring
amazee.ai's own `ai_provider_amazeeio` module; there is no paste-your-API-key
path.

Which of those two established a connection is **recorded** at the time it
happens, through `ProvenanceAwareConfigStorage`, so a surface can report a demo
or an account from a stored fact instead of a guess. Credentials with no
recorded origin claim nothing.

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
