"""Transport-layer failures.

Every class maps to the network exit code so the CLI contract stays stable.
A refusal is always distinguishable from a transport failure: ``ScopeViolation``
and ``AddressNotAllowed`` mean *no request was sent*, while ``TransportError``
means the request was attempted and failed at the connection/HTTP layer.
"""

from __future__ import annotations

from aurora.errors import AuroraError
from aurora.exit_codes import ExitCode

__all__ = [
    "AddressNotAllowed",
    "BudgetExhausted",
    "HeaderLimitExceeded",
    "NetworkError",
    "RequestTimedOut",
    "ResolutionError",
    "ResponseTooLarge",
    "ScopeViolation",
    "TooManyRedirects",
    "TransportError",
]


class NetworkError(AuroraError):
    """Base class for transport failures and refusals."""

    exit_code = ExitCode.NETWORK


class ScopeViolation(NetworkError):
    """The URL (or a redirect target) is outside the authorised scope."""


class AddressNotAllowed(NetworkError):
    """The host resolves only to addresses the scope does not authorise."""


class ResolutionError(NetworkError):
    """The host could not be resolved."""


class ResponseTooLarge(NetworkError):
    """The response body exceeded ``max_response_bytes``."""


class HeaderLimitExceeded(NetworkError):
    """The response header block exceeded ``max_header_bytes``."""


class TooManyRedirects(NetworkError):
    """The redirect chain exceeded ``max_redirects``."""


class BudgetExhausted(NetworkError):
    """The request or wall-clock budget for the run is exhausted."""


class RequestTimedOut(NetworkError):
    """The whole request (including redirects) exceeded the total timeout."""


class TransportError(NetworkError):
    """The request was attempted and failed below the HTTP semantics layer."""
