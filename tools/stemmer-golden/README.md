# stemmer-golden — Pagefind query-stemmer parity oracle

`scolta` builds a Pagefind index at publish time. Pagefind stems **queries** at
search time with its bundled WASM, which is the Rust crate
[`pagefind_stem`](https://crates.io/crates/pagefind_stem). If the binding's
build-time stems differ from Pagefind's runtime query stems, the index silently
misses those queries. So the binding's stemmer must match `pagefind_stem`, not
its own backend's idea of "Snowball".

This tool generates the golden stems straight from `pagefind_stem`, pinned to the
exact version the targeted Pagefind release locks. The
`tests/fixtures/stemmer-corpus/<lang>/expected-stems.txt` fixtures are its output,
and the stemmer parity tests assert the Python binding reproduces them exactly.

## Version mapping (the part that must be kept honest)

| Targeted Pagefind | `Cargo.lock` pins | Algorithm revision |
| --- | --- | --- |
| **1.5.0** | `pagefind_stem` **1.0.0** (checksum `8dfa810b…`) | modern Snowball (post-3.0 / 2024): `added`→`add` |

`pagefind_stem` 0.2.0 (2022) was the pre-3.0 algorithm (`added`→`ad`); the 1.0.0
release (2026-03-23) moved to the revised algorithm. No published
`snowballstemmer` release reproduces 1.0.0 byte-for-byte across all 14
languages (3.0.x predates the `english.sbl` fix; 3.1.x adds apostrophe/elision
handling the crate lacks), so the binding **vendors** the compiler output from
the exact commit the crate was built from — see
`src/scolta/index/snowball/PROVENANCE.md`. This oracle exists to keep the
fixtures those vendored stemmers are tested against reproducible from Pagefind's
own stemmer.

## Regenerating

Requires a Rust toolchain. To re-target a new Pagefind release:

1. Read that Pagefind tag's `Cargo.lock`, find the `pagefind_stem` version.
2. Update the pin in `Cargo.toml` and the table above + `PROVENANCE.md`.
3. Run, for each language:

   ```sh
   cargo run --release -- en ../../tests/fixtures/stemmer-corpus/en/words.txt \
       ../../tests/fixtures/stemmer-corpus/en/expected-stems.txt
   ```

4. Update the sha256 manifest in `PROVENANCE.md`; the provenance test will fail
   until it matches, forcing a conscious re-baseline.

This crate is `publish = false` and is not part of the Python package; it only
exists to keep the fixtures reproducible from Pagefind's own stemmer.
