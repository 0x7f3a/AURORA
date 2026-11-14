"""Pinned request construction: address in, hostname and SNI preserved."""

from __future__ import annotations

import pytest

from aurora.net.errors import NetworkError
from aurora.net.pinning import build_pinned_target
from aurora.scope.urls import normalize_url


def test_http_request_targets_the_validated_literal():
    target = build_pinned_target(normalize_url("http://lab.test/admin?x=1"), "93.184.216.34")
    assert target.connect_url == "http://93.184.216.34:80/admin?x=1"
    assert target.host_header == "lab.test"
    assert target.address == "93.184.216.34"
    assert dict(target.extensions) == {}


def test_host_header_keeps_a_non_default_port():
    target = build_pinned_target(normalize_url("http://lab.test:8080/x"), "127.0.0.1")
    assert target.connect_url == "http://127.0.0.1:8080/x"
    assert target.host_header == "lab.test:8080"


def test_default_port_is_omitted_from_the_host_header_but_kept_for_the_connection():
    target = build_pinned_target(normalize_url("https://lab.test/x"), "93.184.216.34")
    assert target.connect_url == "https://93.184.216.34:443/x"
    assert target.host_header == "lab.test"


def test_https_preserves_the_original_hostname_for_sni():
    target = build_pinned_target(normalize_url("https://lab.test/x"), "93.184.216.34")
    assert target.extensions["sni_hostname"] == "lab.test"


def test_ipv6_literal_is_bracketed_in_the_connect_url():
    target = build_pinned_target(normalize_url("http://lab.test/x"), "2001:db8::1")
    assert target.connect_url == "http://[2001:db8::1]:80/x"
    assert target.host_header == "lab.test"


def test_query_and_path_are_preserved():
    target = build_pinned_target(
        normalize_url("https://lab.test/a/b?q=1&r=2"), "93.184.216.34"
    )
    assert target.connect_url == "https://93.184.216.34:443/a/b?q=1&r=2"


def test_invalid_address_cannot_be_pinned():
    with pytest.raises(NetworkError):
        build_pinned_target(normalize_url("http://lab.test/"), "not-an-ip")


def test_pinned_target_keeps_the_logical_url():
    logical = normalize_url("https://lab.test/x")
    target = build_pinned_target(logical, "93.184.216.34")
    assert target.logical is logical
    assert target.logical.to_url() == "https://lab.test/x"
