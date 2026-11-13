"""Scope enforcement over real sockets.

Each test observes the fixture server, so "no request was sent" is a statement
about the server's request log, not about a client-side flag.
"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import quote

import pytest

from aurora.config.models import NetworkLimits
from aurora.errors import UsageError
from aurora.net.errors import AddressNotAllowed, ScopeViolation, TooManyRedirects
from aurora.scope.models import ScopeRule
from aurora.scope.policy import ScopePolicy
from fixtures.resolver import ScriptedResolver, make_client, policy_for


def _run(coro):
    return asyncio.run(coro)


def _redirect(path: str, target: str) -> str:
    return f"{path}?to={quote(target, safe='')}"


def _header(result, name: str) -> str | None:
    for key, value in result.raw_headers:
        if key.lower() == name.lower():
            return value
    return None


def test_in_scope_request_reaches_the_server(server):
    client = make_client(policy_for(server))
    result = _run(client.fetch(server.url("/ok")))

    assert result.status_code == 200
    assert result.body == b"ok"
    assert result.address == "127.0.0.1"
    assert result.final_url == server.url("/ok")
    assert result.redirect_chain == (server.url("/ok"),)
    assert _header(result, "content-type").startswith("text/plain")

    record = server.state.requests[0]
    assert record.method == "GET"
    assert record.host == f"127.0.0.1:{server.port}"
    assert record.peer[0] == "127.0.0.1"
    assert record.user_agent == "aurora-test/0.0"


def test_out_of_scope_target_is_never_contacted(server):
    client = make_client(ScopePolicy([ScopeRule(host="lab.test")]))

    with pytest.raises(ScopeViolation) as excinfo:
        _run(client.fetch(server.url("/ok")))

    assert "out of scope" in str(excinfo.value)
    assert server.state.requests == []


def test_private_address_requires_explicit_permission(server):
    client = make_client(policy_for(server, allow_private=False))

    with pytest.raises(AddressNotAllowed) as excinfo:
        _run(client.fetch(server.url("/ok")))

    assert "does not allow private networks" in str(excinfo.value)
    assert server.state.requests == []


def test_excluded_path_is_refused_before_the_request(server):
    policy = policy_for(
        server,
        excludes=[
            ScopeRule(
                kind="exclude",
                scheme="http",
                host=server.host,
                port=server.port,
                path_prefix="/admin",
            )
        ],
    )
    client = make_client(policy)

    assert _run(client.fetch(server.url("/ok"))).status_code == 200
    with pytest.raises(ScopeViolation):
        _run(client.fetch(server.url("/admin/secret")))

    assert server.state.paths == ["/ok"]


def test_redirect_inside_scope_is_followed(server):
    target = server.url("/ok")
    client = make_client(policy_for(server))

    result = _run(client.fetch(server.url(_redirect("/redirect", target))))

    assert result.status_code == 200
    assert result.body == b"ok"
    assert result.final_url == target
    assert len(result.redirect_chain) == 2
    assert result.redirect_chain[-1] == target
    assert len(server.state.requests) == 2


def test_redirect_out_of_scope_never_contacts_the_other_server(server, other_server):
    client = make_client(policy_for(server))

    with pytest.raises(ScopeViolation) as excinfo:
        _run(client.fetch(server.url(_redirect("/redirect", other_server.url("/ok")))))

    assert "out of scope" in str(excinfo.value)
    assert len(server.state.requests) == 1
    assert other_server.state.requests == []


def test_redirect_with_credentials_is_refused(server):
    client = make_client(policy_for(server))
    target = f"http://user:pass@127.0.0.1:{server.port}/ok"

    with pytest.raises(ScopeViolation) as excinfo:
        _run(client.fetch(server.url(_redirect("/redirect", target))))

    assert "credentials" in str(excinfo.value)
    assert len(server.state.requests) == 1


def test_redirect_to_unsupported_scheme_is_refused(server):
    client = make_client(policy_for(server))

    with pytest.raises(ScopeViolation):
        _run(client.fetch(server.url(_redirect("/redirect", "file:///etc/passwd"))))

    assert len(server.state.requests) == 1


def test_redirect_loop_stops_at_the_redirect_budget(server):
    client = make_client(
        policy_for(server),
        network=NetworkLimits(max_redirects=2, requests_per_second=100),
    )

    with pytest.raises(TooManyRedirects):
        _run(client.fetch(server.url("/redirect-loop")))

    assert len(server.state.requests) == 3


def test_zero_redirect_budget_refuses_the_first_redirect(server):
    client = make_client(
        policy_for(server),
        network=NetworkLimits(max_redirects=0, requests_per_second=100),
    )

    with pytest.raises(TooManyRedirects):
        _run(client.fetch(server.url(_redirect("/redirect", server.url("/ok")))))

    assert len(server.state.requests) == 1


def test_redirect_target_in_host_scope_but_without_private_permission(server, other_server):
    # Both rules match by host/port, but only the first permits loopback
    # addresses. The redirect is refused at the address layer.
    policy = ScopePolicy(
        [
            ScopeRule(
                scheme="http",
                host="127.0.0.1",
                port=server.port,
                allow_private=True,
            ),
            ScopeRule(
                scheme="http",
                host="127.0.0.1",
                port=other_server.port,
                allow_private=False,
            ),
        ]
    )
    client = make_client(policy)

    with pytest.raises(AddressNotAllowed):
        _run(client.fetch(server.url(_redirect("/redirect", other_server.url("/ok")))))

    assert other_server.state.requests == []


def test_wildcard_host_scope_with_pinned_resolution(server):
    resolver = ScriptedResolver(["127.0.0.1"])
    policy = ScopePolicy(
        [
            ScopeRule(
                scheme="http",
                host="*.lab.test",
                port=server.port,
                allow_private=True,
            )
        ]
    )
    client = make_client(policy, resolver=resolver)

    result = _run(client.fetch(f"http://api.lab.test:{server.port}/echo"))

    payload = json.loads(result.body)
    assert payload["host"] == f"api.lab.test:{server.port}"
    assert resolver.calls == [("api.lab.test", server.port)]
    assert server.state.requests[0].peer[0] == "127.0.0.1"


def test_wildcard_does_not_cover_the_apex(server):
    resolver = ScriptedResolver(["127.0.0.1"])
    policy = ScopePolicy(
        [ScopeRule(scheme="http", host="*.lab.test", port=server.port, allow_private=True)]
    )
    client = make_client(policy, resolver=resolver)

    with pytest.raises(ScopeViolation):
        _run(client.fetch(f"http://lab.test:{server.port}/ok"))

    assert server.state.requests == []
    assert resolver.calls == []


def test_head_request_returns_no_body(server):
    client = make_client(policy_for(server))
    result = _run(client.fetch(server.url("/ok"), method="HEAD"))
    assert result.status_code == 200
    assert result.body == b""


def test_unsupported_method_is_a_usage_error(server):
    client = make_client(policy_for(server))
    with pytest.raises(UsageError):
        _run(client.fetch(server.url("/ok"), method="POST"))
    assert server.state.requests == []


def test_closed_client_refuses_work(server):
    async def scenario():
        client = make_client(policy_for(server))
        await client.aclose()
        with pytest.raises(UsageError):
            await client.fetch(server.url("/ok"))

    _run(scenario())
    assert server.state.requests == []
