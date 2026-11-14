"""Scope: URL canonicalisation and authorisation decisions."""

from __future__ import annotations

from aurora.scope.models import ScopeRule, ScopeSettings, host_matches
from aurora.scope.policy import ScopeDecision, ScopePolicy
from aurora.scope.urls import (
    NormalizedURL,
    normalize_path_prefix,
    normalize_url,
    path_prefix_matches,
)

__all__ = [
    "NormalizedURL",
    "ScopeDecision",
    "ScopePolicy",
    "ScopeRule",
    "ScopeSettings",
    "host_matches",
    "normalize_path_prefix",
    "normalize_url",
    "path_prefix_matches",
]
