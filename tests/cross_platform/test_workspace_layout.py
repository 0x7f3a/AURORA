"""Cross-platform layout matrix.

These tests run on any host and exercise the layout logic for both supported
platforms. They prove the *logic* is platform-independent; they do not prove
that a real Windows host behaves the same way, which only the Windows CI job can
establish.

Expectations are built from ``tmp_path`` rather than written as POSIX literals:
on Windows ``/xdg`` is a drive-relative path, so a hard-coded ``/xdg/aurora``
compares against ``D:/xdg/aurora`` and fails for a reason that has nothing to do
with the layout logic under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aurora.paths import AppPaths


def test_linux_uses_xdg_config_home(tmp_path):
    xdg = tmp_path / "xdg"
    paths = AppPaths.resolve(environ={"XDG_CONFIG_HOME": str(xdg)}, system="Linux")
    assert paths.home == xdg / "aurora"
    assert paths.home.is_absolute()


def test_linux_falls_back_to_dot_config():
    paths = AppPaths.resolve(environ={}, system="Linux")
    assert paths.home == Path.home() / ".config" / "aurora"
    assert paths.home.is_absolute()


def test_windows_uses_appdata(tmp_path):
    appdata = tmp_path / "appdata"
    paths = AppPaths.resolve(environ={"APPDATA": str(appdata)}, system="Windows")
    assert paths.home == appdata / "aurora"
    assert paths.home.is_absolute()


def test_windows_falls_back_to_roaming_appdata():
    paths = AppPaths.resolve(environ={}, system="Windows")
    assert paths.home == Path.home() / "AppData" / "Roaming" / "aurora"


def test_darwin_uses_application_support():
    paths = AppPaths.resolve(environ={}, system="Darwin")
    assert paths.home == Path.home() / "Library" / "Application Support" / "aurora"


@pytest.mark.parametrize("system", ["Linux", "Windows", "Darwin"])
def test_artefact_names_are_identical_on_every_platform(system, tmp_path):
    paths = AppPaths.resolve(
        environ={"APPDATA": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path)},
        system=system,
    )
    assert paths.config_file.name == "config.json"
    assert paths.database.name == "aurora.db"
    assert paths.log_file.name == "aurora.log"
    assert paths.reports_dir.name == "reports"
    assert paths.config_file.parent == paths.home
    assert paths.home.is_absolute()


@pytest.mark.parametrize("system", ["Linux", "Windows"])
def test_native_library_is_namespaced_per_platform(system, tmp_path):
    from aurora.platform.detect import PlatformInfo

    info = PlatformInfo.from_values(system=system, machine="x86_64")
    assert info.native_library_name in {"libaurora.so", "aurora.dll"}

    # The native loader must never search the current working directory, so the
    # name alone is never used as a path.
    assert "/" not in info.native_library_name
    assert "\\" not in info.native_library_name
