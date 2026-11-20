"""Configuration models.

Every bound in this module is enforced, not decorative. A configuration that
asks for zero timeouts, an unbounded response size, or negative concurrency is
rejected at load time so that later phases cannot silently run outside the
resource envelope the operator approved.

Unknown keys are rejected: a typo in a limit name must be an error, not a
silently ignored safety setting.

The models are built on :mod:`aurora.validation`, so reading and writing a
configuration needs nothing outside the standard library.
"""

from __future__ import annotations

from typing import Any

from aurora import DISPLAY_VERSION, OPERATOR
from aurora.scope.models import ScopeSettings
from aurora.validation import Field, Model

__all__ = ["AuroraConfig", "NetworkLimits", "RunLimits"]

_MAX_USER_AGENT = 256


def _clean_operator(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("operator must not be blank")
    if any(character < " " or character == "\x7f" for character in cleaned):
        raise ValueError("operator must not contain control characters")
    return cleaned


def _clean_user_agent(value: str) -> str:
    if any(character in value for character in "\r\n"):
        raise ValueError("user_agent must be a single line")
    return value.strip()


class NetworkLimits(Model):
    """Resource envelope for all HTTP activity.

    These values are enforced by the transport layer in Phase 4; they are
    defined here so that scope and limits are part of one validated document.
    """

    _fields = {
        "connect_timeout_seconds": Field("float", default=5.0, gt=0, le=60),
        "read_timeout_seconds": Field("float", default=15.0, gt=0, le=120),
        "total_timeout_seconds": Field("float", default=30.0, gt=0, le=600),
        "max_response_bytes": Field("int", default=4 * 1024 * 1024, ge=1024, le=64 * 1024 * 1024),
        "max_header_bytes": Field("int", default=64 * 1024, ge=1024, le=1024 * 1024),
        "max_redirects": Field("int", default=5, ge=0, le=20),
        "max_concurrency": Field("int", default=8, ge=1, le=64),
        "requests_per_second": Field("float", default=4.0, gt=0, le=100),
    }

    @classmethod
    def _after(
        cls,
        values: dict[str, Any],
        location: tuple[Any, ...],
        problems: list[tuple[tuple[Any, ...], str]],
    ) -> None:
        read = values.get("read_timeout_seconds")
        connect = values.get("connect_timeout_seconds")
        if isinstance(read, float) and isinstance(connect, float) and read < connect:
            problems.append(
                (
                    location + ("read_timeout_seconds",),
                    "must be at least connect_timeout_seconds",
                )
            )


class RunLimits(Model):
    """Bounds on a single assessment run."""

    _fields = {
        "max_requests": Field("int", default=2000, ge=1, le=100_000),
        "max_wall_seconds": Field("float", default=900.0, gt=0, le=86_400),
    }


class AuroraConfig(Model):
    """The workspace configuration file (``config.json``)."""

    _fields = {
        "schema_version": Field("literal", choices=(1,), default=1),
        "operator": Field(
            "str",
            default=OPERATOR,
            min_length=1,
            max_length=64,
            coerce=_clean_operator,
        ),
        "profile": Field("literal", choices=("safe",), default="safe"),
        "log_level": Field(
            "literal",
            choices=("DEBUG", "INFO", "WARNING", "ERROR"),
            default="INFO",
        ),
        "user_agent": Field(
            "str",
            default=f"aurora/{DISPLAY_VERSION} (+https://github.com/0x7f3a/AURORA)",
            min_length=1,
            max_length=_MAX_USER_AGENT,
            coerce=_clean_user_agent,
        ),
        "network": Field("model", model=NetworkLimits, factory=NetworkLimits),
        "run": Field("model", model=RunLimits, factory=RunLimits),
        "scope": Field("model", model=ScopeSettings, factory=ScopeSettings),
    }

    def to_dict(self) -> dict[str, object]:
        """JSON-serialisable representation used for persistence."""

        return self.model_dump(mode="json")
