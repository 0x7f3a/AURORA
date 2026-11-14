"""Request budgets and pacing.

Two independent limits protect the target and the run:

* :class:`RequestBudget` caps the number of requests and the wall-clock time a
  run may spend. It counts an *attempt*, reserved before the connection is
  opened, so a failing target cannot silently consume more than the operator
  authorised.
* :class:`RateLimiter` is a token bucket with a burst of one, serialised by a
  lock so concurrent workers cannot spend the same token twice. Holding the lock
  while sleeping is intentional: it turns the limiter into a queue, which is
  exactly the pacing guarantee we want.

Both take injected ``clock``/``sleep`` callables so their behaviour is tested
deterministically instead of by measuring wall time.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

from aurora.net.errors import BudgetExhausted

__all__ = ["RateLimiter", "RequestBudget"]


class RequestBudget:
    """Per-run request and wall-clock accounting."""

    def __init__(
        self,
        *,
        max_requests: int,
        max_wall_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        if max_wall_seconds <= 0:
            raise ValueError("max_wall_seconds must be positive")
        self._max_requests = int(max_requests)
        self._max_wall_seconds = float(max_wall_seconds)
        self._clock = clock
        self._requests = 0
        self._started: float | None = None

    @property
    def requests_made(self) -> int:
        return self._requests

    @property
    def remaining_requests(self) -> int:
        return max(0, self._max_requests - self._requests)

    @property
    def elapsed_seconds(self) -> float:
        if self._started is None:
            return 0.0
        return max(0.0, self._clock() - self._started)

    def reserve(self) -> None:
        """Reserve one request, or raise if a budget is exhausted."""

        now = self._clock()
        if self._started is None:
            self._started = now
        if self._requests >= self._max_requests:
            raise BudgetExhausted(
                f"request budget exhausted ({self._max_requests} requests)"
            )
        if now - self._started > self._max_wall_seconds:
            raise BudgetExhausted(
                f"wall-clock budget exhausted ({self._max_wall_seconds:g}s)"
            )
        self._requests += 1


class RateLimiter:
    """Token bucket with a burst of one and FIFO-style serialisation."""

    def __init__(
        self,
        *,
        rate_per_second: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        self._rate = float(rate_per_second)
        self._clock = clock
        self._sleep = sleep
        self._tokens = 1.0
        self._last = clock()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = self._clock()
            elapsed = now - self._last
            if elapsed > 0:
                self._tokens = min(1.0, self._tokens + elapsed * self._rate)
            self._last = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            await self._sleep((1.0 - self._tokens) / self._rate)
            self._tokens = 0.0
            self._last = self._clock()
