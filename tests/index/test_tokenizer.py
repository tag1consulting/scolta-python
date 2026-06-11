"""Tokenizer tests — Parity Gate #2.

Ports tests/Index/TokenizerTest.php and tests/Tokenizer/CjkBigramTest.php (1:1),
plus a golden parity test that asserts the Python tokenizer reproduces the real
PHP Tokenizer's full token stream (stem, original, position) byte-for-byte. The
golden (tests/fixtures/tokenizer_parity.json) is generated from scolta-php's
actual Tokenizer via parity/tokenizer_harness.php.
"""

import json
from pathlib import Path

import pytest

from scolta.index.token import Token
from scolta.index.tokenizer import Tokenizer

_GOLDEN = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "tokenizer_parity.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture
def tokenizer():
    return Tokenizer()


def stems(tokenizer, text):
    return [t.stem for t in tokenizer.tokenize(text)]


# -- Parity gate: full token stream vs real PHP Tokenizer ---------------------


@pytest.mark.parametrize("name", sorted(_GOLDEN["tokenizer_cases"].keys()))
def test_tokenizer_golden_parity(name, tokenizer):
    case = _GOLDEN["tokenizer_cases"][name]
    got = [
        [t.stem, t.original, t.position] for t in tokenizer.tokenize(case["input"], case["start"])
    ]
    assert got == case["tokens"]


# -- TokenizerTest.php (1:1) --------------------------------------------------


def test_basic_words(tokenizer):
    assert [t.stem for t in tokenizer.tokenize("Hello World")] == ["hello", "world"]


def test_diacritic_normalization(tokenizer):
    tokens = tokenizer.tokenize("café")
    assert len(tokens) == 1
    assert isinstance(tokens[0], Token)
    assert tokens[0].stem == "cafe"
    assert tokens[0].original == "café"


def test_hyphen_splitting(tokenizer):
    s = stems(tokenizer, "mother-in-law")
    assert "mother" in s
    assert "in" in s
    assert "law" in s


def test_camel_case_splitting(tokenizer):
    s = stems(tokenizer, "myPage")
    assert "my" in s
    assert "page" in s


def test_numbers(tokenizer):
    assert "123abc" in stems(tokenizer, "123abc")


def test_empty_input(tokenizer):
    assert tokenizer.tokenize("") == []


def test_whitespace_only(tokenizer):
    assert tokenizer.tokenize("   ") == []


def test_position_tracking(tokenizer):
    tokens = tokenizer.tokenize("hello world")
    assert tokens[0].position == 0
    assert tokens[1].position == 6


def test_start_position_offset(tokenizer):
    assert tokenizer.tokenize("hello", 100)[0].position == 100


def test_punctuation_stripped(tokenizer):
    s = stems(tokenizer, "hello, world!")
    assert "hello" in s
    assert "world" in s


def test_multiple_spaces(tokenizer):
    assert stems(tokenizer, "hello   world") == ["hello", "world"]


def test_unicode_lowercasing(tokenizer):
    assert tokenizer.tokenize("ÜBER")[0].stem == "uber"


def test_cjk_splitting(tokenizer):
    tokens = tokenizer.tokenize("你好世界")
    assert len(tokens) == 3
    s = [t.stem for t in tokens]
    assert "你好" in s
    assert "好世" in s
    assert "世界" in s


def test_mixed_content(tokenizer):
    assert len(tokenizer.tokenize("Hello café 123")) >= 3


# -- CjkBigramTest.php (1:1) --------------------------------------------------


def test_pure_cjk_four_chars(tokenizer):
    s = stems(tokenizer, "人工智能")
    assert "人工" in s
    assert "工智" in s
    assert "智能" in s
    for single in ("人", "工", "智", "能"):
        assert single not in s


def test_single_cjk_char_emitted_alone(tokenizer):
    assert stems(tokenizer, "猫") == ["猫"]


def test_mixed_latin_cjk_latin(tokenizer):
    s = stems(tokenizer, "Hello人工智能World")
    assert "hello" in s
    assert "人工" in s
    assert "工智" in s
    assert "智能" in s
    assert "world" in s


def test_hiragana_bigrams(tokenizer):
    s = stems(tokenizer, "おはよう")
    assert "おは" in s
    assert "はよ" in s
    assert "よう" in s
    for single in ("お", "は", "よ", "う"):
        assert single not in s


def test_korean_bigrams(tokenizer):
    s = stems(tokenizer, "안녕하세요")
    assert "안녕" in s
    assert "녕하" in s
    assert "하세" in s
    assert "세요" in s
    for single in ("안", "녕", "하", "세", "요"):
        assert single not in s


def test_two_cjk_chars(tokenizer):
    s = stems(tokenizer, "日本")
    assert "日本" in s
    assert len(s) == 1


def test_pure_latin(tokenizer):
    assert stems(tokenizer, "hello world") == ["hello", "world"]


def test_russian_unaffected(tokenizer):
    s = stems(tokenizer, "физика")
    assert s
    for stem in s:
        assert len(stem) > 1
