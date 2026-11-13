# AURORA

**Web Application Penetration Testing Framework** — version `0.1.0-dev`

AURORA is a modular, evidence-driven assessment framework for web applications
you own or are explicitly authorised to test. It separates *observations* from
*verified findings*, records the evidence behind every claim, and reports what
was actually executed, skipped, or not implemented.

> AURORA is under active development. Delivered so far: the Python foundation
> (workspace, configuration, platform detection, SQLite schema, redacting
> logging, CLI) and the bounded network layer (scope engine, address policy,
> pinned HTTP transport with manual redirects, budgets, timeouts, cancellation).
> Discovery, assessment modules, verification and reporting are **not
> implemented yet**, and no native component exists.

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
| URL normalisation and scope policy | IMPLEMENTED AND TESTED |
| Address policy (private networks opt-in, link-local always denied) | IMPLEMENTED AND TESTED |
| Pinned HTTP transport, manual redirects, Host/SNI preservation | IMPLEMENTED AND TESTED on Linux against local fixtures |
| Budgets: requests, wall clock, rate, concurrency, size, timeouts, cancellation | IMPLEMENTED AND TESTED |
| `aurora scope check` | IMPLEMENTED AND TESTED |
| Native C component | NOT IMPLEMENTED (Phase 5; responsibility defined in `docs/ARCHITECTURE.md`) |
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
aurora scope check URL       explain whether a URL is inside the configured scope
```

Global options: `--home PATH`, `--config PATH`, `--no-color`, `--ascii`,
`--log-level {DEBUG,INFO,WARNING,ERROR}`. They may appear before or after the
subcommand.

Planned commands (`discover`, `assess`, `findings`, `report`) are deliberately
**not registered** until they work: invoking one is a usage error, not a stub.

Scope lives in `config.json` and is evaluated on a normalised URL:

```json
{
  "scope": {
    "targets": [
      {"scheme": "https", "host": "lab.test", "port": 443},
      {"kind": "exclude", "host": "lab.test", "path_prefix": "/logout"},
      {"scheme": "http", "host": "127.0.0.1", "port": 8080, "allow_private": true}
    ]
  }
}
```

Exclusions always win, `port: 0` means any port, `*.example.test` matches
subdomains but not the apex, and `allow_private` is required before a rule may
reach loopback/RFC1918 addresses. `aurora scope check` performs no DNS lookup
and makes no request.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | unexpected failure |
| 2 | usage error (malformed command line) |
| 3 | configuration error |
| 4 | storage/database error |
| 5 | platform error (unsupported or unusable environment) |
| 6 | network error, scope refusal, or `scope check` denial |

## Testing

```bash
python -m pytest
```

The suite covers unit behaviour, a subprocess-level CLI run under an ASCII-only
console, cross-platform layout rules, and integration tests against local HTTP
and HTTPS fixtures. Those fixtures record the peer address, `Host` header, TLS
SNI and request counts server-side, which is how the connection-boundary claims
are checked. See [`docs/NETWORK-BOUNDARY.md`](docs/NETWORK-BOUNDARY.md) and
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) for what is **not** verified.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Network boundary experiment](docs/NETWORK-BOUNDARY.md)
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
