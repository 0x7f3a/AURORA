"""Budgets and pacing, tested with an injected clock instead of real time."""

from __future__ import annotations

import asyncio

import pytest

from aurora.net.budget import RateLimiter, RequestBudget
from aurora.net.errors import BudgetExhausted


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_budget_counts_reserved_requests():
    budget = RequestBudget(max_requests=3, max_wall_seconds=60)
    for _ in range(3):
        budget.reserve()
    assert budget.requests_made == 3
    assert budget.remaining_requests == 0
    with pytest.raises(BudgetExhausted) as excinfo:
        budget.reserve()
    assert "request budget" in str(excinfo.value)


def test_budget_exhaustion_does_not_increment_the_counter():
    budget = RequestBudget(max_requests=1, max_wall_seconds=60)
    budget.reserve()
    with pytest.raises(BudgetExhausted):
        budget.reserve()
    assert budget.requests_made == 1


def test_wall_clock_budget_is_enforced():
    clock = FakeClock()
    budget = RequestBudget(max_requests=10, max_wall_seconds=1.0, clock=clock)
    budget.reserve()
    clock.now = 0.5
    budget.reserve()
    clock.now = 1.5
    with pytest.raises(BudgetExhausted) as excinfo:
        budget.reserve()
    assert "wall-clock" in str(excinfo.value)
    assert budget.requests_made == 2


def test_elapsed_seconds_uses_the_injected_clock():
    clock = FakeClock()
    budget = RequestBudget(max_requests=2, max_wall_seconds=10, clock=clock)
    assert budget.elapsed_seconds == 0.0
    budget.reserve()
    clock.now = 2.5
    assert budget.elapsed_seconds == 2.5


def test_invalid_budget_configuration_is_rejected():
    with pytest.raises(ValueError):
        RequestBudget(max_requests=0, max_wall_seconds=10)
    with pytest.raises(ValueError):
        RequestBudget(max_requests=1, max_wall_seconds=0)


def test_first_request_is_not_delayed():
    clock = FakeClock()
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds

    limiter = RateLimiter(rate_per_second=4.0, clock=clock, sleep=sleep)

    async def scenario() -> None:
        await limiter.acquire()

    asyncio.run(scenario())
    assert sleeps == []


def test_subsequent_requests_are_paced():
    clock = FakeClock()
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds

    limiter = RateLimiter(rate_per_second=4.0, clock=clock, sleep=sleep)

    async def scenario() -> None:
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()

    asyncio.run(scenario())
    assert sleeps == pytest.approx([0.25, 0.25])


def test_tokens_refill_over_time():
    clock = FakeClock()
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds

    limiter = RateLimiter(rate_per_second=2.0, clock=clock, sleep=sleep)

    async def scenario() -> None:
        await limiter.acquire()
        clock.now += 1.0  # a second of work elsewhere refills the bucket
        await limiter.acquire()

    asyncio.run(scenario())
    assert sleeps == []


def test_concurrent_acquirers_are_serialised():
    clock = FakeClock()
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds

    limiter = RateLimiter(rate_per_second=10.0, clock=clock, sleep=sleep)

    async def scenario() -> None:
        await asyncio.gather(*(limiter.acquire() for _ in range(3)))

    asyncio.run(scenario())
    # Three requests at 10/s starting with one token: 0.1s + 0.1s of pacing.
    assert len(sleeps) == 2
    assert clock.now == pytest.approx(0.2)


def test_invalid_rate_is_rejected():
    with pytest.raises(ValueError):
        RateLimiter(rate_per_second=0)
