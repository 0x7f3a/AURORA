"""Credential redaction must hold for headers, URLs, free text and log records."""

from __future__ import annotations

import io
import logging

from aurora.observability.redaction import (
    REDACTED,
    SENSITIVE_HEADERS,
    RedactionFilter,
    redact_headers,
    redact_text,
    redact_url,
)


def test_sensitive_headers_are_replaced():
    headers = {
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature",
        "Cookie": "session=abc123",
        "Set-Cookie": "session=abc123; HttpOnly",
        "Content-Type": "text/html; charset=utf-8",
    }
    result = redact_headers(headers)
    assert result["Authorization"] == REDACTED
    assert result["Cookie"] == REDACTED
    assert result["Set-Cookie"] == REDACTED
    assert result["Content-Type"] == "text/html; charset=utf-8"


def test_header_redaction_is_case_insensitive():
    assert redact_headers({"AUTHORIZATION": "Basic dXNlcjpwYXNz"})["AUTHORIZATION"] == REDACTED


def test_header_redaction_accepts_pairs():
    result = redact_headers([("x-api-key", "secret"), ("accept", "text/html")])
    assert result == {"x-api-key": REDACTED, "accept": "text/html"}


def test_url_userinfo_is_removed():
    redacted = redact_url("https://operator:s3cret@lab.test/admin")
    assert "operator" not in redacted
    assert "s3cret" not in redacted
    assert redacted.startswith("https://")
    assert redacted.endswith("/admin")


def test_url_sensitive_query_values_are_removed():
    redacted = redact_url("https://lab.test/reset?token=abc123&page=2")
    assert "abc123" not in redacted
    assert "page=2" in redacted
    assert f"token={REDACTED}" in redacted


def test_relative_urls_still_redact():
    assert redact_url("/search?q=test&password=hunter2") == f"/search?q=test&password={REDACTED}"


def test_header_lines_in_text_are_redacted():
    message = "GET /admin\nAuthorization: Bearer abcdefghijklmnop\nHost: lab.test"
    redacted = redact_text(message)
    assert "abcdefghijklmnop" not in redacted
    assert "Host: lab.test" in redacted


def test_every_sensitive_header_is_redacted_in_free_text():
    for name in sorted(SENSITIVE_HEADERS):
        redacted = redact_text(f"{name}: SECRETVALUE123456")
        assert "SECRETVALUE123456" not in redacted, name


def test_bare_auth_scheme_in_text_is_redacted():
    redacted = redact_text("using Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 now")
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
    assert "Bearer" in redacted


def test_query_style_secrets_in_text_are_redacted():
    redacted = redact_text("POST /login?user=admin&password=hunter2 HTTP/1.1")
    assert "hunter2" not in redacted
    assert "user=admin" in redacted


def test_innocent_text_is_unchanged():
    message = "analysis complete: 12 assets, 0 findings"
    assert redact_text(message) == message


def test_empty_text_is_safe():
    assert redact_text("") == ""


def test_logging_filter_scrubs_records():
    stream = io.StringIO()
    logger = logging.getLogger("aurora.tests.redaction")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(RedactionFilter())
    logger.addHandler(handler)

    try:
        logger.info("Authorization: Bearer %s", "abcdefghijklmnop")
    finally:
        logger.removeHandler(handler)

    output = stream.getvalue()
    assert "abcdefghijklmnop" not in output
    assert REDACTED in output
