"""Connection-boundary experiment.

These tests answer the questions the design must not assume:

* does the TCP connection really go to the validated address?
* is the original hostname still used for the HTTP ``Host`` header?
* is the original hostname still used for TLS SNI and certificate verification?
* does a resolution answer that changes *after* validation affect the connection?

Every assertion is made from the server side of a real socket.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from aurora.net.errors import TransportError
from aurora.scope.models import ScopeRule
from aurora.scope.policy import ScopePolicy
from fixtures.http_server import FixtureServer
from fixtures.resolver import ScriptedResolver, make_client


def _run(coro):
    return asyncio.run(coro)


def _policy(scheme: str, host: str, port: int) -> ScopePolicy:
    return ScopePolicy([ScopeRule(scheme=scheme, host=host, port=port, allow_private=True)])


def test_http_connects_to_the_validated_address_with_the_original_host(server):
    resolver = ScriptedResolver(["127.0.0.1"])
    client = make_client(_policy("http", "pin.test", server.port), resolver=resolver)

    result = _run(client.fetch(f"http://pin.test:{server.port}/echo"))

    payload = json.loads(result.body)
    assert payload["host"] == f"pin.test:{server.port}"
    assert payload["sni"] is None

    record = server.state.requests[0]
    assert record.peer[0] == "127.0.0.1"
    assert record.host == f"pin.test:{server.port}"

    assert result.address == "127.0.0.1"
    assert resolver.calls == [("pin.test", server.port)]


def test_resolution_happens_exactly_once_per_hop(server):
    resolver = ScriptedResolver(["127.0.0.1", "127.0.0.1"])
    client = make_client(_policy("http", "pin.test", server.port), resolver=resolver)

    result = _run(client.fetch(f"http://pin.test:{server.port}/ok"))

    assert result.status_code == 200
    assert len(resolver.calls) == 1


def test_a_rebinding_answer_cannot_redirect_the_connection(server):
    """Validate 127.0.0.1, then let the resolver offer a different address."""

    try:
        attacker = FixtureServer(host="127.0.0.2", port=server.port).start()
    except OSError:
        pytest.skip("127.0.0.2 is not bindable on this platform")

    try:
        # First (and only) resolution is the validated address. Any further
        # resolution would be offered the attacker's address and would land on
        # a different server listening on the same port.
        resolver = ScriptedResolver(["127.0.0.1", "127.0.0.2"])
        client = make_client(_policy("http", "pin.test", server.port), resolver=resolver)

        result = _run(client.fetch(f"http://pin.test:{server.port}/echo"))

        payload = json.loads(result.body)
        assert payload["host"] == f"pin.test:{server.port}"
        assert attacker.state.requests == []
        assert len(resolver.calls) == 1
        assert len(server.state.requests) == 1
    finally:
        attacker.stop()


def test_tls_sni_and_host_preserved_while_connecting_to_the_literal(tls_server):
    resolver = ScriptedResolver(["127.0.0.1"])
    client = make_client(
        _policy("https", "pin.test", tls_server.port),
        resolver=resolver,
        verify=tls_server.certificate,
    )

    result = _run(client.fetch(f"https://pin.test:{tls_server.port}/echo"))

    payload = json.loads(result.body)
    assert payload["host"] == f"pin.test:{tls_server.port}"
    assert payload["sni"] == "pin.test"

    assert tls_server.state.sni_names == ["pin.test"]
    assert tls_server.state.requests[0].peer[0] == "127.0.0.1"


def test_certificate_verification_uses_the_original_hostname(tls_server):
    """The fixture certificate is valid for ``pin.test`` only.

    If pinning dropped SNI, verification would be attempted against
    ``127.0.0.1`` and would fail; success therefore demonstrates that the
    hostname, not the literal, is verified.
    """

    client = make_client(
        _policy("https", "pin.test", tls_server.port),
        resolver=ScriptedResolver(["127.0.0.1"]),
        verify=tls_server.certificate,
    )
    assert _run(client.fetch(f"https://pin.test:{tls_server.port}/ok")).status_code == 200

    # Without the fixture CA, the same request must fail verification, proving
    # that verification is active rather than bypassed.
    untrusted = make_client(
        _policy("https", "pin.test", tls_server.port),
        resolver=ScriptedResolver(["127.0.0.1"]),
        verify=True,
    )
    with pytest.raises(TransportError):
        _run(untrusted.fetch(f"https://pin.test:{tls_server.port}/ok"))


def test_ip_literal_skips_resolution_but_still_checks_the_address(server):
    resolver = ScriptedResolver([])  # any call would raise ResolutionError
    client = make_client(_policy("http", "127.0.0.1", server.port), resolver=resolver)

    result = _run(client.fetch(server.url("/ok")))

    assert result.status_code == 200
    assert resolver.calls == []


def test_private_permission_is_required_for_hostnames_too(server):
    resolver = ScriptedResolver(["127.0.0.1"])
    policy = ScopePolicy(
        [ScopeRule(scheme="http", host="pin.test", port=server.port, allow_private=False)]
    )
    client = make_client(policy, resolver=resolver)

    from aurora.net.errors import AddressNotAllowed

    with pytest.raises(AddressNotAllowed):
        _run(client.fetch(f"http://pin.test:{server.port}/ok"))

    assert server.state.requests == []
