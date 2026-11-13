# AURORA Limitations

This file states what has been verified, what has not, and what does not exist.
It is updated at every milestone; if a claim cannot be backed by a command that
was executed, it does not belong in the README.

Last updated: milestone 1 (`0.1.0-dev`).

---

## 1. Platform verification status

| Claim | Status |
|---|---|
| Linux (Ubuntu 24.04.5 LTS, x86_64, Python 3.12.3): install, CLI, tests | **TESTED** |
| Windows 10/11: install, CLI, tests | **NOT EXECUTED** |
| Windows CI workflow exists and is valid YAML | **IMPLEMENTED — NOT EXECUTED** (no GitHub runner was available in the development environment) |
| Windows path logic (`%APPDATA%`, `aurora.dll`) | **TESTED as pure logic** on Linux; not executed on a Windows host |
| macOS support | **NOT SUPPORTED** (naming rules exist; untested and unsupported) |

The development environment provided Linux only. No Windows execution has
happened at any point, and the project does not claim Windows compatibility
until the `windows.yml` job has actually run green on a Windows runner.

---

## 2. Implemented functionality

- Workspace resolution and creation (`AURORA_HOME`, `%APPDATA%`, XDG, `--home`).
- Configuration model with enforced bounds and atomic writes.
- Platform detection and native library naming.
- SQLite schema v1 (eight tables), pragmas, forward-only migrations.
- Assessment repository: create, get, list, count.
- Logging with UTC timestamps and credential redaction on every handler.
- CLI: `aurora`, `aurora version`, `aurora init` with `--force`, global flags,
  stable exit codes, ASCII/narrow banner degradation.
- 130 automated tests on Linux (`.venv/bin/python -m pytest`: `130 passed`).

## 3. Not implemented

- **Networking.** No HTTP client wrapper, no requests are ever made.
- **Scope enforcement.** Scope tables exist; no authorisation engine exists.
- **Discovery and checks.** No crawling, no assessment modules.
- **Verification and findings engine.** Findings table exists; nothing writes to
  it and no severity/confidence logic exists.
- **Reporting.** No JSON/Markdown/terminal report generator.
- **Native C component.** No `CMakeLists.txt`, no C source, no loader.
  `aurora version` correctly reports `libaurora.so (not built)`.
- **Assessment lifecycle.** No `assess` command, no run orchestration.
- **Log rotation.** Single log file per workspace; rotation is planned. Python's
  `RotatingFileHandler` is avoided for now because renaming an open file is
  fragile on Windows.

## 4. Unverified protections

| Protection | Reality |
|---|---|
| DNS-rebinding / IP pinning | **Not implemented.** Design caveat documented in `ARCHITECTURE.md` §6. Until a local fixture proves the connected address equals the validated address, no such protection may be claimed. |
| Redirection scope bypass | **Not applicable yet** — no network code exists. The manual redirect design is specified, not built. |
| Response-size and rate limits | Enforced by configuration validation only; nothing consumes them yet. |
| Encrypted storage | **Not implemented.** The SQLite file is plaintext. Workspace permissions are the only control. |
| Windows ACLs | **Not implemented.** `chmod`-style hardening is POSIX-only and skipped on Windows by design. |
| Secret redaction completeness | Pattern-based. It covers auth headers, cookies, URL userinfo and common query keys. A credential in an unusual field will not be caught. |

## 5. Testing gaps

- No tests against a real HTTP server yet (no HTTP layer).
- No fuzzing. Native fuzzing is not applicable until Phase 5.
- The Rich/colour output path is not exercised in CI: `pytest` captures output,
  which is not a TTY, so only the plain writer path runs.
- Terminal detection is tested with synthetic streams; no legacy Windows console
  (code page 437/1252) was executed.
- Cross-platform tests validate the *rules*, not a second operating system.
- Only schema v1 exists, so no migration-from-older-version test is possible yet.
- Concurrent access to one workspace from two processes is not tested. SQLite
  uses a 5 s busy timeout and WAL where available.

## 6. Environmental restrictions in the development environment

- No CMake and no Clang were installed (`gcc 13.3.0` and `make 4.3` were
  present), so the native build system cannot be validated here even when it
  exists; it will need `pip install cmake` or a system package.
- No GitHub credentials were available, so CI workflows were authored but never
  executed, and no push to the remote repository was performed.
- No Windows host was available.

## 7. Known technical debt

- `aurora version` opens the database read/write to read `PRAGMA user_version`;
  a read-only connection would be preferable.
- The CLI resolves configuration paths but does not yet load and validate the
  configuration for commands other than `init`; there is nothing to configure
  them with yet.
- `PlatformInfo.describe()` and the banner both format platform text; they are
  separate so the banner can stay upper-case, but they should converge on one
  source of truth as reporting is added.
- Log level from `config.json` is not yet applied automatically; only
  `--log-level` is honoured at runtime.
