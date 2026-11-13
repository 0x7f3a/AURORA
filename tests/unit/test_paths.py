"""Workspace path resolution, exercised for every supported layout rule."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from aurora.errors import PlatformError
from aurora.paths import AppPaths


def test_linux_uses_xdg_config_home(tmp_path):
    xdg = tmp_path / "xdg"
    paths = AppPaths.resolve(environ={"XDG_CONFIG_HOME": str(xdg)}, system="Linux")
    assert paths.home == xdg / "aurora"


def test_linux_defaults_to_dot_config():
    paths = AppPaths.resolve(environ={}, system="Linux")
    assert paths.home == Path(os.path.expanduser("~/.config/aurora"))


def test_windows_uses_appdata(tmp_path):
    appdata = tmp_path / "appdata"
    paths = AppPaths.resolve(environ={"APPDATA": str(appdata)}, system="Windows")
    assert paths.home == appdata / "aurora"


def test_windows_falls_back_when_appdata_missing():
    paths = AppPaths.resolve(environ={}, system="Windows")
    assert paths.home.parts[-3:] == ("AppData", "Roaming", "aurora")


def test_macos_uses_application_support():
    paths = AppPaths.resolve(environ={}, system="Darwin")
    assert paths.home.parts[-2:] == ("Application Support", "aurora")


def test_environment_override_wins_over_platform_default(tmp_path):
    target = tmp_path / "aurora-home"
    paths = AppPaths.resolve(
        environ={"AURORA_HOME": str(target), "XDG_CONFIG_HOME": str(tmp_path / "ignored")},
        system="Linux",
    )
    assert paths.home == target


def test_blank_environment_override_is_ignored(tmp_path):
    xdg = tmp_path / "xdg"
    paths = AppPaths.resolve(
        environ={"AURORA_HOME": "   ", "XDG_CONFIG_HOME": str(xdg)}, system="Linux"
    )
    assert paths.home == xdg / "aurora"


def test_explicit_override_wins_over_environment(tmp_path):
    paths = AppPaths.resolve(
        environ={"AURORA_HOME": str(tmp_path / "from-env")},
        system="Linux",
        home_override=tmp_path / "from-flag",
    )
    assert paths.home == tmp_path / "from-flag"


def test_relative_override_becomes_absolute():
    paths = AppPaths.resolve(environ={}, system="Linux", home_override="relative-workspace")
    assert paths.home.is_absolute()
    assert paths.home.name == "relative-workspace"


def test_empty_override_is_rejected():
    with pytest.raises(PlatformError):
        AppPaths.resolve(environ={}, system="Linux", home_override="  ")


def test_derived_artefacts_are_stable(tmp_path):
    paths = AppPaths.resolve(environ={}, system="Linux", home_override=tmp_path)
    assert paths.config_file == tmp_path / "config.json"
    assert paths.database == tmp_path / "aurora.db"
    assert paths.log_file == tmp_path / "aurora.log"
    assert paths.reports_dir == tmp_path / "reports"


def test_ensure_layout_creates_directories(tmp_path):
    paths = AppPaths.resolve(environ={}, system="Linux", home_override=tmp_path / "ws")
    paths.ensure_layout()
    assert paths.home.is_dir()
    assert paths.reports_dir.is_dir()
    # The config and database must not be created as a side effect.
    assert not paths.config_file.exists()
    assert not paths.database.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits do not apply on Windows")
def test_ensure_layout_restricts_permissions(tmp_path):
    paths = AppPaths.resolve(environ={}, system="Linux", home_override=tmp_path / "ws")
    paths.ensure_layout()
    mode = stat.S_IMODE(paths.home.stat().st_mode)
    assert mode == 0o700
