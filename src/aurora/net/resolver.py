"""Name resolution.

Resolution is separated from connection establishment on purpose: AURORA
resolves once, validates every returned address against the scope, and then
connects to the validated literal (see :mod:`aurora.net.pinning`). That single
resolution is what removes the usual time-of-check/time-of-use window.

The resolver is an injectable protocol so integration tests can script address
answers — including a mid-request change — without touching system DNS.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Protocol, runtime_checkable

from aurora.net.errors import ResolutionError

__all__ = ["Resolver", "SystemResolver"]


@runtime_checkable
class Resolver(Protocol):
    """Async name resolver."""

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        """Return address literals for *host*, most-preferred first."""
        ...


class SystemResolver:
    """Resolve through the operating system's resolver.

    ``getaddrinfo`` runs in a worker thread because it is a blocking call with
    no asyncio equivalent; ``asyncio.to_thread`` keeps the event loop free
    without introducing a thread pool AURORA has to own.
    """

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        literal = _as_literal(host)
        if literal is not None:
            return (literal,)

        try:
            infos = await asyncio.to_thread(
                socket.getaddrinfo,
                host,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise ResolutionError(f"cannot resolve {host}: {exc}") from exc
        except OSError as exc:
            raise ResolutionError(f"cannot resolve {host}: {exc}") from exc

        addresses: list[str] = []
        for info in infos:
            candidate = info[4][0]
            if candidate not in addresses:
                addresses.append(candidate)

        if not addresses:
            raise ResolutionError(f"{host} resolved to no addresses")
        return tuple(addresses)


def _as_literal(host: str) -> str | None:
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None
