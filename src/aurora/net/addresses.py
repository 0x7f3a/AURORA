"""Address classification for scope enforcement.

Hostname scope is not enough: a name inside scope can resolve to an address
outside the authorised network. Every candidate address is therefore classified
before a connection is made.

Policy, deliberately narrow:

* link-local (including the cloud metadata address ``169.254.169.254``),
  multicast, unspecified, reserved and unparseable addresses are **never**
  contacted, even when a rule allows private networks;
* loopback, RFC1918, IPv6 ULA and shared address space (``100.64.0.0/10``) are
  reachable only when the matching scope rule sets ``allow_private`` — that flag
  is how an authorised local lab is expressed without global weakening;
* anything else must be a globally routable address.

IPv4-mapped IPv6 addresses are classified by their embedded IPv4 address, so
``::ffff:127.0.0.1`` cannot slip past the loopback rule.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "ALWAYS_DENIED",
    "LOCAL_ONLY",
    "AddressClass",
    "AddressDecision",
    "classify_address",
    "evaluate_address",
]

_SHARED_V4 = ipaddress.ip_network("100.64.0.0/10")


class AddressClass(StrEnum):
    LOOPBACK = "loopback"
    PRIVATE = "private"
    SHARED = "shared"
    GLOBAL = "global"
    LINK_LOCAL = "link-local"
    MULTICAST = "multicast"
    UNSPECIFIED = "unspecified"
    RESERVED = "reserved"
    INVALID = "invalid"


#: Refused regardless of ``allow_private``.
ALWAYS_DENIED: frozenset[AddressClass] = frozenset(
    {
        AddressClass.LINK_LOCAL,
        AddressClass.MULTICAST,
        AddressClass.UNSPECIFIED,
        AddressClass.RESERVED,
        AddressClass.INVALID,
    }
)

#: Reachable only when the matching scope rule allows private networks.
LOCAL_ONLY: frozenset[AddressClass] = frozenset(
    {AddressClass.LOOPBACK, AddressClass.PRIVATE, AddressClass.SHARED}
)


def classify_address(raw: str) -> AddressClass:
    """Classify an address literal. Membership tests drive the policy."""

    try:
        address = ipaddress.ip_address(raw.strip())
    except ValueError:
        return AddressClass.INVALID

    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped

    # Order matters: ``is_global`` is true for multicast, and ``is_private`` is
    # true for both loopback and link-local, so the specific checks come first.
    if address.is_multicast:
        return AddressClass.MULTICAST
    if address.is_unspecified:
        return AddressClass.UNSPECIFIED
    if address.is_link_local:
        return AddressClass.LINK_LOCAL
    if address.is_loopback:
        return AddressClass.LOOPBACK
    if isinstance(address, ipaddress.IPv4Address) and address in _SHARED_V4:
        return AddressClass.SHARED
    # ``is_reserved`` before ``is_private``: the limited broadcast address and
    # 240.0.0.0/4 report both, and neither may ever be contacted.
    if address.is_reserved:
        return AddressClass.RESERVED
    if address.is_private:
        return AddressClass.PRIVATE
    if address.is_global:
        return AddressClass.GLOBAL
    return AddressClass.RESERVED


@dataclass(frozen=True, slots=True)
class AddressDecision:
    allowed: bool
    address_class: AddressClass
    reason: str


def evaluate_address(raw: str, *, allow_private: bool) -> AddressDecision:
    """Decide whether *raw* may be connected to for this scope decision."""

    address_class = classify_address(raw)
    if address_class in ALWAYS_DENIED:
        return AddressDecision(
            allowed=False,
            address_class=address_class,
            reason=f"{raw} is {address_class.value} and is never contacted",
        )
    if address_class in LOCAL_ONLY and not allow_private:
        return AddressDecision(
            allowed=False,
            address_class=address_class,
            reason=(
                f"{raw} is {address_class.value}; the matching scope rule does not "
                "allow private networks"
            ),
        )
    return AddressDecision(
        allowed=True,
        address_class=address_class,
        reason=f"{raw} is {address_class.value}",
    )
