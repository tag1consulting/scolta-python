"""Indexer backend resolver (port of ``IndexerResolver``).

Design rule (matched exactly): 'auto' always means the Python indexer. 'binary'
resolves the Pagefind binary and uses it only if present, otherwise logs a
notice and falls back to Python. Any unrecognized value -> Python.
"""

from __future__ import annotations

import logging

_DEFAULT_LOGGER = logging.getLogger("scolta.index")


class IndexerResolver:
    def __init__(self, binary, logger=None) -> None:
        self.binary = binary
        self.logger = logger if logger is not None else _DEFAULT_LOGGER

    def resolve(self, effective_indexer: str) -> str:
        """Return 'python' or 'binary'."""
        if effective_indexer == "python":
            self.logger.info("[scolta] Using Python indexer.")
            return "python"

        if effective_indexer == "binary":
            path = self.binary.resolve()
            if path is not None:
                self.logger.info("[scolta] Using binary indexer: %s.", path)
                return "binary"
            status = self.binary.status()
            self.logger.info(
                "[scolta] Falling back to Python indexer: binary not available. %s",
                status["message"],
            )
            return "python"

        # 'auto' or any unrecognized value: always the Python indexer.
        self.logger.info("[scolta] Using Python indexer.")
        return "python"
