"""Scope rule models.

A scope entry is deliberately explicit: scheme, host, port and path prefix are
all part of it, and ``allow_private`` is opt-in per entry so that reaching a
local lab never silently widens every other target. Wildcards are allowed only
as a leading ``*.`` label and never match the apex domain.

A target may also be written as a URL (``https://lab.test/app``): the URL is
parsed once, at load time, into the explicit fields above, so a rule never
holds a half-parsed string. Targets are therefore accepted in three forms —
a URL string, an object with ``url``, or the explicit object form — and all
three produce the same rule.

These models are also the configuration schema (``config.json`` → ``scope``),
so a typo in a rule fails at load time with the field name in the message.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal
from urllib.parse import urlsplit

from aurora.errors import UrlError
from aurora.scope.urls import (
    NormalizedURL,
    normalize_host,
    normalize_path_prefix,
    path_prefix_matches,
)
from aurora.validation import Field, Model, ValidationError

__all__ = ["ScopeRule", "ScopeSettings", "host_matches"]

_HOST_MAX = 253
_DEFAULT_PORTS = {"http": 80, "https": 443}


def host_matches(pattern: str, host: str) -> bool:
    """Whether *host* is covered by *pattern* (exact or ``*.`` subdomain).

    Both sides are canonicalised here as well as by the models, so a caller
    passing a rule host or a URL host straight from configuration still gets
    case-insensitive, trailing-dot-insensitive DNS comparison.
    """

    pattern_host = pattern.strip().rstrip(".").lower()
    candidate = host.strip().rstrip(".").lower()
    if pattern_host.startswith("*."):
        suffix = pattern_host[2:]
        return candidate.endswith("." + suffix) and candidate != suffix
    return pattern_host == candidate


def _target_url_fields(raw: str) -> dict[str, object]:
    """Translate a target URL into the explicit fields a rule stores.

    The URL supplies one origin and the path prefix beneath it: scheme and port
    come from the URL (the scheme default when the port is omitted), so
    ``https://lab.test/app`` means ``https://lab.test:443/app`` and nothing
    else. A query string or fragment is refused rather than dropped, because a
    rule covers scheme, host, port and path only and silently discarding one
    would claim coverage the rule does not have.
    """

    text = raw.strip()
    if not text:
        raise ValueError("target URL is empty")
    if any(character.isspace() or character == "\\" for character in text):
        raise ValueError(f"target URL {raw!r} contains whitespace or a backslash")
    authority = text.split("://", 1)[-1].split("/", 1)[0]
    if "@" in authority:
        raise ValueError("target URLs with embedded credentials are not allowed")

    try:
        parts = urlsplit(text)
    except ValueError as exc:
        raise ValueError(f"cannot parse target URL {raw!r}: {exc}") from exc

    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        shown = parts.scheme or "<none>"
        raise ValueError(f"target URL must start with http:// or https://, got {shown!r}")
    if parts.username is not None or parts.password is not None:
        raise ValueError("target URLs with embedded credentials are not allowed")
    if not parts.hostname:
        raise ValueError(f"target URL {raw!r} has no host")
    if parts.query:
        raise ValueError(
            "target URL must not contain a query string; a scope rule covers "
            "scheme, host, port and path"
        )
    if parts.fragment:
        raise ValueError("target URL must not contain a fragment")

    try:
        explicit_port = parts.port
    except ValueError as exc:
        raise ValueError(f"target URL {raw!r} has an invalid port: {exc}") from exc
    port = _DEFAULT_PORTS[scheme] if explicit_port is None else explicit_port
    if not 1 <= port <= 65535:
        raise ValueError(f"target URL {raw!r} has a port outside 1-65535")

    hostname = parts.hostname
    try:
        if "*" in hostname:
            suffix = hostname[2:] if hostname.startswith("*.") else ""
            if not suffix:
                raise ValueError(
                    "a wildcard target must be a leading '*.' label, "
                    "e.g. https://*.example.test/"
                )
            host = "*." + normalize_host(suffix)
        else:
            host = normalize_host(hostname)
    except UrlError as exc:
        raise ValueError(str(exc)) from exc

    return {
        "scheme": scheme,
        "host": host,
        "port": port,
        "path_prefix": normalize_path_prefix(parts.path or "/"),
    }


def _clean_host(value: str) -> str:
    candidate = value.strip().lower()
    if not candidate:
        raise ValueError("host must not be empty")
    if candidate.startswith("*."):
        suffix = candidate[2:]
        if not suffix:
            raise ValueError("wildcard host must include a domain, e.g. '*.example.test'")
        return "*." + normalize_host(suffix)
    if "*" in candidate:
        raise ValueError("wildcards are only supported as a leading '*.'")
    return normalize_host(candidate)


class ScopeRule(Model):
    """One authorised (or explicitly excluded) target."""

    _fields = {
        "kind": Field("literal", choices=("include", "exclude"), default="include"),
        "scheme": Field("literal", choices=("http", "https", "any"), default="any"),
        "host": Field(
            "str",
            min_length=1,
            max_length=_HOST_MAX,
            coerce=_clean_host,
        ),
        "port": Field("int", default=0, ge=0, le=65535),
        "path_prefix": Field("str", default="/", coerce=normalize_path_prefix),
        "allow_private": Field("bool", default=False),
    }

    @classmethod
    def _before(cls, data: Any) -> Any:
        """Accept a URL string or a ``{"url": ...}`` object as a target."""

        if isinstance(data, str):
            return cls._expand(data)
        if isinstance(data, Mapping) and "url" in data:
            if "host" in data:
                raise ValidationError([((), "give either 'url' or 'host', not both")])
            extra = dict(data)
            raw_url = extra.pop("url")
            kind = extra.pop("kind", "include")
            allow_private = extra.pop("allow_private", False)
            if not isinstance(raw_url, str):
                raise ValidationError([(("url",), "must be a string")])
            expanded = cls._expand(raw_url, kind=kind, allow_private=allow_private)
            # Anything left over is unknown; the field list must still reject it.
            expanded.update(extra)
            return expanded
        return data

    @classmethod
    def _expand(cls, raw: str, **options: Any) -> dict[str, Any]:
        try:
            return cls.from_url(raw, **options).model_dump()
        except ValidationError:
            raise
        except ValueError as exc:
            raise ValidationError([((), str(exc))]) from exc

    @classmethod
    def from_url(
        cls,
        raw: str,
        *,
        kind: Literal["include", "exclude"] = "include",
        allow_private: bool = False,
    ) -> "ScopeRule":
        """Build a rule from a URL target such as ``https://lab.test/app``.

        A leading ``!`` marks an exclusion, so ``!https://lab.test/logout`` and
        ``from_url("https://lab.test/logout", kind="exclude")`` agree.
        """

        text = raw.strip()
        if text.startswith("!"):
            kind = "exclude"
            text = text[1:].strip()
        rule = cls(kind=kind, allow_private=allow_private, **_target_url_fields(text))
        assert isinstance(rule, cls)
        return rule

    def matches(self, url: NormalizedURL) -> bool:
        if self.scheme != "any" and self.scheme != url.scheme:
            return False
        if self.port and self.port != url.port:
            return False
        if not host_matches(self.host, url.host):
            return False
        return path_prefix_matches(self.path_prefix, url.path)

    def describe(self) -> str:
        port = "*" if self.port == 0 else str(self.port)
        # An IPv6 literal needs its brackets back, or the description reads as
        # an unbracketed address followed by a port.
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{self.kind} {self.scheme}://{host}:{port}{self.path_prefix}"


class ScopeSettings(Model):
    """The ``scope`` section of the workspace configuration."""

    _fields = {
        "targets": Field(
            "tuple",
            item=Field("model", model=ScopeRule),
            default=(),
        )
    }
