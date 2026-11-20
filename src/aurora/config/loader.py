"""Reading and writing the workspace configuration file.

Writes are atomic (``os.replace`` of a fully written sibling file) so an
interrupted ``aurora init`` cannot leave a truncated ``config.json`` behind.
On POSIX the file is created with mode ``0600`` because scope definitions will
eventually live there.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from aurora.config.models import AuroraConfig
from aurora.errors import ConfigError
from aurora.paths import AppPaths
from aurora.validation import ValidationError

__all__ = ["config_path", "default_config", "load_config", "write_config"]


def config_path(paths: AppPaths, override: str | os.PathLike[str] | None = None) -> Path:
    """Return the configuration path, honouring an explicit ``--config``."""

    if override is None:
        return paths.config_file
    candidate = Path(os.fspath(override)).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return Path(os.path.normpath(candidate))


def default_config() -> AuroraConfig:
    """A fresh configuration with safe defaults."""

    return AuroraConfig()


def _format_validation_error(exc: ValidationError, path: Path) -> str:
    problems: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        problems.append(f"{location}: {error['msg']}")
    return f"invalid configuration in {path}: " + "; ".join(problems)


def load_config(path: Path) -> AuroraConfig:
    """Load and validate a configuration file."""

    target = Path(path).expanduser()
    if not target.exists():
        raise ConfigError(
            f"configuration file not found: {target}",
            hint="run 'aurora init' to create a workspace",
        )
    if not target.is_file():
        raise ConfigError(f"configuration path is not a file: {target}")

    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read configuration file {target}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"invalid JSON in {target} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigError(
            f"configuration root in {target} must be a JSON object, found {type(data).__name__}"
        )

    try:
        return AuroraConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc, target)) from exc


def write_config(config: AuroraConfig, path: Path) -> Path:
    """Write *config* atomically and return the destination path."""

    target = Path(path).expanduser()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(f"cannot create directory {target.parent}: {exc}") from exc

    payload = json.dumps(config.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temporary = target.with_name(target.name + ".tmp")

    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
        os.replace(temporary, target)
    except OSError as exc:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise ConfigError(f"cannot write configuration file {target}: {exc}") from exc

    return target
