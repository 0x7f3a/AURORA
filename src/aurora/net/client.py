"""Bounded HTTP transport.

HTTPX owns HTTP/1.1 parsing, TLS and connection handling. AURORA owns the
policy around it:

1. canonicalise the URL (:mod:`aurora.scope.urls`);
2. evaluate scope **before** touching the network;
3. resolve once and validate every address against the address policy;
4. pin the request to the validated literal, preserving ``Host`` and SNI;
5. reserve budget, take a concurrency slot, wait for a rate token;
6. stream the body with a hard size cap;
7. on a redirect, resolve ``Location`` against the logical URL and repeat from
   step 2 for that hop — redirects are never followed implicitly.

Connection reuse is disabled (one connection per hop, ``max_keepalive_connections=0``)
because a pooled connection could outlive a scope or DNS decision. For an
assessment workload with a small request budget that cost is acceptable and
makes the boundary auditable. It is a deliberate trade, recorded in
``docs/ARCHITECTURE.md``.
"""

from __future__ import annotations

import asyncio
import ipaddress
import ssl
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping

import httpx

from aurora.config.models import NetworkLimits, RunLimits
from aurora.errors import UrlError, UsageError
from aurora.net.addresses import evaluate_address
from aurora.net.budget import RateLimiter, RequestBudget
from aurora.net.errors import (
    AddressNotAllowed,
    HeaderLimitExceeded,
    RequestTimedOut,
    ResponseTooLarge,
    ScopeViolation,
    TooManyRedirects,
    TransportError,
)
from aurora.net.pinning import build_pinned_target
from aurora.net.resolver import Resolver, SystemResolver
from aurora.scope.policy import ScopeDecision, ScopePolicy
from aurora.scope.urls import NormalizedURL, normalize_url

__all__ = ["AuroraClient", "FetchResult"]

_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
_ALLOWED_METHODS = frozenset({"GET", "HEAD"})


@dataclass(frozen=True, slots=True)
class FetchResult:
    """A completed, in-scope response."""

    requested_url: str
    final_url: str
    status_code: int
    headers: Mapping[str, str]
    raw_headers: tuple[tuple[str, str], ...]
    body: bytes
    redirect_chain: tuple[str, ...]
    address: str
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class _Hop:
    status_code: int
    headers: Mapping[str, str]
    raw_headers: tuple[tuple[str, str], ...]
    body: bytes
    location: str | None


