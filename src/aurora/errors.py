"""AURORA error hierarchy.

Every recoverable failure is represented by a subclass of
:class:`AuroraError`. Each subclass carries the exit code the CLI must return,
so error handling stays in one place instead of being scattered through the
command implementations.
"""

from __future__ import annotations

from aurora.exit_codes import ExitCode

__all__ = [
    "AuroraError",
    "ConfigError",
    "PlatformError",
    "StorageError",
    "UrlError",
    "UsageError",
]


class AuroraError(Exception):
    """Base class for all expected AURORA failures."""

    exit_code: ExitCode = ExitCode.ERROR

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        if self.hint:
            return f"{self.message} (hint: {self.hint})"
        return self.message


class UsageError(AuroraError):
    """The operator asked for something the tool cannot do as written."""

    exit_code = ExitCode.USAGE


class ConfigError(AuroraError):
    """Configuration is missing, unreadable, or fails validation."""

    exit_code = ExitCode.CONFIG


class StorageError(AuroraError):
    """The assessment database cannot be opened, migrated, or queried."""

    exit_code = ExitCode.STORAGE


class PlatformError(AuroraError):
    """The current platform is unsupported for the requested operation."""

    exit_code = ExitCode.PLATFORM


class UrlError(AuroraError, ValueError):
    """A URL is malformed, unparseable, or uses a disallowed form.

    Also a :class:`ValueError` so that Pydantic field validators report it as a
    normal validation failure rather than letting it escape configuration load.
    """

    exit_code = ExitCode.NETWORK
