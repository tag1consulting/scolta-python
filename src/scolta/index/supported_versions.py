"""Pagefind version tracking (port of ``SupportedVersions``)."""

from __future__ import annotations

TESTED_VERSIONS = ["1.3.0", "1.4.0", "1.5.0"]
BUNDLED_VERSION = "1.5.0"
MIN_VERSION = "1.3.0"
INCOMPATIBLE_VERSIONS: dict[str, str] = {}


class SupportedVersions:
    TESTED_VERSIONS = TESTED_VERSIONS
    BUNDLED_VERSION = BUNDLED_VERSION
    MIN_VERSION = MIN_VERSION
    INCOMPATIBLE_VERSIONS = INCOMPATIBLE_VERSIONS

    @staticmethod
    def is_supported(version: str) -> bool:
        return version in TESTED_VERSIONS

    @staticmethod
    def is_incompatible(version: str) -> bool:
        return version in INCOMPATIBLE_VERSIONS

    @staticmethod
    def warn(version: str) -> str | None:
        if SupportedVersions.is_incompatible(version):
            return f"Pagefind version {version} is INCOMPATIBLE: {INCOMPATIBLE_VERSIONS[version]}"
        if not SupportedVersions.is_supported(version):
            return (
                f"Pagefind version {version} has NOT been tested with Scolta's Python "
                f"indexer. Search may work, but results are not guaranteed. "
                f"Tested versions: {', '.join(TESTED_VERSIONS)}."
            )
        return None

    @staticmethod
    def get_version_for_metadata() -> str:
        return BUNDLED_VERSION

    @staticmethod
    def get_version_info() -> str:
        return (
            f"Bundled Pagefind: {BUNDLED_VERSION} | "
            f"Tested versions: {', '.join(TESTED_VERSIONS)} | Minimum: {MIN_VERSION}"
        )
