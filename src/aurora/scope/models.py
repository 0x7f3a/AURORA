"""Scope rule models.

A scope entry is deliberately explicit: scheme, host, port and path prefix are
all part of it, and ``allow_private`` is opt-in per entry so that reaching a
local lab never silently widens every other target. Wildcards are allowed only
as a leading ``*.`` label and never match the apex domain.

These models are also the configuration schema (``config.json`` → ``scope``),
so a typo in a rule fails at load time with the field name in the message.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aurora.scope.urls import (
    NormalizedURL,
    normalize_host,
    normalize_path_prefix,
    path_prefix_matches,
)

__all__ = ["ScopeRule", "ScopeSettings", "host_matches"]

_HOST_MAX = 253


def host_matches(pattern: str, host: str) -> bool:
    """Whether *host* is covered by *pattern* (exact or ``*.`` subdomain)."""

    if pattern.startswith("*."):
        suffix = pattern[2:]
        return host.endswith("." + suffix) and host != suffix
    return pattern == host


class ScopeRule(BaseModel):
    """One authorised (or explicitly excluded) target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["include", "exclude"] = "include"
    scheme: Literal["http", "https", "any"] = "any"
    host: str = Field(min_length=1, max_length=_HOST_MAX)
    port: int = Field(default=0, ge=0, le=65535, description="0 means any port")
    path_prefix: str = "/"
    allow_private: bool = Field(
        default=False,
        description="permit loopback/RFC1918/ULA addresses for this entry only",
    )

    @field_validator("host")
    @classmethod
    def _clean_host(cls, value: str) -> str:
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

    @field_validator("path_prefix")
    @classmethod
    def _clean_path_prefix(cls, value: str) -> str:
        return normalize_path_prefix(value)

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
        return f"{self.kind} {self.scheme}://{self.host}:{port}{self.path_prefix}"


class ScopeSettings(BaseModel):
    """The ``scope`` section of the workspace configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    targets: tuple[ScopeRule, ...] = ()
