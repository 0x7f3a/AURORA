"""Resolver double and client builder for integration tests.

The resolver is the only injected component in the transport path. Everything
beneath it — TCP, TLS, HTTP/1.1, redirects, body streaming — is real, which is
what makes the pinning tests meaningful rather than mock assertions.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from aurora.config.models import NetworkLimits, RunLimits
from aurora.net.client import AuroraClient
from aurora.net.errors import ResolutionError
from aurora.scope.models import ScopeRule
from aurora.scope.policy import ScopePolicy

__all__ = ["ScriptedResolver", "make_client", "policy_for"]


class ScriptedResolver:
    """Return scripted answers in order, remembering every call.

    The final answer repeats, so a client that resolves only once (`calls`)
    can still be compared against one that re-resolves. An empty script raises,
    which makes it a usable assertion that resolution never happened.
    """

    def __init__(self, answers: Iterable[str | Sequence[str]] = ()) -> None:
        self._answers: list[str | Sequence[str]] = list(answers)
        self.calls: list[tuple[str, int]] = []

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        self.calls.append((host, port))
        if not self._answers:
            raise ResolutionError(f"no scripted answer for {host}")
        answer = self._answers.pop(0) if len(self._answers) > 1 else self._answers[0]
        return (answer,) if isinstance(answer, str) else tuple(answer)


def policy_for(
    server,
    *,
    path_prefix: str = "/",
    allow_private: bool = True,
    scheme: str | None = None,
    excludes: Sequence[ScopeRule] = (),
) -> ScopePolicy:
    """A single-include policy matching one fixture server."""

    rule = ScopeRule(
        scheme=scheme or ("https" if server.tls else "http"),
        host=server.host,
        port=server.port,
        path_prefix=path_prefix,
        allow_private=allow_private,
    )
    return ScopePolicy([rule, *excludes])


def make_client(
    policy: ScopePolicy,
    *,
    resolver=None,
    network: NetworkLimits | None = None,
    run: RunLimits | None = None,
    verify: bool | str = True,
    user_agent: str = "aurora-test/0.0",
) -> AuroraClient:
    return AuroraClient(
        policy=policy,
        network_limits=network or NetworkLimits(requests_per_second=50.0),
        run_limits=run or RunLimits(),
        user_agent=user_agent,
        resolver=resolver,
        verify=verify,
    )
