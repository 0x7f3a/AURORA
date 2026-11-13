# AURORA Limitations

This file states what has been verified, what has not, and what does not exist.
It is updated at every milestone; if a claim cannot be backed by a command that
was executed, it does not belong in the README.

Last updated: milestone 2, Phase 4 (`0.1.0-dev`).

---

## 1. Platform verification status

| Claim | Status |
|---|---|
| Linux (Ubuntu 24.04.5 LTS, x86_64, Python 3.12.3): install, CLI, 287 tests, HTTP/HTTPS fixtures | **TESTED** |
| Windows 10/11: install, CLI, tests | **NOT EXECUTED** |
| Windows CI workflow exists and is valid YAML | **IMPLEMENTED — NOT EXECUTED** (no GitHub runner was available) |
| Windows path logic (`%APPDATA%`, `aurora.dll`) | **TESTED as pure logic** on Linux; not executed on a Windows host |
| DNS-rebinding experiment (`127.0.0.2` attacker server) | **TESTED on Linux**; the test **skips** on platforms that cannot bind a second loopback address |
| IPv6 connection behaviour | **NOT EXECUTED** (URL construction unit-tested only) |
| macOS support | **NOT SUPPORTED** |

The development environment provided Linux only. No Windows execution has
happened at any point, and the project does not claim Windows compatibility
until the `windows.yml` job has actually run green on a Windows runner.

---

## 2. Implemented functionality

- Workspace resolution and creation (`AURORA_HOME`, `%APPDATA%`, XDG, `--home`).
- Configuration model with enforced bounds and atomic writes, including scope.
- Platform detection and native library naming.
- SQLite schema v1 (eight tables), pragmas, forward-only migrations.
- Assessment repository: create, get, list, count.
- Logging with UTC timestamps and credential redaction on every handler.
- CLI: `aurora`, `aurora version`, `aurora init`, `aurora scope check`, global
  flags, stable exit codes, ASCII/narrow banner degradation.
- URL normalisation and scope policy (exclusions first, wildcard subdomains,
  path-prefix boundaries, per-rule private-network permission).
- Address policy (link-local/multicast/unspecified/reserved always denied;
  loopback/RFC1918/ULA/shared only with `allow_private`; IPv4-mapped IPv6
  classified by its embedded address).
- Pinned HTTPX transport: manual redirect chains, `Host` and TLS SNI preserved,
  request/wall-clock budgets, rate limiting, concurrency limit, connect/read and
  total timeouts, streamed body cap, header cap, cancellation.
- 287 automated tests on Linux (242 unit, 37 integration, 8 cross-platform).

## 3. Not implemented

- **Discovery and checks.** No crawling, no assessment modules, no observations.
- **Verification and findings engine.** Findings table exists; nothing writes to
  it and no severity/confidence logic exists.
- **Reporting.** No JSON/Markdown/terminal report generator.
- **Native C component.** No `CMakeLists.txt`, no C source, no loader.
  `aurora version` correctly reports `libaurora.so (not built)`.
- **Assessment lifecycle.** No `assess` command, no run orchestration; scope is
  configured in `config.json`, not yet persisted per assessment in
  `scope_targets`.
- **Request methods beyond `GET`/`HEAD`.** No bodies, forms, cookies or
  authentication flows.
- **Log rotation.** Single log file per workspace; Python's
  `RotatingFileHandler` is avoided for now because renaming an open file is
  fragile on Windows.

## 4. Protections: verified vs. unverified

