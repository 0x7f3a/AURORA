"""Cross-platform resolution of AURORA's on-disk workspace.

Resolution order (first match wins):

1. an explicit ``home_override`` (CLI ``--home``),
2. the ``AURORA_HOME`` environment variable,
3. the platform default:

   * Windows — ``%APPDATA%\\aurora`` (falling back to
     ``~/AppData/Roaming/aurora`` when ``APPDATA`` is unset, which is rare but
     possible in service contexts),
   * macOS — ``~/Library/Application Support/aurora``,
   * everything else — ``$XDG_CONFIG_HOME/aurora`` or ``~/.config/aurora``.

All returned paths are absolute and normalised. The module never creates
directories as a side effect of resolving them: only
:meth:`AppPaths.ensure_layout` writes to disk, so read-only commands such as
``aurora version`` cannot leave files behind in a directory the operator did
not intend to initialise.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from aurora.errors import PlatformError

__all__ = [
    "APP_DIRNAME",
    "CONFIG_FILENAME",
    "DATABASE_FILENAME",
    "ENV_HOME",
    "LOG_FILENAME",
    "REPORTS_DIRNAME",
    "AppPaths",
]

APP_DIRNAME = "aurora"
ENV_HOME = "AURORA_HOME"
CONFIG_FILENAME = "config.json"
DATABASE_FILENAME = "aurora.db"
LOG_FILENAME = "aurora.log"
REPORTS_DIRNAME = "reports"


def _absolute(path: Path) -> Path:
    """Expand ``~`` and make *path* absolute without touching the filesystem."""

    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return Path(os.path.normpath(expanded))


def _default_home(environ: Mapping[str, str], system: str) -> Path:
    if system == "Windows":
        appdata = environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / APP_DIRNAME
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIRNAME
    xdg = environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP_DIRNAME


def _current_system() -> str:
    if os.name == "nt":
        return "Windows"
    if sys.platform == "darwin":
        return "Darwin"
    return "Linux"


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Absolute locations of the workspace artefacts."""

    home: Path
    config_file: Path
    database: Path
    log_file: Path
    reports_dir: Path

    @classmethod
    def resolve(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        system: str | None = None,
        home_override: str | os.PathLike[str] | None = None,
    ) -> "AppPaths":
        """Resolve workspace paths.

        *system* and *environ* exist so that Windows and Linux layout rules can
        be exercised from a single host in tests.
        """

        env = os.environ if environ is None else environ
        target_system = system or _current_system()

        if home_override is not None:
            # Check the string before Path() normalises it: Path("") is ".", so an
            # empty flag value would otherwise silently mean the current directory.
            override_text = os.fspath(home_override)
            if not str(override_text).strip():
                raise PlatformError("--home requires a non-empty path")
            home = _absolute(Path(override_text))
        elif env.get(ENV_HOME, "").strip():
            home = _absolute(Path(env[ENV_HOME].strip()))
        else:
            home = _absolute(_default_home(env, target_system))

        return cls(
            home=home,
            config_file=home / CONFIG_FILENAME,
            database=home / DATABASE_FILENAME,
            log_file=home / LOG_FILENAME,
            reports_dir=home / REPORTS_DIRNAME,
        )

    def ensure_layout(self) -> None:
        """Create the workspace directories and restrict their permissions.

        On POSIX the workspace is created with mode ``0700`` because it will
        eventually hold scope definitions and evidence. On Windows the POSIX
        mode is not meaningful (ACLs govern access); the limitation is
        documented in ``docs/LIMITATIONS.md`` rather than silently ignored.
        """

        for directory in (self.home, self.reports_dir):
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:  # pragma: no cover - depends on host state
                raise PlatformError(
                    f"cannot create workspace directory {directory}: {exc}"
                ) from exc
            self._restrict(directory)

    @staticmethod
    def _restrict(directory: Path) -> None:
        if os.name == "nt":
            return
        try:
            os.chmod(directory, 0o700)
        except OSError:  # pragma: no cover - e.g. read-only mounts
            pass
