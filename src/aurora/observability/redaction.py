"""Redaction of credentials before they reach logs, evidence or reports.

The rule is conservative: a value that is likely to be a credential is replaced
whether or not the surrounding context proves it is one. Over-redacting a log
line is a cosmetic problem; leaking a session cookie into a report is a breach.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit

__all__ = [
    "REDACTED",
    "SENSITIVE_HEADERS",
    "RedactionFilter",
    "redact_headers",
    "redact_text",
    "redact_url",
]

REDACTED = "<redacted>"

SENSITIVE_HEADERS: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "x-amz-security-token",
        "x-csrf-token",
        "api-key",
    }
)

_SENSITIVE_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "id_token",
        "key",
        "password",
        "passwd",
        "pwd",
        "refresh_token",
        "secret",
        "session",
        "sessionid",
        "sig",
        "signature",
        "token",
    }
)

_HEADER_LINE = re.compile(
    r"(?im)^([ \t]*(?:authorization|proxy-authorization|cookie|set-cookie|"
    r"x-api-key|x-auth-token|x-csrf-token|api-key)[ \t]*:[ \t]*)[^\r\n]+"
)

_AUTH_SCHEME = re.compile(r"(?i)\b(Bearer|Basic|Token)[ \t]+[A-Za-z0-9\-._~+/]{8,}=*")

_QUERY_SECRET = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|access_token|refresh_token|"
    r"id_token|api[_-]?key|apikey|session(?:id)?|signature|sig)=([^&\s\"'<>]+)"
)


def redact_headers(
    headers: Mapping[str, str] | Iterable[tuple[str, str]],
) -> dict[str, str]:
    """Return a copy of *headers* with sensitive values replaced."""

    items = headers.items() if isinstance(headers, Mapping) else headers
    result: dict[str, str] = {}
    for name, value in items:
        if name.strip().lower() in SENSITIVE_HEADERS:
            result[name] = REDACTED
        else:
            result[name] = value
    return result


def redact_url(url: str) -> str:
    """Remove userinfo and sensitive query values from *url*."""

    try:
        parts = urlsplit(url)
    except ValueError:
        return redact_text(url)

    netloc = parts.netloc
    if "@" in netloc:
        _, _, host = netloc.rpartition("@")
        netloc = f"{REDACTED}@{host}"

    query = parts.query
    if query:
        segments: list[str] = []
        for segment in query.split("&"):
            if not segment:
                continue
            key, separator, value = segment.partition("=")
            if value and key.strip().lower() in _SENSITIVE_QUERY_KEYS:
                segments.append(f"{key}{separator}{REDACTED}")
            else:
                segments.append(segment)
        query = "&".join(segments)

    rebuilt = ""
    if parts.scheme:
        rebuilt += f"{parts.scheme}://"
    rebuilt += netloc + parts.path
    if query:
        rebuilt += f"?{query}"
    if parts.fragment:
        rebuilt += f"#{parts.fragment}"
    return rebuilt


def redact_text(text: str) -> str:
    """Replace credential-looking substrings inside free-form text."""

    if not text:
        return text
    redacted = _HEADER_LINE.sub(lambda match: f"{match.group(1)}{REDACTED}", text)
    redacted = _AUTH_SCHEME.sub(lambda match: f"{match.group(1)} {REDACTED}", redacted)
    redacted = _QUERY_SECRET.sub(lambda match: f"{match.group(1)}={REDACTED}", redacted)
    return redacted


def redact_value(value: Any) -> Any:
    """Redact strings inside the common containers used by log arguments."""

    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {key: redact_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact_value(item) for item in value)
    return value


class RedactionFilter(logging.Filter):
    """Logging filter that scrubs credential material from messages."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - stdlib API
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - malformed format arguments
            return True
        redacted = redact_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True
