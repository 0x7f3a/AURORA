"""Scope policy evaluation.

Rules are evaluated in a fixed, documented order:

1. **Exclusions first.** Any matching ``exclude`` rule denies the URL, even if
   an include rule would also match. Exclusion always wins; there is no
   "more specific include beats exclude" heuristic to reason about.
2. **Includes second.** The first matching include rule allows the URL and
   carries its ``allow_private`` decision into address validation.
3. **Nothing matching means denied.** An empty policy authorises nothing.

A decision carries the rule that produced it and a human-readable reason, so
reports and CLI output can explain *why* a URL was refused instead of just
failing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from aurora.scope.models import ScopeRule, ScopeSettings
from aurora.scope.urls import NormalizedURL

__all__ = ["ScopeDecision", "ScopePolicy"]


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    allowed: bool
    reason: str
    rule: ScopeRule | None = None
    allow_private: bool = False


class ScopePolicy:
    """An immutable set of scope rules."""

    def __init__(self, rules: Sequence[ScopeRule] = ()) -> None:
        self._rules: tuple[ScopeRule, ...] = tuple(rules)
        self._excludes: tuple[ScopeRule, ...] = tuple(
            rule for rule in self._rules if rule.kind == "exclude"
        )
        self._includes: tuple[ScopeRule, ...] = tuple(
            rule for rule in self._rules if rule.kind == "include"
        )

    @classmethod
    def from_settings(cls, settings: ScopeSettings) -> "ScopePolicy":
        return cls(settings.targets)

    @property
    def rules(self) -> tuple[ScopeRule, ...]:
        return self._rules

    @property
    def include_count(self) -> int:
        return len(self._includes)

    def __len__(self) -> int:
        return len(self._rules)

    def evaluate(self, url: NormalizedURL) -> ScopeDecision:
        for rule in self._excludes:
            if rule.matches(url):
                return ScopeDecision(
                    allowed=False,
                    reason=f"matches exclusion rule ({rule.describe()})",
                    rule=rule,
                )

        for rule in self._includes:
            if rule.matches(url):
                return ScopeDecision(
                    allowed=True,
                    reason=f"matches include rule ({rule.describe()})",
                    rule=rule,
                    allow_private=rule.allow_private,
                )

        if not self._includes:
            return ScopeDecision(
                allowed=False,
                reason="no include rules are configured, so nothing is authorised",
            )
        return ScopeDecision(
            allowed=False,
            reason="no include rule matches this scheme, host, port and path",
        )
