"""Resource limits: body size, header size, budgets, timeouts, cancellation."""

from __future__ import annotations

import asyncio
import time

import pytest

from aurora.config.models import NetworkLimits, RunLimits
from aurora.net.errors import (
    BudgetExhausted,
    HeaderLimitExceeded,
    RequestTimedOut,
    ResponseTooLarge,
    TransportError,
)
from fixtures.resolver import make_client, policy_for


def _run(coro):
    return asyncio.run(coro)


def _network(**overrides) -> NetworkLimits:
    values = {"requests_per_second": 100.0, "max_concurrency": 4}
    values.update(overrides)
    return NetworkLimits(**values)


def test_response_body_limit_is_enforced(server):
    client = make_client(
        policy_for(server),
        network=_network(max_response_bytes=1024),
    )

    with pytest.raises(ResponseTooLarge) as excinfo:
        _run(client.fetch(server.url("/big?size=20000")))

    assert "1024" in str(excinfo.value)


def test_response_body_below_the_limit_is_returned(server):
    client = make_client(policy_for(server), network=_network(max_response_bytes=2048))
    result = _run(client.fetch(server.url("/big?size=1024")))
    assert result.status_code == 200
    assert len(result.body) == 1024


def test_header_limit_is_enforced(server):
    client = make_client(policy_for(server), network=_network(max_header_bytes=1024))

    with pytest.raises(HeaderLimitExceeded):
        _run(client.fetch(server.url("/huge-header")))


def test_request_budget_stops_further_requests(server):
    client = make_client(
        policy_for(server),
        run=RunLimits(max_requests=1, max_wall_seconds=60),
    )

    assert _run(client.fetch(server.url("/ok"))).status_code == 200
    with pytest.raises(BudgetExhausted):
        _run(client.fetch(server.url("/ok")))

    assert len(server.state.requests) == 1
    assert client.requests_made == 1


def test_wall_clock_budget_stops_further_requests(server):
    async def scenario():
        client = make_client(
            policy_for(server),
            run=RunLimits(max_requests=10, max_wall_seconds=0.05),
        )
        await client.fetch(server.url("/ok"))
        await asyncio.sleep(0.1)
        with pytest.raises(BudgetExhausted):
            await client.fetch(server.url("/ok"))

    _run(scenario())
    assert len(server.state.requests) == 1


def test_total_timeout_bounds_a_slow_response(server):
    client = make_client(
        policy_for(server),
        network=_network(
            total_timeout_seconds=0.2,
            connect_timeout_seconds=1.0,
            read_timeout_seconds=2.0,
        ),
    )

    started = time.monotonic()
    with pytest.raises(RequestTimedOut):
        _run(client.fetch(server.url("/slow?delay=0.8")))
    assert time.monotonic() - started < 0.7


def test_cancellation_interrupts_a_slow_response(server):
    async def scenario() -> float:
        client = make_client(
            policy_for(server),
            network=_network(
                total_timeout_seconds=10.0,
                connect_timeout_seconds=2.0,
                read_timeout_seconds=5.0,
            ),
        )
        task = asyncio.create_task(client.fetch(server.url("/slow?delay=0.8")))
        await asyncio.sleep(0.15)
        assert not task.done()

        task.cancel()
        started = time.monotonic()
        with pytest.raises(asyncio.CancelledError):
            await task
        return time.monotonic() - started

    assert _run(scenario()) < 0.4


def test_concurrency_limit_is_respected(server):
    async def scenario():
        client = make_client(
            policy_for(server),
            network=_network(max_concurrency=2, requests_per_second=100),
        )
        results = await asyncio.gather(
            *(client.fetch(server.url("/slow?delay=0.15")) for _ in range(6))
        )
        return results

    results = _run(scenario())

    assert all(result.status_code == 200 for result in results)
    assert len(server.state.requests) == 6
    assert server.state.max_active <= 2


def test_rate_limit_paces_sequential_requests(server):
    async def scenario() -> float:
        client = make_client(
            policy_for(server),
            network=_network(requests_per_second=4.0),
        )
        started = time.monotonic()
        for _ in range(3):
            await client.fetch(server.url("/ok"))
        return time.monotonic() - started

    elapsed = _run(scenario())
    assert elapsed >= 0.4
    assert len(server.state.requests) == 3


def test_repeated_headers_are_preserved_individually(server):
    client = make_client(policy_for(server))
    result = _run(client.fetch(server.url("/dup-headers")))

    cookies = [value for name, value in result.raw_headers if name.lower() == "set-cookie"]
    assert cookies == ["a=1; Path=/", "b=2; Path=/"]


def test_truncated_body_is_a_transport_error(server):
    client = make_client(policy_for(server))

    with pytest.raises(TransportError) as excinfo:
        _run(client.fetch(server.url("/truncated-body")))

    assert "reading the body" in str(excinfo.value)


def test_read_timeout_while_streaming_the_body_is_a_timeout(server):
    client = make_client(
        policy_for(server),
        network=_network(
            connect_timeout_seconds=0.2,
            read_timeout_seconds=0.3,
            total_timeout_seconds=5.0,
        ),
    )

    with pytest.raises(RequestTimedOut):
        _run(client.fetch(server.url("/stall-body?delay=1.5")))


def test_status_codes_are_returned_without_body_caps_interfering(server):
    client = make_client(policy_for(server))
    assert _run(client.fetch(server.url("/status?code=404"))).status_code == 404
    assert _run(client.fetch(server.url("/status?code=503"))).status_code == 503
