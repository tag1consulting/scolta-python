"""Ported from tests/Index/SupportedVersionsTest.php (1:1)."""

import re

from scolta.index.supported_versions import SupportedVersions


def test_bundled_version_is_in_tested_versions():
    assert SupportedVersions.BUNDLED_VERSION in SupportedVersions.TESTED_VERSIONS


def test_is_supported_true_for_tested_versions():
    for v in SupportedVersions.TESTED_VERSIONS:
        assert SupportedVersions.is_supported(v)


def test_is_supported_false_for_unknown_version():
    assert SupportedVersions.is_supported("99.99.99") is False


def test_warn_returns_none_for_supported_version():
    assert SupportedVersions.warn(SupportedVersions.BUNDLED_VERSION) is None


def test_warn_returns_message_for_unsupported_version():
    w = SupportedVersions.warn("99.99.99")
    assert w is not None
    assert "NOT been tested" in w
    assert "99.99.99" in w


def test_warn_returns_message_for_empty_version():
    assert SupportedVersions.warn("") is not None


def test_get_version_for_metadata():
    assert SupportedVersions.get_version_for_metadata() == SupportedVersions.BUNDLED_VERSION


def test_get_version_info_contains_versions():
    info = SupportedVersions.get_version_info()
    assert SupportedVersions.BUNDLED_VERSION in info
    assert SupportedVersions.MIN_VERSION in info


def test_min_version_is_in_tested_versions():
    assert SupportedVersions.MIN_VERSION in SupportedVersions.TESTED_VERSIONS


def test_is_incompatible_false_for_tested_version():
    assert SupportedVersions.is_incompatible(SupportedVersions.BUNDLED_VERSION) is False


def test_version_format_is_valid_semver():
    assert re.match(r"^\d+\.\d+\.\d+$", SupportedVersions.BUNDLED_VERSION)
