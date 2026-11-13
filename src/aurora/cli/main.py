"""AURORA command-line interface.

Only commands that are implemented are registered. ``version`` reports the
build, the host platform, the workspace layout and the database schema so that
support requests and reports can state what was actually running. ``init``
creates the workspace (config file, directories, SQLite schema) and is
idempotent: it never overwrites an existing configuration unless ``--force`` is
given.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

from aurora import BUILD, DISPLAY_VERSION, OPERATOR, PROGRAM_NAME
from aurora.cli.banner import BannerContext, render_banner
from aurora.cli.console import CliConsole
from aurora.config.loader import config_path, default_config, load_config, write_config
from aurora.errors import AuroraError, StorageError
from aurora.exit_codes import ExitCode
from aurora.observability.logging import LOG_LEVELS, configure_logging
from aurora.paths import AppPaths
from aurora.platform.detect import PlatformInfo
from aurora.platform.terminal import TerminalInfo
from aurora.scope.policy import ScopePolicy
from aurora.scope.urls import normalize_url
from aurora.storage.database import Database

__all__ = ["build_parser", "entrypoint", "main"]

_LOG = logging.getLogger(__name__)

_EPILOG = """\
examples:
  aurora                       show the banner and this help
  aurora init                  create the workspace in the default location
  aurora init --home ./lab     create an isolated workspace for a local lab
  aurora version               show build, platform and workspace state
  aurora scope check https://lab.test/admin
                               explain whether a URL is inside the configured scope

