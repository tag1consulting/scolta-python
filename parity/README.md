# Parity harnesses

These PHP scripts regenerate the committed golden files that the Python parity
tests assert against. They run the **real** scolta-php classes and dump their
output, so the Python port is checked byte-for-byte against PHP behaviour. The
golden files are committed, so the Python test suite runs PHP-free in CI; the
harnesses only need to be re-run when the PHP reference changes.

Requires a local `../../scolta-php` with `composer install` done.

- `html_harness.php` → `tests/fixtures/html_parity.json`
  Cleaner output for the 20 recipe fixtures + edge-case units, and
  PagefindHtmlBuilder output for 14 cases.
- `tokenizer_harness.php` → `tests/fixtures/tokenizer_parity.json`
  Full token streams (stem, original, position) from the real Tokenizer for 29
  cases (diacritics, camelCase, hyphen, CJK/Hiragana/Katakana/Hangul bigrams,
  emoji, contractions, German ß, real recipe prose).

The stemmer corpus under `tests/fixtures/stemmer-corpus/` (en/fr/de/es/ru) is
copied verbatim from scolta-php; `tests/index/test_stemmer.py` asserts the
Python Stemmer reproduces those committed (canonical Snowball) stems for every
word.

- `index_harness.php` → `tests/fixtures/index_parity.json`
  Full Pagefind index built from the recipe fixtures via both writers, decoded
  to a canonical order-independent structure; the PHP-built index/pages (so the
  Python test can drive the Python writers with an identical index, isolating
  the writer); and a controlled alphabetic-only corpus dumped as byte-exact
  uncompressed payloads.

Notes:
- The Python writers sort terms lexicographically (canonical Rust-Pagefind /
  WASM order). PHP `sort()` (SORT_REGULAR) is non-transitive on numeric tokens,
  so its chunk partitioning is algorithm-dependent; per-word postings are
  identical either way, which is why the recipe gate is structural.
- `wamania/php-stemmer` diverges from canonical Snowball on a few words
  (`adding`→`ad`, `paste`→`past`); Python (the vendored Snowball stemmers in
  `src/scolta/index/snowball/`, generated from the same commit `pagefind_stem`
  1.0.0 was) follows the canonical reference + rust-stemmers, so it is the
  correct side. This is asserted explicitly in `test_format_parity.py`.

Run (deprecation notices from a vendor lib on PHP 8.5 are harmless):

```sh
php -d error_reporting=0 html_harness.php
php -d error_reporting=0 tokenizer_harness.php
```
