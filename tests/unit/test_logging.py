"""Logging configuration: redaction on every handler and honest degradation."""

from __future__ import annotations

import io
import logging
import re

import pytest

from aurora.observability.logging import (
    LOG_LEVELS,
    LOGGER_NAME,
    configure_logging,
    validate_level,
)


@pytest.fixture()
def clean_logger():
    logger = logging.getLogger(LOGGER_NAME)
    yield logger
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_messages_are_written_to_stderr_and_file(tmp_path, clean_logger):
    log_file = tmp_path / "aurora.log"
    stream = io.StringIO()
    logger = configure_logging(level="INFO", log_file=log_file, stream=stream)

    logger.info("scan started for %s", "lab.test")

    assert "scan started for lab.test" in stream.getvalue()
    assert "scan started for lab.test" in log_file.read_text(encoding="utf-8")


def test_credentials_never_reach_the_file(tmp_path, clean_logger):
    log_file = tmp_path / "aurora.log"
    logger = configure_logging(level="DEBUG", log_file=log_file, stream=io.StringIO())

    logger.info("Authorization: Bearer abcdefghijklmnop")
    logger.debug("request url %s", "/login?password=hunter2")

    content = log_file.read_text(encoding="utf-8")
    assert "abcdefghijklmnop" not in content
    assert "hunter2" not in content
    assert "<redacted>" in content


def test_timestamps_are_utc(tmp_path, clean_logger):
    log_file = tmp_path / "aurora.log"
    logger = configure_logging(level="INFO", log_file=log_file, stream=io.StringIO())
    logger.info("tick")
    line = log_file.read_text(encoding="utf-8").strip()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z INFO", line)


def test_handlers_are_not_duplicated_when_reconfigured(clean_logger):
    configure_logging(level="INFO", stream=io.StringIO())
    configure_logging(level="INFO", stream=io.StringIO())
    logger = logging.getLogger(LOGGER_NAME)
    assert len(logger.handlers) == 1
    assert logger.propagate is False


def test_unusable_log_file_degrades_to_stream(tmp_path, clean_logger):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    logger = configure_logging(level="WARNING", log_file=blocked, stream=io.StringIO())
    # Only the console handler survives; the command must keep working.
    assert len(logger.handlers) == 1


def test_unknown_level_is_rejected():
    with pytest.raises(ValueError):
        validate_level("CHATTY")


def test_level_names_are_normalised():
    assert validate_level("info") == "INFO"
    assert LOG_LEVELS == ("DEBUG", "INFO", "WARNING", "ERROR")
