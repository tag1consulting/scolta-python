"""Ported from tests/Config/FilterFieldDescriptionValidationTest.php.

The PHP test defines a private helper extractEnumeratedValues() and exercises
it; the helper is the regression surface (filter_field_descriptions strings
used in adapter LLM prompts must enumerate values machine-parseably). The
helper is ported here as a test-local function.
"""

import re

import pytest

_VALUES_RE = re.compile(r"(?:Valid v|V)alues:\s*(.+)", re.IGNORECASE)


def extract_enumerated_values(description: str) -> list[str]:
    """Extract enumerated values from a filter_field_descriptions string.

    Recognizes "Valid values: Foo, Bar, Baz" and "Values: Foo, Bar, Baz".
    Returns [] if no enumerated list is found.
    """
    m = _VALUES_RE.search(description)
    if not m:
        return []
    raw = m.group(1)
    values = [v.strip(" \t\n\r\0\x0b\"'") for v in raw.split(",")]
    return [v for v in values if v != ""]


def test_extracts_valid_values_format():
    desc = "Subject area or domain. Valid values: Arts, Biography, Science"
    assert extract_enumerated_values(desc) == ["Arts", "Biography", "Science"]


def test_extracts_values_with_quotes():
    desc = 'Geographic region. Values: Africa, Americas, "Global / Multiple Regions", Oceania'
    values = extract_enumerated_values(desc)
    assert "Africa" in values
    assert "Americas" in values
    assert "Global / Multiple Regions" in values
    assert "Oceania" in values


def test_returns_empty_for_freeform_description():
    desc = "Total number of words in the article (typically 2,000–15,000)"
    assert extract_enumerated_values(desc) == []


_PROVIDER = {
    "topics": (
        "Subject area or domain. Valid values: Arts, Biography, Engineering, "
        "Geography, History, Mathematics, Medicine, Military, Nature, Philosophy, "
        "Religion, Science, Society, Sports, Technology",
        [
            "Arts",
            "Biography",
            "Engineering",
            "Geography",
            "History",
            "Mathematics",
            "Medicine",
            "Military",
            "Nature",
            "Philosophy",
            "Religion",
            "Science",
            "Society",
            "Sports",
            "Technology",
        ],
    ),
    "era": (
        'Historical period. Values: "Ancient (before 500 CE)", '
        '"Medieval (500-1500)", "Early Modern (1500-1800)", '
        '"Modern (1800-1945)", "Contemporary (1945-present)", "Timeless"',
        [
            "Ancient (before 500 CE)",
            "Medieval (500-1500)",
            "Early Modern (1500-1800)",
            "Modern (1800-1945)",
            "Contemporary (1945-present)",
            "Timeless",
        ],
    ),
    "region": (
        "Geographic region. Values: Africa, Americas, Antarctica, Asia, Europe, "
        '"Global / Multiple Regions", "Not Geographic", Oceania, Space',
        [
            "Africa",
            "Americas",
            "Antarctica",
            "Asia",
            "Europe",
            "Global / Multiple Regions",
            "Not Geographic",
            "Oceania",
            "Space",
        ],
    ),
}


@pytest.mark.parametrize("field,description,actual", [(k, *v) for k, v in _PROVIDER.items()])
def test_description_values_exist_in_index(field, description, actual):
    described = extract_enumerated_values(description)
    assert described, f"No enumerated values in description for '{field}'"
    missing = set(described) - set(actual)
    assert not missing, f"'{field}' description references values not in index: {missing}"


@pytest.mark.parametrize("field,description,actual", [(k, *v) for k, v in _PROVIDER.items()])
def test_index_values_appear_in_description(field, description, actual):
    described = extract_enumerated_values(description)
    assert described, f"No enumerated values in description for '{field}'"
    undocumented = set(actual) - set(described)
    assert not undocumented, f"'{field}' has index values not in description: {undocumented}"


def test_detects_invented_values():
    description = "Subject area (Arts, Biology, Chemistry, Physics, etc.)"
    # Parenthesized "etc." lists are intentionally not treated as exhaustive.
    assert extract_enumerated_values(description) == []