| Protection | Reality |
|---|---|
| DNS pinning / rebinding | **Implemented and tested on Linux.** The request connects to the validated literal; server-side tests confirm peer address, `Host`, SNI and that a changed resolver answer cannot redirect the connection. See `docs/NETWORK-BOUNDARY.md`. Not executed on Windows; IPv6 not exercised over a socket. |
| Redirect scope bypass | Manual hop-by-hop processing; out-of-scope, credential-bearing and non-HTTP redirect targets are refused with no request sent (tested). |
| Response-size limit | Streamed and enforced at `max_response_bytes` (tested at 1 KiB against a 20 KB response). |
| Header-size limit | Enforced **after** HTTPX parses the header block; it bounds accepted responses, not library parser memory. |
| Rate / concurrency / budget limits | Enforced in-process (tested). Two AURORA processes pointed at the same target each get their own budget. |
| Cancellation | In-flight request is cancelled promptly (tested: < 0.4 s against a 0.8 s response). |
| Encrypted storage | **Not implemented.** The SQLite file is plaintext; workspace permissions are the only control. |
| Windows ACLs | **Not implemented.** `chmod`-style hardening is POSIX-only and skipped on Windows by design. |
| Secret redaction completeness | Pattern-based (auth headers, cookies, URL userinfo, common token query keys). A credential in an unusual field will not be caught. |
| Proxies | Not supported; `trust_env=False` means environment proxy variables are ignored rather than silently routing traffic outside the scope path. |
| HTTP/2 | Disabled. |

## 5. Testing gaps

**Which tests skipped where.** On Linux (`os.name != "nt"`, `127.0.0.2`
bindable) the suite reports `287 passed`, `0 skipped`. Exactly three tests can
skip on other platforms, for stated reasons:

| Test | Skips when | Reason |
|---|---|---|
| `tests/unit/test_paths.py::test_ensure_layout_restricts_permissions` | Windows | POSIX mode bits are not meaningful on Windows |
| `tests/unit/test_config.py::test_config_file_is_private` | Windows | Same |
| `tests/integration/test_pinning_experiment.py::test_a_rebinding_answer_cannot_redirect_the_connection` | `127.0.0.2` not bindable | The experiment needs a second loopback server on the same port |

The remaining gaps:

- No Windows execution; CI authored but never run.
- The ping/pinning rebinding test skips where `127.0.0.2` cannot be bound.
- No IPv6 socket test, no HTTP/2 test, no proxy test.
- No fuzzing. Native fuzzing is not applicable until Phase 5.
- The Rich/colour output path is not exercised in CI: `pytest` captures output,
  which is not a TTY, so only the plain writer path runs.
- Terminal detection is tested with synthetic streams; no legacy Windows console
  (code page 437/1252) was executed.
- Cross-platform tests validate the *rules*, not a second operating system.
- Only schema v1 exists, so no migration-from-older-version test is possible yet.
- Concurrent access to one workspace from two processes is not tested. SQLite
  uses a 5 s busy timeout and WAL where available.
- TLS is exercised only with a throwaway self-signed fixture CA; no public CA,
  client certificates or OCSP/CRL behaviour is covered.

## 6. Environmental restrictions in the development environment

- No CMake and no Clang were installed (`gcc 13.3.0` and `make 4.3` were
  present), so the native build system cannot be validated here.
- No GitHub credentials were available, so CI workflows were authored but never
  executed, and no push to the remote repository was performed.
- No Windows host was available.
- The `pin.test` certificate under `tests/fixtures/certs/` was generated with
  OpenSSL 3.0.13 and is valid until 2036-11-10.

## 7. Known technical debt

- `aurora version` opens the database read/write to read `PRAGMA user_version`;
  a read-only connection would be preferable.
- Log level from `config.json` is not applied automatically; only `--log-level`
  is honoured at runtime.
- Scope exists only in configuration; the `scope_targets` table is unused until
  the assessment lifecycle lands. The two representations must be reconciled
  with a migration before `assess` exists.
- Only the first authorised address is used; there is no retry against a second
  validated address, and no connection-level retry at all (`retries=0`).
- One connection per hop is a deliberate correctness trade-off; revisit only
  with measurements.
- Redirect handling does not implement method rewriting (irrelevant while only
  `GET`/`HEAD` exist) and ignores `Refresh` headers deliberately.
- An `AuroraClient` belongs to one event loop (it owns an `asyncio.Semaphore`
  and a rate-limiter lock); it is not safe to share across `asyncio.run` calls.
