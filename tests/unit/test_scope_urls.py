"""URL canonicalisation: the input to every scope decision."""

from __future__ import annotations

import pytest

from aurora.errors import UrlError
from aurora.scope.models import ScopeRule, host_matches
from aurora.scope.policy import ScopePolicy
from aurora.scope.urls import normalize_host, normalize_path_prefix, normalize_url, path_prefix_matches


def test_scheme_and_host_are_lower_cased():
    url = normalize_url("HTTPS://Lab.Example.TEST/Path")
    assert url.scheme == "https"
    assert url.host == "lab.example.test"
    assert url.path == "/Path"


def test_default_port_is_made_explicit_but_hidden_from_host_header():
    url = normalize_url("https://lab.test/x")
    assert url.port == 443
    assert url.host_header == "lab.test"
    assert url.origin == "https://lab.test:443"


def test_explicit_default_port_is_collapsed():
    url = normalize_url("http://lab.test:80/x")
    assert url.port == 80
    assert url.to_url() == "http://lab.test/x"


def test_non_default_port_is_kept():
    url = normalize_url("http://lab.test:8080/x")
    assert url.port == 8080
    assert url.host_header == "lab.test:8080"


def test_empty_path_becomes_root():
    assert normalize_url("https://lab.test").path == "/"


def test_dot_segments_are_resolved():
    url = normalize_url("https://lab.test/admin/../public/./index.html")
    assert url.path == "/public/index.html"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://lab.test//a/..", "//"),
        ("http://lab.test/a//.", "/a//"),
        ("http://lab.test/../a", "/a"),
        ("http://lab.test/a/../../b", "/b"),
    ],
)
def test_dot_segment_removal_keeps_empty_segments_as_rfc_3986_says(raw, expected):
    assert normalize_url(raw).path == expected


def test_encoded_unreserved_characters_are_decoded():
    assert normalize_url("http://lab.test/%61dmin").path == "/admin"
    assert normalize_url("http://lab.test/~%75ser").path == "/~user"


def test_encoded_unreserved_prefix_matches_the_decoded_form():
    assert normalize_path_prefix("/%61dmin") == "/admin"


def test_exclusion_cannot_be_evaded_with_encoded_unreserved_characters():
    policy = ScopePolicy(
        [
            ScopeRule(scheme="http", host="lab.test", allow_private=True),
            ScopeRule(kind="exclude", scheme="http", host="lab.test", path_prefix="/admin"),
        ]
    )
    assert policy.evaluate(normalize_url("http://lab.test/public")).allowed
    assert not policy.evaluate(normalize_url("http://lab.test/%61dmin/users")).allowed


def test_host_matching_is_case_and_trailing_dot_insensitive():
    assert host_matches("LAB.test.", "lab.test")
    assert host_matches("*.LAB.test", "api.lab.test")
    assert not host_matches("*.lab.test", "lab.test")
    assert not host_matches("*.lab.test", "badexa.test")


def test_encoded_dot_segment_is_refused():
    with pytest.raises(UrlError):
        normalize_url("https://lab.test/admin/%2e%2e/public")


def test_encoded_slash_is_refused():
    with pytest.raises(UrlError):
        normalize_url("https://lab.test/admin%2f..%2fpublic")


def test_embedded_credentials_are_refused():
    with pytest.raises(UrlError):
        normalize_url("https://operator:secret@lab.test/")


def test_backslash_is_refused():
    with pytest.raises(UrlError):
        normalize_url("https://lab.test\\@evil.test/")


def test_control_characters_are_refused():
    with pytest.raises(UrlError):
        normalize_url("https://lab.test/\r\nX-Injected: 1")


def test_whitespace_inside_url_is_refused():
    with pytest.raises(UrlError):
        normalize_url("https://lab.test/a b")


@pytest.mark.parametrize("raw", ["ftp://lab.test/", "file:///etc/passwd", "javascript:alert(1)", "//lab.test/"])
def test_non_http_schemes_are_refused(raw):
    with pytest.raises(UrlError):
        normalize_url(raw)


def test_fragment_is_dropped_and_query_preserved():
    url = normalize_url("https://lab.test/search?q=a%20b#section")
    assert url.query == "q=a%20b"
    assert url.to_url() == "https://lab.test/search?q=a%20b"


def test_relative_location_resolution():
    url = normalize_url("../other?x=1", base="https://lab.test/a/b/c")
    assert url.to_url() == "https://lab.test/a/other?x=1"


def test_scheme_relative_location_resolution():
    url = normalize_url("//lab.test:8080/x", base="https://lab.test/a")
    assert url.to_url() == "https://lab.test:8080/x"


@pytest.mark.parametrize(
    "ambiguous",
    [
        "http://127.000.000.001/",
        "http://127.1/",
        "http://2130706433/",
        "http://0x7f.0.0.1/",
    ],
)
def test_non_canonical_numeric_hosts_are_refused(ambiguous):
    # These resolve differently across platforms and are a classic scope bypass.
    with pytest.raises(UrlError):
        normalize_url(ambiguous)


def test_ipv4_literal_is_canonicalised():
    assert normalize_url("http://127.0.0.1:8080/").host == "127.0.0.1"


def test_ipv6_literal_gets_brackets_in_host_header():
    url = normalize_url("http://[::1]:8080/x")
    assert url.host == "::1"
    assert url.host_header == "[::1]:8080"
    assert url.to_url() == "http://[::1]:8080/x"


def test_zone_identifier_is_refused():
    with pytest.raises(UrlError):
        normalize_url("http://[fe80::1%25eth0]/")


def test_idna_host_is_encoded():
    assert normalize_url("https://bücher.example/").host == "xn--bcher-kva.example"


def test_trailing_dot_host_is_collapsed():
    assert normalize_url("https://lab.test./x").host == "lab.test"


def test_wildcard_is_not_a_url_host():
    with pytest.raises(UrlError):
        normalize_host("*.lab.test")


def test_path_prefix_normalisation():
    assert normalize_path_prefix("") == "/"
    assert normalize_path_prefix("/admin/") == "/admin/"
    assert normalize_path_prefix("/admin/../api") == "/api"


@pytest.mark.parametrize("raw", ["admin", "/admin/%2e%2e/", "/a b", "/a\\b"])
def test_invalid_path_prefix_is_refused(raw):
    with pytest.raises(UrlError):
        normalize_path_prefix(raw)


@pytest.mark.parametrize(
    ("prefix", "path", "expected"),
    [
        ("/", "/anything", True),
        ("/admin", "/admin", True),
        ("/admin", "/admin/users", True),
        ("/admin/", "/admin/users", True),
        ("/admin", "/administrator", False),
        ("/admin", "/public/admin", False),
        ("/api/v1", "/api/v2", False),
    ],
)
def test_path_prefix_matching_respects_segment_boundaries(prefix, path, expected):
    assert path_prefix_matches(prefix, path) is expected