AURORA is for systems you own or are explicitly authorised to assess.
"""


def _add_common_flags(parser: argparse.ArgumentParser, *, suppressed: bool = False) -> None:
    default = argparse.SUPPRESS if suppressed else None
    parser.add_argument(
        "--home",
        metavar="PATH",
        default=default,
        help="workspace directory (default: platform-specific; overrides AURORA_HOME)",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=default,
        help="configuration file (default: <home>/config.json)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=argparse.SUPPRESS if suppressed else False,
        help="disable coloured output",
    )
    parser.add_argument(
        "--ascii",
        action="store_true",
        default=argparse.SUPPRESS if suppressed else False,
        help="force the ASCII banner (legacy consoles)",
    )
    parser.add_argument(
        "--log-level",
        choices=LOG_LEVELS,
        default=default,
        help="stderr log level (default: WARNING)",
    )


def build_parser() -> argparse.ArgumentParser:
    """The top-level argument parser (used by tests and help rendering)."""

    return _build_parsers()[0]


def _build_parsers() -> tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
    parser = argparse.ArgumentParser(
        prog="aurora",
        description=f"{PROGRAM_NAME} - web application penetration testing framework",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common_flags(parser)

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    version_parser = subparsers.add_parser(
        "version",
        help="show build, platform and workspace state",
        description="Show build, host platform, workspace paths and database schema version.",
    )
    _add_common_flags(version_parser, suppressed=True)

    init_parser = subparsers.add_parser(
        "init",
        help="create the workspace (config and database)",
        description="Create the workspace directories, the configuration file and the SQLite schema.",
    )
    _add_common_flags(init_parser, suppressed=True)
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing configuration file with defaults",
    )

    scope_parser = subparsers.add_parser(
        "scope",
        help="inspect the configured scope without making requests",
        description=(
            "Inspect the scope configured in config.json. Scope is evaluated on a "
            "normalised URL; no DNS or network activity takes place."
        ),
    )
    _add_common_flags(scope_parser, suppressed=True)
    scope_actions = scope_parser.add_subparsers(dest="scope_command", metavar="<action>")

    check_parser = scope_actions.add_parser(
        "check",
        help="evaluate a URL against the configured scope",
        description=(
            "Explain whether a URL is inside the configured scope. Exits 0 when the "
            "URL is allowed and 6 when it is refused."
        ),
    )
    _add_common_flags(check_parser, suppressed=True)
    check_parser.add_argument("url", help="URL to evaluate (http or https)")

    return parser, scope_parser


def _banner(context_platform: PlatformInfo, terminal: TerminalInfo) -> str:
    context = BannerContext(
        version=DISPLAY_VERSION,
        operator=OPERATOR,
        build=BUILD,
        platform_label=context_platform.banner_label,
    )
    return render_banner(
        context,
        width=terminal.width,
        ascii_only=not terminal.unicode_ok,
    )


def _describe_file(path: Path) -> str:
    return f"{path} ({'present' if path.exists() else 'missing'})"


def _schema_description(database_path: Path) -> str:
    if not database_path.exists():
        return "not created"
    database = Database(database_path)
    try:
        version = database.schema_version()
    except StorageError as exc:
        return f"unreadable ({exc})"
    finally:
        database.close()
    return f"v{version}" if version else "uninitialised"


def _cmd_version(args: argparse.Namespace, paths: AppPaths, console: CliConsole) -> int:
    platform_info = PlatformInfo.collect()
    configuration = config_path(paths, getattr(args, "config", None))

    try:
        native = platform_info.native_library_name
        native_text = f"{native} (not built)"
    except AuroraError:
        native = "unavailable"
        native_text = "unavailable (unsupported platform)"

    rows: list[tuple[str, str]] = [
        ("version", DISPLAY_VERSION),
        ("build", BUILD),
        ("operator", OPERATOR),
        (
            "platform",
            f"{platform_info.system} {platform_info.release} {platform_info.normalized_machine}".strip(),
        ),
        ("python", f"{platform_info.python_implementation} {platform_info.python_version}"),
        ("supported", "yes" if platform_info.is_supported else "no (Windows and Linux are supported)"),
        ("native", native_text),
        ("schema", _schema_description(paths.database)),
        ("home", str(paths.home)),
        ("config", _describe_file(configuration)),
        ("database", _describe_file(paths.database)),
    ]

    console.out(f"{PROGRAM_NAME} {DISPLAY_VERSION}")
    console.out("    " + ("-" * 53))
    for label, value in rows:
        console.out(f"{label:<12}{value}")
    return int(ExitCode.OK)


def _cmd_init(
    args: argparse.Namespace,
    paths: AppPaths,
    console: CliConsole,
    terminal: TerminalInfo,
) -> int:
    platform_info = PlatformInfo.collect()
    console.out(_banner(platform_info, terminal))
    console.out("")

    paths.ensure_layout()

    configuration = config_path(paths, getattr(args, "config", None))
    existed = configuration.exists()
    if existed and not getattr(args, "force", False):
        config_state = "kept (already exists, use --force to overwrite)"
    else:
        new_config = default_config()
        requested_level = getattr(args, "log_level", None)
        if requested_level:
            new_config = new_config.model_copy(update={"log_level": requested_level})
        write_config(new_config, configuration)
        config_state = "overwritten" if existed else "created"

    database = Database(paths.database)
    try:
        schema_version = database.initialize()
    finally:
        database.close()

    _LOG.info("workspace initialised at %s (schema v%s)", paths.home, schema_version)

    console.out("WORKSPACE")
    for label, value in (
        ("home", str(paths.home)),
        ("config", f"{configuration} ({config_state})"),
        ("database", f"{paths.database} (schema v{schema_version})"),
        ("logs", str(paths.log_file)),
        ("reports", str(paths.reports_dir)),
    ):
        console.out(f"  {label:<10}{value}")
    console.out("")
    console.out("next: aurora version")
    return int(ExitCode.OK)


def _cmd_scope_check(
    args: argparse.Namespace,
    paths: AppPaths,
    console: CliConsole,
) -> int:
    configuration = config_path(paths, getattr(args, "config", None))
    config = load_config(configuration)
    policy = ScopePolicy.from_settings(config.scope)

    url = normalize_url(args.url)
    decision = policy.evaluate(url)

    console.out(f"url         {args.url}")
    console.out(f"normalized  {url.to_url()}")
    console.out(f"decision    {'ALLOW' if decision.allowed else 'DENY'}")
    console.out(f"reason      {decision.reason}")
    if decision.allowed:
        console.out(
            "private     "
            + ("permitted for this target" if decision.allow_private else "not permitted")
        )
    console.out("note        address policy is evaluated per request, not here")
    return int(ExitCode.OK) if decision.allowed else int(ExitCode.NETWORK)


def _cmd_scope(
    args: argparse.Namespace,
    paths: AppPaths,
    console: CliConsole,
    scope_parser: argparse.ArgumentParser,
) -> int:
    if getattr(args, "scope_command", None) == "check":
        return _cmd_scope_check(args, paths, console)
    scope_parser.print_help()
    return int(ExitCode.OK)


def _cmd_default(parser: argparse.ArgumentParser, console: CliConsole, terminal: TerminalInfo) -> int:
    console.out(_banner(PlatformInfo.collect(), terminal))
    console.out("")
    parser.print_help()
    return int(ExitCode.OK)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser, scope_parser = _build_parsers()
    args = parser.parse_args(argv)

    terminal = TerminalInfo.detect(
        ascii_only=bool(getattr(args, "ascii", False)),
        no_color=bool(getattr(args, "no_color", False)),
    )
    console = CliConsole(color=terminal.color_ok, ascii_only=not terminal.unicode_ok)

    try:
        paths = AppPaths.resolve(home_override=getattr(args, "home", None))
    except AuroraError as exc:
        console.err(f"error: {exc}")
        return int(exc.exit_code)

    try:
        configure_logging(
            level=getattr(args, "log_level", None) or "WARNING",
            log_file=paths.log_file if paths.home.exists() else None,
        )
    except (AuroraError, ValueError) as exc:
        console.err(f"warning: logging disabled: {exc}")

    try:
        if args.command == "version":
            return _cmd_version(args, paths, console)
        if args.command == "init":
            return _cmd_init(args, paths, console, terminal)
        if args.command == "scope":
            return _cmd_scope(args, paths, console, scope_parser)
        return _cmd_default(parser, console, terminal)
    except AuroraError as exc:
        console.err(f"error: {exc}")
        return int(exc.exit_code)
    except KeyboardInterrupt:
        console.err("interrupted")
        return 130


def entrypoint() -> None:
    """Console-script entry point."""

    raise SystemExit(int(main()))


if __name__ == "__main__":  # pragma: no cover - convenience
    raise SystemExit(int(main()))
