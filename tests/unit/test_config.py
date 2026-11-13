"""Configuration loading, validation and atomic persistence."""

from __future__ import annotations

import json
import os
import stat

import pytest

from aurora.config.loader import default_config, load_config, write_config
from aurora.config.models import AuroraConfig, NetworkLimits
from aurora.errors import ConfigError


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_defaults_are_safe_and_valid():
    config = default_config()
    assert config.schema_version == 1
    assert config.profile == "safe"
    assert config.network.max_redirects == 5
    assert config.network.max_concurrency == 8
    assert config.run.max_requests == 2000
    assert config.operator == "0x7f3a"


def test_round_trip_through_disk(tmp_path):
    target = tmp_path / "config.json"
    original = default_config().model_copy(update={"log_level": "DEBUG"})
    write_config(original, target)

    assert target.is_file()
    assert not (tmp_path / "config.json.tmp").exists()
    assert load_config(target) == original


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits do not apply on Windows")
def test_config_file_is_private(tmp_path):
    target = write_config(default_config(), tmp_path / "config.json")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_missing_file_points_at_init(tmp_path):
    with pytest.raises(ConfigError) as excinfo:
        load_config(tmp_path / "missing.json")
    assert "aurora init" in str(excinfo.value)


def test_malformed_json_is_reported_with_position(tmp_path):
    target = tmp_path / "config.json"
    target.write_text('{"schema_version": 1,', encoding="utf-8")
    with pytest.raises(ConfigError) as excinfo:
        load_config(target)
    assert "invalid JSON" in str(excinfo.value)
    assert "line" in str(excinfo.value)


def test_non_object_root_is_rejected(tmp_path):
    target = _write_json(tmp_path / "config.json", [1, 2, 3])
    with pytest.raises(ConfigError) as excinfo:
        load_config(target)
    assert "must be a JSON object" in str(excinfo.value)


def test_unknown_keys_are_rejected(tmp_path):
    payload = default_config().to_dict()
    payload["network"]["netwrok_timeout"] = 5
    target = _write_json(tmp_path / "config.json", payload)
    with pytest.raises(ConfigError) as excinfo:
        load_config(target)
    assert "netwrok_timeout" in str(excinfo.value)


def test_negative_timeout_is_rejected(tmp_path):
    payload = default_config().to_dict()
    payload["network"]["connect_timeout_seconds"] = -1
    target = _write_json(tmp_path / "config.json", payload)
    with pytest.raises(ConfigError) as excinfo:
        load_config(target)
    assert "connect_timeout_seconds" in str(excinfo.value)


def test_excessive_redirect_budget_is_rejected(tmp_path):
    payload = default_config().to_dict()
    payload["network"]["max_redirects"] = 21
    target = _write_json(tmp_path / "config.json", payload)
    with pytest.raises(ConfigError) as excinfo:
        load_config(target)
    assert "max_redirects" in str(excinfo.value)


def test_read_timeout_shorter_than_connect_timeout_is_rejected(tmp_path):
    payload = default_config().to_dict()
    payload["network"]["connect_timeout_seconds"] = 10
    payload["network"]["read_timeout_seconds"] = 5
    target = _write_json(tmp_path / "config.json", payload)
    with pytest.raises(ConfigError) as excinfo:
        load_config(target)
    assert "read_timeout_seconds" in str(excinfo.value)


def test_zero_concurrency_is_rejected():
    with pytest.raises(ValueError):
        NetworkLimits(max_concurrency=0)


def test_blank_operator_is_rejected():
    with pytest.raises(ValueError):
        AuroraConfig(operator="   ")


def test_operator_control_characters_are_rejected():
    with pytest.raises(ValueError):
        AuroraConfig(operator="bad\noperator")


def test_multiline_user_agent_is_rejected():
    with pytest.raises(ValueError):
        AuroraConfig(user_agent="aurora/0.1\nInjected: 1")


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError):
        AuroraConfig(profile="aggressive")


def test_null_redirect_budget_is_allowed():
    config = AuroraConfig(network=NetworkLimits(max_redirects=0))
    assert config.network.max_redirects == 0
