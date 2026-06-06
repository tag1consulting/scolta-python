"""Token tests (ported from tests/Index/TokenTest.php).

The PHP testTokenUsesLessMemoryThanEquivalentArray guards a PHP-specific memory
layout (final readonly class vs 3-key array) and does not translate to Python;
the Token here is a frozen slots dataclass, which is the equivalent compact
representation. Only the behavioural property test is ported.
"""

from scolta.index.token import Token


def test_properties_are_readable():
    token = Token("hello", "Hello", 42)
    assert token.stem == "hello"
    assert token.original == "Hello"
    assert token.position == 42


def test_token_is_slotted():
    # Equivalent of the PHP memory test: confirm Token uses __slots__ (no __dict__).
    token = Token("a", "b", 1)
    assert not hasattr(token, "__dict__")
