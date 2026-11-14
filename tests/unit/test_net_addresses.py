"""Address policy: what may be connected to, and under which condition."""

from __future__ import annotations

import pytest

from aurora.net.addresses import (
    ALWAYS_DENIED,
    LOCAL_ONLY,
    AddressClass,
    classify_address,
    evaluate_address,
)


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("127.0.0.1", AddressClass.LOOPBACK),
        ("127.10.20.30", AddressClass.LOOPBACK),
        ("::1", AddressClass.LOOPBACK),
        ("10.1.2.3", AddressClass.PRIVATE),
        ("192.168.1.10", AddressClass.PRIVATE),
        ("172.16.5.5", AddressClass.PRIVATE),
        ("fd00::1", AddressClass.PRIVATE),
        ("100.64.0.1", AddressClass.SHARED),
        ("169.254.169.254", AddressClass.LINK_LOCAL),
        ("fe80::1", AddressClass.LINK_LOCAL),
        ("0.0.0.0", AddressClass.UNSPECIFIED),
        ("::", AddressClass.UNSPECIFIED),
        ("224.0.0.1", AddressClass.MULTICAST),
        ("255.255.255.255", AddressClass.RESERVED),
        ("93.184.216.34", AddressClass.GLOBAL),
        ("8.8.8.8", AddressClass.GLOBAL),
        ("2606:4700::1111", AddressClass.GLOBAL),
        ("::ffff:127.0.0.1", AddressClass.LOOPBACK),
        ("::ffff:10.0.0.1", AddressClass.PRIVATE),
        ("not-an-address", AddressClass.INVALID),
        ("", AddressClass.INVALID),
    ],
)
def test_classification(address, expected):
    assert classify_address(address) is expected


def test_denied_and_local_sets_are_disjoint():
    assert ALWAYS_DENIED.isdisjoint(LOCAL_ONLY)


def test_public_address_is_allowed_without_private_permission():
    decision = evaluate_address("93.184.216.34", allow_private=False)
    assert decision.allowed is True
    assert decision.address_class is AddressClass.GLOBAL


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "100.64.0.1", "fd00::1"])
def test_local_addresses_require_explicit_permission(address):
    denied = evaluate_address(address, allow_private=False)
    allowed = evaluate_address(address, allow_private=True)
    assert denied.allowed is False
    assert "does not allow private networks" in denied.reason
    assert allowed.allowed is True


@pytest.mark.parametrize(
    "address",
    ["169.254.169.254", "fe80::1", "224.0.0.1", "0.0.0.0", "::", "255.255.255.255", "bogus"],
)
def test_always_denied_addresses_ignore_the_private_flag(address):
    for allow_private in (True, False):
        decision = evaluate_address(address, allow_private=allow_private)
        assert decision.allowed is False, address


def test_metadata_address_is_never_reachable_even_for_a_lab():
    decision = evaluate_address("169.254.169.254", allow_private=True)
    assert decision.allowed is False
    assert "never contacted" in decision.reason


def test_ipv4_mapped_loopback_cannot_bypass_the_rule():
    decision = evaluate_address("::ffff:127.0.0.1", allow_private=False)
    assert decision.allowed is False
    assert decision.address_class is AddressClass.LOOPBACK
