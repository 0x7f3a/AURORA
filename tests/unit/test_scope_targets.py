"""URL targets: entering a URL produces an explicit scope rule.

The operator writes the address of the application (``https://lab.test/app``)
and the URL is parsed once into scheme, host, port and path prefix. These tests
pin that translation, including the forms that must be refused.
"""

from __future__ import annotations

import json

import pytest

from aurora.config.loader import default_config, load_config, write_config
from aurora.config.models import AuroraConfig
from aurora.scope.models import ScopeRule, ScopeSettings
from aurora.scope.policy import ScopePolicy
from aurora.scope.urls import normalize_url


def test_url_supplies_every_field():
    rule = ScopeRule.from_url("https://lab.test/app")
    assert (rule.kind, rule.scheme, rule.host, rule.port, rule.path_prefix) == (
        "include",
        "https",
        "lab.test",
        443,
        "/app",
    )


def test_omitted_port_uses_the_scheme_default():
    assert ScopeRule.from_url("http://lab.test/").port == 80
    assert ScopeRule.from_url("https://lab.test/").port == 443


def test_explicit_port_is_kept():
    rule = ScopeRule.from_url("http://127.0.0.1:8080/")
    assert (rule.host, rule.port) == ("127.0.0.1", 8080)


def test_bang_prefix_marks_an_exclusion():
    rule = ScopeRule.from_url("!https://lab.test/logout")
    assert rule.kind == "exclude"
    assert rule.path_prefix == "/logout"


def test_path_is_normalised_like_a_request_url():
    assert ScopeRule.from_url("https://lab.test/a/../admin").path_prefix == "/admin"
    assert ScopeRule.from_url("https://lab.test/%61dmin").path_prefix == "/admin"
    assert ScopeRule.from_url("https://lab.test").path_prefix == "/"


def test_wildcard_host_is_accepted_as_a_leading_label():
    rule = ScopeRule.from_url("https://*.example.test/")
    assert rule.host == "*.example.test"
    policy = ScopePolicy([rule])
    assert policy.evaluate(normalize_url("https://api.example.test/")).allowed is True
    assert policy.evaluate(normalize_url("https://example.test/")).allowed is False


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "lab.test",
        "//lab.test/",
        "ftp://lab.test/",
        "https://",
        "https://lab.test/?q=1",
        "https://lab.test/#section",
        "https://user:pw@lab.test/",
        "https://lab.test:0/",
        "https://lab.test:70000/",
        "https://api.*.test/",
        "https://*/",
        "https://lab test/",
    ],
)
def test_invalid_target_urls_are_refused(bad):
    with pytest.raises(ValueError):
        ScopeRule.from_url(bad)


def test_string_targets_load_from_configuration():
    settings = ScopeSettings.model_validate(
        {"targets": ["https://lab.test/", "!https://lab.test/admin"]}
    )
    assert [rule.kind for rule in settings.targets] == ["include", "exclude"]
    assert [rule.port for rule in settings.targets] == [443, 443]

    policy = ScopePolicy.from_settings(settings)
    assert policy.evaluate(normalize_url("https://lab.test/public")).allowed is True
    assert policy.evaluate(normalize_url("https://lab.test/admin")).allowed is False


def test_object_form_with_url_and_allow_private():
    settings = ScopeSettings.model_validate(
        {"targets": [{"url": "http://127.0.0.1:8080/", "allow_private": True}]}
    )
    rule = settings.targets[0]
    assert rule.allow_private is True
    assert (rule.host, rule.port, rule.path_prefix) == ("127.0.0.1", 8080, "/")


def test_url_and_host_together_are_refused():
    with pytest.raises(ValueError) as excinfo:
        ScopeSettings.model_validate({"targets": [{"url": "https://a.test/", "host": "a.test"}]})
    assert "not both" in str(excinfo.value)


def test_unknown_key_is_still_refused_next_to_url():
    with pytest.raises(ValueError) as excinfo:
        ScopeSettings.model_validate(
            {"targets": [{"url": "https://a.test/", "allow_privat": True}]}
        )
    assert "allow_privat" in str(excinfo.value)


def test_explicit_object_form_still_works():
    rule = ScopeRule.model_validate({"host": "lab.test", "port": 0})
    assert rule.scheme == "any"
    assert rule.port == 0


def test_url_targets_round_trip_through_disk(tmp_path):
    payload = default_config().to_dict()
    payload["scope"] = {"targets": ["https://lab.test/app", "!https://lab.test/app/logout"]}
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_config(config_file)
    assert len(loaded.scope.targets) == 2
    assert loaded.scope.targets[1].kind == "exclude"

    # Persisting the parsed form and loading it again must not change the rules.
    written = write_config(loaded, tmp_path / "rewritten.json")
    assert load_config(written) == loaded


def test_configuration_accepts_url_targets_directly():
    payload = default_config().to_dict()
    payload["scope"] = {"targets": ["https://lab.test/"]}
    config = AuroraConfig.model_validate(payload)
    assert config.scope.targets[0].host == "lab.test"
