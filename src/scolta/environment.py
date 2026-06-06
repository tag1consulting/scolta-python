"""Hosting environment detection (port of ``Environment\\*``).

Detects managed hosting via environment variables. The PHP version also checks
PHP-only constants (IS_WPE, IS_FLYWHEEL, IS_PRESSABLE) which have no Python
equivalent and are omitted; env-var detection covers the rest.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

_MIB = 1024 * 1024


class HostingEnvironment(str, Enum):
    WP_ENGINE = "wp_engine"
    KINSTA = "kinsta"
    FLYWHEEL = "flywheel"
    PRESSABLE = "pressable"
    PANTHEON = "pantheon"
    ACQUIA = "acquia"
    PLATFORM_SH = "platform_sh"
    VAPOR = "vapor"
    RESTRICTED_EXEC = "restricted_exec"
    STANDARD = "standard"


@dataclass(frozen=True)
class HostingConstraints:
    max_execution_time: int = 0
    memory_limit: int = 0
    exec_available: bool = True
    ephemeral_filesystem: bool = False
    note: str = ""


class HostingDetector:
    @staticmethod
    def detect() -> HostingEnvironment:
        getenv = os.environ.get
        if getenv("WPE_APIKEY"):
            return HostingEnvironment.WP_ENGINE
        if getenv("KINSTA_CACHE_ZONE"):
            return HostingEnvironment.KINSTA
        if getenv("PANTHEON_ENVIRONMENT"):
            return HostingEnvironment.PANTHEON
        if getenv("AH_SITE_ENVIRONMENT"):
            return HostingEnvironment.ACQUIA
        if getenv("PLATFORM_ENVIRONMENT"):
            return HostingEnvironment.PLATFORM_SH
        if getenv("VAPOR_SSM_PATH") or getenv("AWS_LAMBDA_FUNCTION_NAME"):
            return HostingEnvironment.VAPOR
        return HostingEnvironment.STANDARD

    @staticmethod
    def constraints() -> HostingConstraints:
        env = HostingDetector.detect()
        if env == HostingEnvironment.PANTHEON:
            return HostingConstraints(
                max_execution_time=120,
                exec_available=True,
                note="Pantheon has a 120-second hard limit. Use Terminus for large sites.",
            )
        if env == HostingEnvironment.ACQUIA:
            return HostingConstraints(
                max_execution_time=300,
                memory_limit=128 * _MIB,
                exec_available=True,
                note="Acquia default memory is 128MB. Use indexer=python for large sites.",
            )
        if env in (
            HostingEnvironment.WP_ENGINE,
            HostingEnvironment.KINSTA,
            HostingEnvironment.FLYWHEEL,
            HostingEnvironment.PRESSABLE,
            HostingEnvironment.RESTRICTED_EXEC,
        ):
            return HostingConstraints(
                exec_available=False,
                note="exec() disabled. Python indexer used automatically.",
            )
        if env == HostingEnvironment.VAPOR:
            return HostingConstraints(
                max_execution_time=900,
                ephemeral_filesystem=True,
                note="Lambda filesystem is ephemeral. Configure persistent state storage.",
            )
        return HostingConstraints()

    @staticmethod
    def describe() -> str:
        env = HostingDetector.detect()
        constraints = HostingDetector.constraints()
        desc = "Standard hosting" if env == HostingEnvironment.STANDARD else env.value.replace("_", " ").title()
        if constraints.note != "":
            desc += " — " + constraints.note
        return desc
