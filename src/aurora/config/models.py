"""Configuration models.

Every bound in this module is enforced, not decorative. A configuration that
asks for zero timeouts, an unbounded response size, or negative concurrency is
rejected at load time so that later phases cannot silently run outside the
resource envelope the operator approved.

``extra="forbid"`` is deliberate: a typo in a limit name must be an error, not a
silently ignored safety setting.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aurora import DISPLAY_VERSION, OPERATOR
from aurora.scope.models import ScopeSettings

__all__ = ["AuroraConfig", "NetworkLimits", "RunLimits"]

_MAX_USER_AGENT = 256


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NetworkLimits(_Section):
    """Resource envelope for all HTTP activity.

    These values are enforced by the transport layer in Phase 4; they are
    defined here so that scope and limits are part of one validated document.
    """

    connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    read_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    total_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    max_response_bytes: int = Field(default=4 * 1024 * 1024, ge=1024, le=64 * 1024 * 1024)
    max_header_bytes: int = Field(default=64 * 1024, ge=1024, le=1024 * 1024)
    max_redirects: int = Field(default=5, ge=0, le=20)
    max_concurrency: int = Field(default=8, ge=1, le=64)
    requests_per_second: float = Field(default=4.0, gt=0, le=100)

    @field_validator("read_timeout_seconds")
    @classmethod
    def _read_timeout_must_exceed_connect(cls, value: float, info):  # noqa: ANN001
        connect = info.data.get("connect_timeout_seconds")
        if connect is not None and value < connect:
            raise ValueError("read_timeout_seconds must be >= connect_timeout_seconds")
        return value


class RunLimits(_Section):
    """Bounds on a single assessment run."""

    max_requests: int = Field(default=2000, ge=1, le=100_000)
    max_wall_seconds: float = Field(default=900.0, gt=0, le=86_400)


class AuroraConfig(BaseModel):
    """The workspace configuration file (``config.json``)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    operator: str = Field(default=OPERATOR, min_length=1, max_length=64)
    profile: Literal["safe"] = "safe"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    user_agent: str = Field(
        default=f"aurora/{DISPLAY_VERSION} (+https://github.com/0x7f3a/AURORA)",
        min_length=1,
        max_length=_MAX_USER_AGENT,
    )
    network: NetworkLimits = Field(default_factory=NetworkLimits)
    run: RunLimits = Field(default_factory=RunLimits)
    scope: ScopeSettings = Field(default_factory=ScopeSettings)

    @field_validator("operator")
    @classmethod
    def _clean_operator(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("operator must not be blank")
        if any(character < " " or character == "\x7f" for character in cleaned):
            raise ValueError("operator must not contain control characters")
        return cleaned

    @field_validator("user_agent")
    @classmethod
    def _clean_user_agent(cls, value: str) -> str:
        if any(character in value for character in "\r\n"):
            raise ValueError("user_agent must be a single line")
        return value.strip()

    def to_dict(self) -> dict[str, object]:
        """JSON-serialisable representation used for persistence."""

        return self.model_dump(mode="json")
