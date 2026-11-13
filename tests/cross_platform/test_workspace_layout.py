"""Cross-platform layout matrix.

These tests run on any host and exercise the layout logic for both supported
platforms. They prove the *logic* is platform-independent; they do not prove
that a real Windows host behaves the same way, which only the Windows CI job can
establish.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aurora.paths import AppPaths

CASES = [
    (
        "Linux",
        {"XDG_CONFIG_HOME": "/xdg"},
        Path("/xdg/aurora"),
    ),
    (
        "Linux",
        {"HOME": "/home/operator"},
        None,  # resolved through Path.home() of the running host
    ),
    (
        "Windows",
        {"APPDATA": "/appdata/roaming"},
        Path("/appdata/roaming/aurora"),
    ),
]


@pytest.mark.parametrize(("system", "environ", "expected"), CASES)
def test_workspace_home_per_platform(system, environ, expected):
    paths = AppPaths.resolve(environ=environ, system=system)
    assert paths.home.is_absolute()
    assert paths.home.name == "aurora"
    if expected is not None:
        assert paths.home == expected


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
