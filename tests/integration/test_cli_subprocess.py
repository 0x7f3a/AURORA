"""End-to-end CLI tests through a real interpreter.

These exercise what an operator actually runs: ``python -m aurora`` with an
ASCII-only stdout encoding (the legacy Windows console case) and an isolated
workspace. They also prove that no traceback escapes to the user.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"


def _environment(workspace: Path) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(_SRC) if not existing else str(_SRC) + os.pathsep + existing
    env["AURORA_HOME"] = str(workspace)
    env["PYTHONIOENCODING"] = "ascii"
    env["NO_COLOR"] = "1"
    env.pop("TERM", None)
    return env


def _run(arguments: list[str], workspace: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "aurora", *arguments],
        env=_environment(workspace),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_banner_survives_ascii_only_console(tmp_path):
    result = _run([], tmp_path / "ws")
    assert result.returncode == 0
    assert result.stdout.isascii(), "non-ASCII output on an ASCII console"
    assert "AURORA" in result.stdout
    assert "Traceback" not in result.stderr


def test_init_then_version_end_to_end(tmp_path):
    workspace = tmp_path / "ws"

    init = _run(["init"], workspace)
    assert init.returncode == 0, init.stderr
    assert (workspace / "config.json").is_file()
    assert (workspace / "aurora.db").is_file()

    version = _run(["version"], workspace)
    assert version.returncode == 0, version.stderr
    schema_line = next(
        line for line in version.stdout.splitlines() if line.startswith("schema")
    )
    assert schema_line.split()[-1] == "v1"
    assert "present" in version.stdout
    assert str(workspace) in version.stdout


def test_version_output_is_ascii_only(tmp_path):
    workspace = tmp_path / "ws"
    assert _run(["init"], workspace).returncode == 0

    result = _run(["version"], workspace)
    assert result.returncode == 0, result.stderr
    assert result.stdout.isascii(), "version output must survive a non-Unicode console"


def test_version_tolerates_a_damaged_configuration(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "config.json").write_text("{not json", encoding="utf-8")

    result = _run(["version"], workspace)
    assert result.returncode == 0, result.stderr
    assert "config" in result.stdout
    assert "Traceback" not in result.stderr
