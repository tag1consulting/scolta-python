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
Python Stemmer reproduces those committed wamania stems for every word.

Run (deprecation notices from a vendor lib on PHP 8.5 are harmless):

```sh
php -d error_reporting=0 html_harness.php
php -d error_reporting=0 tokenizer_harness.php
```
