"""Scope policy: exclusions win, nothing matching means denied."""

from __future__ import annotations

import pytest

from aurora.errors import UrlError
from aurora.scope.models import ScopeRule, ScopeSettings, host_matches
from aurora.scope.policy import ScopePolicy
from aurora.scope.urls import normalize_url


def _policy(*rules: ScopeRule) -> ScopePolicy:
    return ScopePolicy(rules)


def _allow(url: str, *rules: ScopeRule) -> bool:
    return _policy(*rules).evaluate(normalize_url(url)).allowed


def test_empty_policy_denies_everything():
    decision = _policy().evaluate(normalize_url("https://lab.test/"))
    assert decision.allowed is False
    assert "nothing is authorised" in decision.reason
    assert decision.rule is None


def test_include_rule_allows_matching_target():
    rule = ScopeRule(host="lab.test")
    decision = _policy(rule).evaluate(normalize_url("https://lab.test/app"))
    assert decision.allowed is True
    assert decision.rule is rule
    assert "include" in decision.reason


def test_other_host_is_denied():
    policy = _policy(ScopeRule(host="lab.test"))
    decision = policy.evaluate(normalize_url("https://other.test/"))
    assert decision.allowed is False
    assert "no include rule matches" in decision.reason


def test_scheme_restriction_is_enforced():
    rule = ScopeRule(host="lab.test", scheme="https")
    assert _allow("https://lab.test/", rule) is True
    assert _allow("http://lab.test/", rule) is False


def test_scheme_any_covers_both():
    rule = ScopeRule(host="lab.test", scheme="any")
    assert _allow("https://lab.test/", rule) is True
    assert _allow("http://lab.test/", rule) is True


def test_port_zero_means_any_port_but_explicit_port_is_exact():
    any_port = ScopeRule(host="lab.test", port=0)
    exact = ScopeRule(host="lab.test", port=8443)
    assert _allow("https://lab.test:9000/", any_port) is True
    assert _allow("https://lab.test:8443/", exact) is True
    assert _allow("https://lab.test:9000/", exact) is False


def test_path_prefix_limits_scope():
    rule = ScopeRule(host="lab.test", path_prefix="/app")
    assert _allow("https://lab.test/app/dashboard", rule) is True
    assert _allow("https://lab.test/app", rule) is True
    assert _allow("https://lab.test/application", rule) is False
    assert _allow("https://lab.test/", rule) is False


def test_exclusion_beats_include():
    policy = _policy(
        ScopeRule(host="lab.test"),
        ScopeRule(kind="exclude", host="lab.test", path_prefix="/logout"),
    )
    assert policy.evaluate(normalize_url("https://lab.test/dashboard")).allowed is True
    denied = policy.evaluate(normalize_url("https://lab.test/logout"))
    assert denied.allowed is False
    assert "exclusion" in denied.reason


def test_exclusion_rule_never_grants_access():
    policy = _policy(ScopeRule(kind="exclude", host="lab.test"))
    decision = policy.evaluate(normalize_url("https://lab.test/"))
    assert decision.allowed is False
    assert "exclusion" in decision.reason


def test_wildcard_matches_subdomains_but_not_apex():
    assert host_matches("*.example.test", "a.example.test") is True
    assert host_matches("*.example.test", "deep.a.example.test") is True
    assert host_matches("*.example.test", "example.test") is False
    assert host_matches("*.example.test", "notexample.test") is False


def test_wildcard_rule_is_evaluated_end_to_end():
    rule = ScopeRule(host="*.example.test")
    assert _allow("https://api.example.test/", rule) is True
    assert _allow("https://example.test/", rule) is False


def test_wildcard_only_allowed_as_leading_label():
    with pytest.raises(ValueError):
        ScopeRule(host="api.*.test")
    with pytest.raises(ValueError):
        ScopeRule(host="*")


def test_allow_private_is_carried_into_the_decision():
    private_allowed = _policy(ScopeRule(host="127.0.0.1", allow_private=True))
    private_denied = _policy(ScopeRule(host="127.0.0.1"))
    allowed = private_allowed.evaluate(normalize_url("http://127.0.0.1:8000/"))
    denied = private_denied.evaluate(normalize_url("http://127.0.0.1:8000/"))
    assert allowed.allowed is True and allowed.allow_private is True
    assert denied.allowed is True and denied.allow_private is False


def test_host_is_normalised_in_rules():
    rule = ScopeRule(host="LAB.Example.TEST.")
    assert rule.host == "lab.example.test"


def test_invalid_rule_hosts_are_rejected():
    for bad in ("", "   ", "lab test", "lab..test", "https://lab.test/"):
        with pytest.raises(ValueError):
            ScopeRule(host=bad)


def test_invalid_path_prefix_in_rule_is_rejected():
    with pytest.raises(ValueError):
        ScopeRule(host="lab.test", path_prefix="admin")
    with pytest.raises(ValueError) as excinfo:
        ScopeRule(host="lab.test", path_prefix="/admin/%2e%2e")
    assert "ambiguous" in str(excinfo.value)


def test_settings_parse_from_json_shape():
    settings = ScopeSettings.model_validate(
        {
            "targets": [
                {"scheme": "https", "host": "lab.test", "port": 443},
                {"kind": "exclude", "host": "lab.test", "path_prefix": "/admin"},
            ]
        }
    )
    policy = ScopePolicy.from_settings(settings)
    assert len(policy) == 2
    assert policy.include_count == 1
    assert policy.evaluate(normalize_url("https://lab.test/admin")).allowed is False
    assert policy.evaluate(normalize_url("https://lab.test/public")).allowed is True


def test_rule_describe_is_readable():
    rule = ScopeRule(scheme="https", host="lab.test", port=443, path_prefix="/app")
    assert rule.describe() == "include https://lab.test:443/app"
    assert ScopeRule(host="lab.test").describe() == "include any://lab.test:*/"


def test_default_rule_is_inclusive():
    assert ScopeRule(host="lab.test").kind == "include"
