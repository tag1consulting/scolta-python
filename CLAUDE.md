# scolta-python — porting conventions

This package is a faithful port of `scolta-php` (`../scolta-php`). The PHP source
is the reference for behaviour — read it before porting each piece.

## Ground rules

- **Parity over idiom.** Match observable behaviour of the PHP code. Where the
  Pagefind on-disk format is involved (CBOR, delta encoding, format writers,
  tokenizer boundaries, hashing), reproduce it exactly — the shared WASM rejects
  a non-conforming index. Internal-only formats (token cache, build chunks) use
  Python-native serialization (msgpack/JSON), not PHP `serialize()` parity.
- **The pure-Python indexer is the default** (`indexer: auto`). The Pagefind
  binary path is opt-in (`indexer: binary`) and falls back to Python when the
  binary is unavailable, mirroring `IndexerResolver` exactly.
- **Reuse the WASM/JS/CSS assets verbatim** from `../scolta-php/assets/` via a
  fail-closed extension allowlist. Never ship `.sha256`, `.d.ts`, `.map`.
- **No AI attribution** anywhere (commits, comments, docstrings, docs).
- **Tests are ported 1:1** from `../scolta-php/tests/` (PHPUnit → pytest),
  preserving each test's regression intent. WASM/browser suites (`tests/js/`,
  `tests/E2E/`) stay in `scolta-php`; the Amazee subsystem is deferred.

## Naming

- PHP camelCase properties/methods → Python snake_case. The PHP `fromArray`
  already accepted snake_case config keys, so the config wire contract is
  unchanged; `from_dict` is the Python entry point.

## Layout

- `src/scolta/` — the binding (config, content, ai/, index/, html, export, …).
- `src/scolta/index/` — the full Pagefind in-process indexer subsystem.
- `tests/` — pytest mirror of `../scolta-php/tests/`.

## Toolchain

- `uv` for env/deps, `pytest` for tests, `ruff` for lint.
- Python floor 3.10. `PyICU` is an optional `[icu]` extra (mirrors PHP's
  `ext-intl` being a Composer "suggest").
