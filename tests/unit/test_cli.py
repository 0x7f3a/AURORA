"""CLI behaviour: implemented commands, exit codes, idempotency, degradation."""

from __future__ import annotations

import json

import pytest

from aurora import DISPLAY_VERSION
from aurora.cli.main import main
from aurora.config.loader import default_config, load_config, write_config
from aurora.scope.models import ScopeSettings
from aurora.storage.database import Database
from aurora.storage.schema import SCHEMA_VERSION


def _workspace_with_scope(tmp_path, targets):
    workspace = tmp_path / "ws"
    assert main(["init", "--home", str(workspace)]) == 0
    config_file = workspace / "config.json"
    config = load_config(config_file).model_copy(
        update={"scope": ScopeSettings.model_validate({"targets": targets})}
    )
    write_config(config, config_file)
    return workspace


def test_bare_invocation_shows_banner_and_help(tmp_path, capsys):
    assert main(["--home", str(tmp_path / "ws")]) == 0
    output = capsys.readouterr().out
    assert DISPLAY_VERSION in output
    assert "WEB APPLICATION PENETRATION TESTING FRAMEWORK" in output
    assert "usage: aurora" in output
    assert "version" in output
    assert "init" in output


@pytest.mark.parametrize("command", ["discover", "assess", "findings", "report"])
def test_planned_commands_are_not_registered(tmp_path, command):
    # Planned features must fail as usage errors rather than pretend to run.
    with pytest.raises(SystemExit) as excinfo:
        main([command, "--home", str(tmp_path)])
    assert excinfo.value.code == 2


def test_version_reports_workspace_state(tmp_path, capsys):
    assert main(["version", "--home", str(tmp_path / "ws")]) == 0
    output = capsys.readouterr().out
    assert DISPLAY_VERSION in output
    assert "not created" in output
    assert "missing" in output
    assert "0x7f3a" in output
    assert "PLATFORM" not in output  # the banner belongs to `aurora` and `init`


def test_init_creates_config_and_database(tmp_path, capsys):
    workspace = tmp_path / "ws"
    assert main(["init", "--home", str(workspace)]) == 0
    output = capsys.readouterr().out

    config_file = workspace / "config.json"
    database_file = workspace / "aurora.db"
    assert config_file.is_file()
    assert database_file.is_file()
    assert (workspace / "reports").is_dir()
    assert "created" in output
    assert SCHEMA_VERSION == Database(database_file).schema_version()

    assert load_config(config_file) == default_config()


def test_init_is_idempotent_and_keeps_existing_config(tmp_path, capsys):
    workspace = tmp_path / "ws"
    assert main(["init", "--home", str(workspace)]) == 0
    capsys.readouterr()

    config_file = workspace / "config.json"
    payload = json.loads(config_file.read_text(encoding="utf-8"))
    payload["operator"] = "local-lab"
    config_file.write_text(json.dumps(payload), encoding="utf-8")

    assert main(["init", "--home", str(workspace)]) == 0
    output = capsys.readouterr().out
    assert "kept" in output
    assert load_config(config_file).operator == "local-lab"


def test_init_force_overwrites_configuration(tmp_path, capsys):
    workspace = tmp_path / "ws"
    assert main(["init", "--home", str(workspace)]) == 0
    config_file = workspace / "config.json"
    config_file.write_text("{}", encoding="utf-8")
    capsys.readouterr()

    assert main(["init", "--home", str(workspace), "--force"]) == 0
    output = capsys.readouterr().out
    assert "overwritten" in output
    assert load_config(config_file).operator == "0x7f3a"


def test_init_honours_log_level(tmp_path, capsys):
    workspace = tmp_path / "ws"
    assert main(["init", "--home", str(workspace), "--log-level", "DEBUG"]) == 0
    assert load_config(workspace / "config.json").log_level == "DEBUG"


def test_version_after_init_reports_presence(tmp_path, capsys):
    workspace = tmp_path / "ws"
    assert main(["init", "--home", str(workspace)]) == 0
    capsys.readouterr()

    assert main(["--home", str(workspace), "version"]) == 0
    output = capsys.readouterr().out
    schema_line = next(line for line in output.splitlines() if line.startswith("schema"))
    assert schema_line.split()[-1] == "v1"
    assert "present" in output


def test_ascii_flag_produces_ascii_output(tmp_path, capsys):
    assert main(["--ascii", "--home", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert output.isascii()
    assert "A U R O R A" in output


def test_global_flags_may_follow_the_subcommand(tmp_path, capsys):
    workspace = tmp_path / "ws"
    assert main(["init", "--home", str(workspace), "--ascii"]) == 0
    assert capsys.readouterr().out.isascii()


def test_unknown_command_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        main(["exploit", "--home", str(tmp_path)])
    assert excinfo.value.code == 2


def test_unknown_log_level_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        main(["version", "--home", str(tmp_path), "--log-level", "LOUD"])
    assert excinfo.value.code == 2


def test_missing_config_is_a_config_error(tmp_path, capsys):
    workspace = tmp_path / "ws"
    assert main(["init", "--home", str(workspace)]) == 0
    capsys.readouterr()
    assert main(["version", "--home", str(workspace), "--config", str(tmp_path / "nope.json")]) == 0
    assert "missing" in capsys.readouterr().out


def test_corrupt_database_is_reported_without_traceback(tmp_path, capsys):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "aurora.db").write_bytes(b"this is not a database")

    exit_code = main(["version", "--home", str(workspace)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Traceback" not in captured.err
    assert "unreadable" in captured.out


def test_scope_check_allows_an_in_scope_url(tmp_path, capsys):
    workspace = _workspace_with_scope(
        tmp_path, [{"scheme": "https", "host": "lab.test", "port": 443}]
    )
    capsys.readouterr()

    assert main(["scope", "check", "https://lab.test/admin", "--home", str(workspace)]) == 0
    output = capsys.readouterr().out
    assert "decision    ALLOW" in output
    assert "matches include rule" in output
    assert "https://lab.test/admin" in output


def test_scope_check_denies_an_out_of_scope_url(tmp_path, capsys):
    workspace = _workspace_with_scope(
        tmp_path, [{"scheme": "https", "host": "lab.test", "port": 443}]
    )
    capsys.readouterr()

    assert main(["scope", "check", "https://other.test/", "--home", str(workspace)]) == 6
    assert "decision    DENY" in capsys.readouterr().out


def test_scope_check_reports_a_malformed_url(tmp_path, capsys):
    workspace = _workspace_with_scope(tmp_path, [{"host": "lab.test"}])
    capsys.readouterr()

    assert main(["scope", "check", "ftp://lab.test/", "--home", str(workspace)]) == 6
    assert "error:" in capsys.readouterr().err


def test_scope_check_requires_a_workspace(tmp_path, capsys):
    exit_code = main(
        ["scope", "check", "https://lab.test/", "--home", str(tmp_path / "missing")]
    )
    assert exit_code == 3
    assert "aurora init" in capsys.readouterr().err


def test_scope_without_action_prints_help(tmp_path, capsys):
    assert main(["scope", "--home", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "check" in output
    assert "no DNS or network activity" in output


def test_empty_home_flag_is_rejected(capsys):
    exit_code = main(["--home", "   ", "version"])
    captured = capsys.readouterr()
    assert exit_code == 5  # PLATFORM exit code for an invalid workspace path
    assert "error:" in captured.err
