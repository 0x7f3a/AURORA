"""Logging setup.

Design notes:

* the ``aurora`` logger never propagates, so embedding AURORA as a library does
  not duplicate records into a host application's root handlers;
* every handler carries :class:`~aurora.observability.redaction.RedactionFilter`,
  so a credential cannot reach a log sink through an unguarded handler;
* a log file that cannot be opened degrades to stderr output with a warning
  instead of aborting the command the operator actually asked for;
* timestamps are UTC, because assessment timelines are compared across hosts.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import TextIO

from aurora.observability.redaction import RedactionFilter

__all__ = ["LOGGER_NAME", "LOG_LEVELS", "configure_logging", "validate_level"]

LOGGER_NAME = "aurora"
LOG_LEVELS: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR")


class _UtcFormatter(logging.Formatter):
    converter = time.gmtime


def validate_level(level: str) -> str:
    """Normalise and validate a level name, raising ``ValueError`` if unknown."""

    candidate = level.strip().upper()
    if candidate not in LOG_LEVELS:
        raise ValueError(f"unknown log level {level!r}; expected one of {', '.join(LOG_LEVELS)}")
    return candidate


def configure_logging(
    *,
    level: str = "WARNING",
    log_file: Path | None = None,
    stream: TextIO | None = None,
) -> logging.Logger:
    """(Re)configure the ``aurora`` logger and return it."""

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(validate_level(level))
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = _UtcFormatter(
        "%(asctime)sZ %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    console_handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RedactionFilter())
    logger.addHandler(console_handler)

    if log_file is not None:
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            # Opened eagerly (no delay) so an unusable path fails here, where it
            # can be reported, instead of on the first log record.
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
        except OSError as exc:
            logger.warning("log file unavailable (%s); logging to stderr only", exc)
        else:
            file_handler.setFormatter(formatter)
            file_handler.addFilter(RedactionFilter())
            logger.addHandler(file_handler)

    return logger
