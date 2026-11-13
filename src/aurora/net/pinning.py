"""Connection pinning.

The hostname is resolved once (see :mod:`aurora.net.resolver`) and every
returned address is validated against scope (:mod:`aurora.net.addresses`).
The request is then addressed to the validated literal, so the HTTP stack
performs no further name resolution — there is no second lookup for an attacker
to influence.

Two things must survive that rewrite, and both are asserted in integration
tests against a local server rather than assumed:

* **HTTP ``Host``** — rebuilt from the logical URL, including a non-default
  port, and sent explicitly so it is never derived from the IP literal.
* **TLS SNI and certificate verification** — httpcore honours the
  ``sni_hostname`` request extension, so the handshake still presents and
  verifies the original host name. ``connect_tcp`` uses the literal.

The logical URL is kept in the result and in the redirect chain; the rewritten
URL is an implementation detail of the connection.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from aurora.net.errors import NetworkError
from aurora.scope.urls import NormalizedURL

__all__ = ["PinnedTarget", "build_pinned_target"]


@dataclass(frozen=True, slots=True)
class PinnedTarget:
    """The logical URL plus the concrete connection coordinates."""

    logical: NormalizedURL
    address: str
    connect_url: str
    host_header: str
    extensions: Mapping[str, str]


def build_pinned_target(url: NormalizedURL, address: str) -> PinnedTarget:
    """Combine a logical URL with the validated address to connect to."""

    try:
        literal = ipaddress.ip_address(address)
    except ValueError as exc:
        raise NetworkError(f"cannot pin {url.host} to {address!r}: not an IP literal") from exc

    host_part = f"[{literal.compressed}]" if literal.version == 6 else literal.compressed
    connect_url = f"{url.scheme}://{host_part}:{url.port}{url.path}"
    if url.query:
        connect_url += f"?{url.query}"

    extensions: dict[str, str] = {}
    if url.scheme == "https":
        # Preserve the original hostname for the handshake and for certificate
        # verification while connecting to the validated literal.
        extensions["sni_hostname"] = url.host

    return PinnedTarget(
        logical=url,
        address=str(literal),
        connect_url=connect_url,
        host_header=url.host_header,
        extensions=MappingProxyType(extensions),
    )
