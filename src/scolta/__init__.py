"""Scolta — AI-powered search with Pagefind (Python language binding).

This is a faithful port of the PHP binding (scolta-php). It produces a
Pagefind-compatible static index in-process (pure-Python indexer, the
default) and proxies AI calls for query expansion, summarization, and
follow-ups. The browser-side scoring engine (scolta-core compiled to WASM)
is reused verbatim from the shared asset bundle.
"""

__version__ = "1.1.0.dev0"
