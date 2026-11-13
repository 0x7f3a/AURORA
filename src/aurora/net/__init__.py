"""Bounded, scope-enforcing HTTP transport built on HTTPX."""

from __future__ import annotations

from aurora.net.addresses import (
    AddressClass,
    AddressDecision,
    classify_address,
    evaluate_address,
)
from aurora.net.budget import RateLimiter, RequestBudget
from aurora.net.client import AuroraClient, FetchResult
from aurora.net.errors import (
    AddressNotAllowed,
    BudgetExhausted,
    HeaderLimitExceeded,
    NetworkError,
    RequestTimedOut,
    ResolutionError,
    ResponseTooLarge,
    ScopeViolation,
    TooManyRedirects,
    TransportError,
)
from aurora.net.pinning import PinnedTarget, build_pinned_target
from aurora.net.resolver import Resolver, SystemResolver

__all__ = [
    "AddressClass",
    "AddressDecision",
    "AddressNotAllowed",
    "AuroraClient",
    "BudgetExhausted",
    "FetchResult",
    "HeaderLimitExceeded",
    "NetworkError",
    "PinnedTarget",
    "RateLimiter",
    "RequestBudget",
    "RequestTimedOut",
    "ResolutionError",
    "Resolver",
    "ResponseTooLarge",
    "ScopeViolation",
    "SystemResolver",
    "TooManyRedirects",
    "TransportError",
    "build_pinned_target",
    "classify_address",
    "evaluate_address",
]