class AuroraClient:
    """Scope-enforcing, resource-bounded HTTP client.

    An instance belongs to one event loop: it owns an ``asyncio.Semaphore`` and a
    rate-limiter lock, so it must not be shared across ``asyncio.run`` calls.
    """

    def __init__(
        self,
        *,
        policy: ScopePolicy,
        network_limits: NetworkLimits,
        run_limits: RunLimits,
        user_agent: str,
        resolver: Resolver | None = None,
        verify: bool | str | ssl.SSLContext = True,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._policy = policy
        self._limits = network_limits
        self._user_agent = user_agent
        self._resolver: Resolver = resolver if resolver is not None else SystemResolver()
        self._verify = verify
        self._clock = clock
        self._budget = RequestBudget(
            max_requests=run_limits.max_requests,
            max_wall_seconds=run_limits.max_wall_seconds,
            clock=clock,
        )
        self._limiter = RateLimiter(
            rate_per_second=network_limits.requests_per_second,
            clock=clock,
            sleep=sleep,
        )
        self._semaphore = asyncio.Semaphore(network_limits.max_concurrency)
        self._closed = False

    @property
    def requests_made(self) -> int:
        return self._budget.requests_made

    @property
    def elapsed_seconds(self) -> float:
        return self._budget.elapsed_seconds

    async def __aenter__(self) -> "AuroraClient":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001 - protocol
        await self.aclose()

    async def aclose(self) -> None:
        """Mark the client closed. Connections are per-request and already closed."""

        self._closed = True

    async def fetch(self, url: str, *, method: str = "GET") -> FetchResult:
        """Perform one bounded request, following only in-scope redirects."""

        if self._closed:
            raise UsageError("client is closed")
        verb = method.upper()
        if verb not in _ALLOWED_METHODS:
            raise UsageError(f"method {method!r} is not supported; use GET or HEAD")

        requested = normalize_url(url)

        try:
            async with asyncio.timeout(self._limits.total_timeout_seconds):
                return await self._follow_redirects(requested, verb)
        except TimeoutError as exc:
            raise RequestTimedOut(
                f"request to {requested.to_url()} exceeded "
                f"{self._limits.total_timeout_seconds:g}s total timeout"
            ) from exc

    async def _follow_redirects(self, requested: NormalizedURL, method: str) -> FetchResult:
        started = self._clock()
        current = requested
        chain: list[str] = []
        address = ""

        for hop_index in range(self._limits.max_redirects + 1):
            decision = self._policy.evaluate(current)
            if not decision.allowed:
                raise ScopeViolation(f"{current.to_url()} is out of scope: {decision.reason}")

            address = await self._validated_address(current, decision)
            chain.append(current.to_url())

            hop = await self._send(current, address, method)

            if hop.location is not None and hop.status_code in _REDIRECT_STATUS_CODES:
                if hop_index >= self._limits.max_redirects:
                    raise TooManyRedirects(
                        f"exceeded {self._limits.max_redirects} redirects while following "
                        f"{requested.to_url()}"
                    )
                try:
                    current = normalize_url(hop.location, base=current.to_url())
                except UrlError as exc:
                    raise ScopeViolation(
                        f"refusing redirect from {current.to_url()} to "
                        f"{hop.location!r}: {exc}"
                    ) from exc
                continue

            return FetchResult(
                requested_url=requested.to_url(),
                final_url=current.to_url(),
                status_code=hop.status_code,
                headers=hop.headers,
                raw_headers=hop.raw_headers,
                body=hop.body,
                redirect_chain=tuple(chain),
                address=address,
                elapsed_seconds=max(0.0, self._clock() - started),
            )

        raise TooManyRedirects(  # pragma: no cover - loop always returns or raises
            f"exceeded {self._limits.max_redirects} redirects"
        )

    async def _validated_address(self, url: NormalizedURL, decision: ScopeDecision) -> str:
        # An address literal needs no resolution; it still goes through the
        # address policy below, so loopback/RFC1918 rules still apply.
        try:
            literal = str(ipaddress.ip_address(url.host))
        except ValueError:
            literal = ""
        addresses = (literal,) if literal else await self._resolver.resolve(url.host, url.port)
        if not addresses:
            raise AddressNotAllowed(f"{url.host} resolved to no addresses")

        reasons: list[str] = []
        for candidate in addresses:
            verdict = evaluate_address(candidate, allow_private=decision.allow_private)
            if verdict.allowed:
                return candidate
            reasons.append(verdict.reason)

        raise AddressNotAllowed(
            f"{url.host} did not resolve to an authorised address: " + "; ".join(reasons)
        )

    async def _send(self, url: NormalizedURL, address: str, method: str) -> _Hop:
        target = build_pinned_target(url, address)

        self._budget.reserve()
        async with self._semaphore:
            await self._limiter.acquire()

            request = httpx.Request(
                method,
                target.connect_url,
                headers={
                    "Host": target.host_header,
                    "User-Agent": self._user_agent,
                    "Accept": "*/*",
                    "Connection": "close",
                },
                extensions=dict(target.extensions),
            )

            transport = self._build_transport()
            try:
                async with httpx.AsyncClient(
                    transport=transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=self._timeout(),
                ) as client:
                    try:
                        response = await client.send(request, stream=True)
                    except httpx.TimeoutException as exc:
                        raise RequestTimedOut(
                            f"{method} {url.to_url()} timed out ({type(exc).__name__})"
                        ) from exc
                    except httpx.HTTPError as exc:
                        raise TransportError(
                            f"{method} {url.to_url()} failed: {type(exc).__name__}: {exc}"
                        ) from exc

                    try:
                        return await self._consume(url, response)
                    finally:
                        await response.aclose()
            finally:
                await transport.aclose()

    async def _consume(self, url: NormalizedURL, response: httpx.Response) -> _Hop:
        raw_headers = tuple((name, value) for name, value in response.headers.items())
        header_bytes = sum(
            len(name.encode("latin-1", "replace")) + len(value.encode("latin-1", "replace")) + 4
            for name, value in raw_headers
        )
        if header_bytes > self._limits.max_header_bytes:
            raise HeaderLimitExceeded(
                f"response headers from {url.to_url()} exceeded "
                f"{self._limits.max_header_bytes} bytes"
            )

        headers = dict(raw_headers)
        location = response.headers.get("location")

        if location is not None and response.status_code in _REDIRECT_STATUS_CODES:
            # A redirect body is discarded; only the Location matters.
            return _Hop(
                status_code=response.status_code,
                headers=headers,
                raw_headers=raw_headers,
                body=b"",
                location=location,
            )

        body = bytearray()
        limit = self._limits.max_response_bytes
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > limit:
                raise ResponseTooLarge(
                    f"response body from {url.to_url()} exceeded {limit} bytes"
                )

        return _Hop(
            status_code=response.status_code,
            headers=headers,
            raw_headers=raw_headers,
            body=bytes(body),
            location=None,
        )

    def _ssl_verify(self) -> bool | ssl.SSLContext:
        # httpx deprecates a CA *path*; build the context here so callers can
        # still configure a CA file (and so the deprecation never fires).
        if isinstance(self._verify, str):
            return ssl.create_default_context(cafile=self._verify)
        return self._verify

    def _build_transport(self) -> httpx.AsyncHTTPTransport:
        return httpx.AsyncHTTPTransport(
            verify=self._ssl_verify(),
            trust_env=False,
            http1=True,
            http2=False,
            retries=0,
            limits=httpx.Limits(
                max_connections=1,
                max_keepalive_connections=0,
                keepalive_expiry=0.0,
            ),
        )

    def _timeout(self) -> httpx.Timeout:
        connect = self._limits.connect_timeout_seconds
        read = self._limits.read_timeout_seconds
        return httpx.Timeout(connect=connect, read=read, write=read, pool=connect)
