# AURORA

**Web Application Penetration Testing Framework** — version `0.1.0-dev`

AURORA is a modular, evidence-driven assessment framework for web applications
you own or are explicitly authorised to test. It separates *observations* from
*verified findings*, records the evidence behind every claim, and reports what
was actually executed, skipped, or not implemented.

> AURORA is under active development. The current milestone delivers the
> Python foundation: workspace layout, configuration, platform detection,
> the SQLite schema, logging with credential redaction, and the CLI. Networking,
> discovery, assessment modules and reporting are **not implemented yet**.

## Status

| Area | State |
|---|---|
| Package layout, CLI entry point, banner | IMPLEMENTED AND TESTED (Linux) |
| Platform detection (Linux/Windows/macOS rules, native library names) | IMPLEMENTED AND TESTED (logic), Windows host not executed |
| Workspace paths, `$AURORA_HOME`, `%APPDATA%` | IMPLEMENTED AND TESTED (Linux), Windows host not executed |
| Configuration model and validation | IMPLEMENTED AND TESTED |
| Logging with credential redaction | IMPLEMENTED AND TESTED |
| SQLite schema (assessments, scope, assets, observations, findings, evidence, module runs, errors) | IMPLEMENTED AND TESTED |
| Assessment repository | IMPLEMENTED AND TESTED (create/get/list/count) |
| Native C component | NOT IMPLEMENTED (Phase 5; responsibility defined in `docs/ARCHITECTURE.md`) |
| Scope enforcement, HTTP transport, redirect policy | NOT IMPLEMENTED (Phase 4) |
| Discovery, assessment modules, verification, reporting | NOT IMPLEMENTED (Phases 6–7) |

The precise evidence behind this table is in
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

## Requirements

- Python 3.11 or newer
- Windows 10/11 x86_64, or Linux x86_64 (Ubuntu, Debian, Kali)
- No native toolchain is required yet; CMake and a C compiler become necessary
  only for the Phase 5 native component.

## Quick start

```bash
python -m venv .venv
# Linux
source .venv/bin/activate
# Windows PowerShell
# .\.venv\Scripts\Activate.ps1

pip install -e ".[dev]"

aurora init
aurora version
```

`aurora init` creates a workspace (`config.json`, `aurora.db`, `reports/`) in the
platform default location:

- Linux: `$XDG_CONFIG_HOME/aurora` or `~/.config/aurora`
- Windows: `%APPDATA%\aurora`

Use `--home PATH` or the `AURORA_HOME` environment variable to isolate a
workspace, for example one per lab:

```bash
aurora init --home ./lab-workspace
aurora version --home ./lab-workspace
```

## CLI

```text
aurora                       show the banner and help
aurora init [--force]        create the workspace (config + SQLite schema)
aurora version               show build, platform, workspace and schema state
```

Global options: `--home PATH`, `--config PATH`, `--no-color`, `--ascii`,
`--log-level {DEBUG,INFO,WARNING,ERROR}`. They may appear before or after the
subcommand.

Planned commands (`scope add`, `discover`, `assess`, `findings`, `report`) are
deliberately **not registered** until they work: invoking one is a usage error,
not a stub.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | unexpected failure |
| 2 | usage error (malformed command line) |
| 3 | configuration error |
| 4 | storage/database error |
| 5 | platform error (unsupported or unusable environment) |

## Testing

```bash
python -m pytest
```

The suite covers unit behaviour, a subprocess-level CLI run under an ASCII-only
console, and cross-platform layout rules exercised on any host. See
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) for what is **not** verified.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Installation — Linux](docs/INSTALLATION-LINUX.md)
- [Installation — Windows](docs/INSTALLATION-WINDOWS.md)
- [Security policy](docs/SECURITY.md)
- [Limitations](docs/LIMITATIONS.md)

## Authorisation

AURORA performs active security testing. Use it only against systems you own or
have written permission to assess. Scope enforcement, rate limiting and
resource caps are architectural requirements of this project, not optional
features; see [`docs/SECURITY.md`](docs/SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).
