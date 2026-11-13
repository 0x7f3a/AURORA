# AURORA Architecture

Version: `0.1.0-dev`
Status: milestone 1 — Python foundation implemented; assessment engines planned.

This document describes the architecture AURORA is being built against, marks
what exists today, and records the trade-offs behind the important decisions.
Anything labelled *planned* is design intent, not code.

---

## 1. Design position

AURORA is an assessment **framework**, not a scanner that emits a score. Three
properties drive the design:

1. **Evidence before assertion.** A check produces observations; a finding only
   exists once an observation has been interpreted and verified. A missing
   header, a banner, a reflected parameter or an unusual status code is an
   observation, never a vulnerability by itself.
2. **Bounded behaviour.** Every network action runs inside an explicit scope,
   with rate, concurrency, size and time limits that are part of the validated
   configuration. There is no "run everything" mode.
3. **Honest reporting.** Reports must distinguish a completed check from a
   check that could not run, from one that does not exist. The CLI follows the
   same rule: unimplemented commands are not registered at all.

Non-goals for 0.1: denial-of-service testing, destructive payloads,
persistence, credential theft, evasion/stealth, exploitation automation, a GUI.

---

## 2. Layers

```text
            operator
               │
        ┌──────▼───────┐
        │     CLI      │  argument parsing, banner, console, exit codes
        └──────┬───────┘
               │  config + paths
   ┌───────────▼────────────┐
   │  config / platform /   │  validated limits, host capabilities,
   │  observability / paths │  redacted logging, workspace layout
   └───────────┬────────────┘
               │
   ┌───────────▼────────────┐        (planned, Phase 4)
   │  scope  ──►  net       │  normalise → authorise → send → bound
   └───────────┬────────────┘
               │  responses
   ┌───────────▼────────────┐        (planned, Phase 6)
   │  discovery ──► checks  │  assets, observations
   └───────────┬────────────┘
               │  observations
   ┌───────────▼────────────┐        (planned, Phase 7)
   │  verification ──►      │  CONFIRMED / POTENTIAL / INCONCLUSIVE / REJECTED
   │  findings              │
   └───────────┬────────────┘
               │
   ┌───────────▼────────────┐
   │  storage  ──► reporting│  SQLite → JSON / Markdown / terminal
   └────────────────────────┘
```

Dependencies point downward only. `storage` does not know about `cli`;
`cli` does not perform HTTP. This keeps modules testable in isolation and lets
the reporting layer be exercised without a network.

---

## 3. Module responsibilities

| Package | Responsibility | State |
|---|---|---|
| `aurora.cli` | Argument parsing, banner rendering, console output, exit codes, command dispatch | Implemented |
| `aurora.config` | Pydantic models for limits/identity; atomic JSON load/save with precise validation errors | Implemented |
| `aurora.platform` | OS/architecture detection, native library naming, terminal capability detection | Implemented |
| `aurora.observability` | UTC logging with redaction on every handler; header/URL/text redaction helpers | Implemented |
| `aurora.storage` | SQLite connections, pragmas, versioned migrations, assessment repository | Implemented (assessments only) |
| `aurora.paths` | Cross-platform workspace resolution (`AURORA_HOME`, `%APPDATA%`, XDG) | Implemented |
| `aurora.scope` | URL normalisation and authorisation decisions | Planned (Phase 4) |
| `aurora.net` | HTTPX client, manual redirect chain, limits, cancellation | Planned (Phase 4) |
| `aurora.native` | Safe loading and ABI validation of the C component | Planned (Phase 5) |
| `aurora.discovery` | Bounded asset discovery and attack-surface inventory | Planned (Phase 6) |
| `aurora.checks` | Individual checks that emit observations | Planned (Phase 6) |
| `aurora.verification` | Evidence evaluation, severity and confidence assignment | Planned (Phase 7) |
| `aurora.findings` | Finding model and identifiers | Planned (Phase 7) |
| `aurora.reporting` | JSON, Markdown and terminal reports | Planned (Phase 7) |

No package is created before it has a responsibility and a testable interface.
Empty placeholder modules are deliberately absent.

---

## 4. Key dependency decisions

| Decision | Reason | Trade-off |
|---|---|---|
| **HTTPX owns all HTTP** | TLS, HTTP/2, connection pooling and protocol correctness are solved problems; a bespoke stack would add risk, not value | We inherit HTTPX behaviour and must verify our scope/redirect wrapping at the transport boundary |
| **Pydantic for configuration** | Bounds are declared next to the field, produce path-precise errors, and reject unknown keys (`extra="forbid"`) | One more runtime dependency; model definitions must stay in sync with the transport |
| **`sqlite3` (stdlib)** | No extra dependency, transactional integrity, works identically on both platforms | Synchronous API; the async engine will use one connection per worker rather than a shared connection |
| **Rich for presentation only** | Good terminal rendering without turning the CLI into a TUI | Output must still work with Rich absent/disabled, hence the plain writer path |
| **BeautifulSoup4 for HTML** | Tolerant parsing of real-world markup | Not used until discovery exists; no parser differential is claimed |
| **`asyncio`** | Cancellation and bounded concurrency | Windows uses the proactor loop since 3.8; the transport must avoid selectors-only assumptions |

`httpx` and `beautifulsoup4` are declared dependencies because they belong to
the approved stack; they are not imported by the current milestone. Importing
them anyway would be dead code.

---

## 5. Native C component

### The problem it must solve

The strongest candidate responsibility is **differential HTTP header parsing**.
Request smuggling and header-confusion bugs live in parser differences: two
independent parsers disagreeing about how a request or response is framed is
itself the signal. AURORA will parse header blocks twice — once with HTTPX/`h11`
(the library view) and once with a small, strict, allocation-free C parser — and
record any disagreement as an observation for verification.

Why that is not decoration:

- it reasons about **raw bytes**, which the Python-level response model has
  already normalised away;
- it is a bounded, pure function (`bytes in → fixed struct out`), which is the
  only kind of C this project should contain;
- a disagreement is genuine evidence, not a heuristic.

### Deferral criteria (binding)

The C component ships only if all of these hold:

1. The Python reference implementation of the same parser exists first and is
   tested against malformed input.
2. The C and Python parsers agree on a shared corpus, including truncated,
   duplicated and whitespace-obfuscated headers. Strict validation is never
   relaxed to force agreement.
3. Benchmarks show a measurable benefit, or a concrete safety benefit is
   documented. "Looks more advanced" is not a justification.
4. Fuzz/ASan/UBSan runs show no memory or undefined-behaviour findings.

If those cannot be demonstrated, the component is deferred and the framework
keeps its Python reference parser. That outcome is acceptable and will be
reported as such rather than shipping C that exists only for appearance.

### ABI rules for when it lands

- C11, fixed-width integer types; no `int`/`long` in the public ABI.
- `AURORA_NATIVE_ABI_VERSION` and a caller-initialised `struct_size` are
  validated before any other field is read.
- Caller-owned buffers with explicit length in/out; the library never returns
  memory the caller must free across runtimes (no cross-runtime `malloc`/`free`).
- Symbol visibility explicit on both platforms
  (`__declspec(dllexport)` / `__attribute__((visibility("default")))`).
- Loading uses an absolute, validated path. Never the current working directory,
  never `PATH`/`DLL_LOAD_LIBRARY_SEARCH_*` defaults that include CWD.
- Mismatch between library ABI and Python expectation disables the native path
  and logs why; it never silently falls back to "close enough".

---

## 6. Scope and network boundaries (planned, Phase 4)

Scope is a first-class object, not a string check:

```text
scope target := (kind: include|exclude, scheme, host, port, path_prefix)
```

Rules the transport must satisfy:

1. **Normalise first.** Lower-case scheme/host, IDNA-encode the host, strip
   default ports, resolve dot segments, reject credentials in URLs.
2. **Authorise each hop.** Redirects are followed manually: receive, resolve the
   `Location`, validate scheme/host/port/path against scope, apply connection
   policy, then continue. Automatic redirect following is never enabled, because
   it would let the server choose the next destination.
3. **Validate the address actually used.** A hostname may resolve to addresses
   outside the authorised lab range. Private ranges are **not** blocked globally
   — explicitly authorised local labs need them — but an address outside the
   declared allowlist must not be contacted.
4. **Enforce limits.** Connect/read/total timeouts, `max_response_bytes`,
   `max_header_bytes`, `max_redirects`, `requests_per_second`, `max_concurrency`,
   and a hard request budget per run.
5. **Cancel deterministically.** Cancellation must stop in-flight requests, not
   merely stop reading from them.

### DNS pinning: an open, unproven item

Validating a DNS answer and then letting the transport resolve the name again
leaves a time-of-check/time-of-use window. Correct pinning requires the
connection to use the validated address while the original hostname is preserved
for the `Host` header and TLS SNI. HTTPX/`httpcore` allows a custom network
backend, but **AURORA has not yet proven that the pinned address is the address
actually connected to.**

Until an integration test demonstrates that behaviour against a local fixture
that changes its DNS answer mid-run, AURORA will:

- validate the resolved address set before connecting,
- document the residual TOCTOU window as an unverified protection,
- and disable any feature whose safety depends on pinning.

No documentation or report will claim rebinding protection before that test
exists.

---

## 7. Findings model

Two separate axes, never collapsed into one score:

| Field | Values |
|---|---|
| `verification` | `CONFIRMED`, `POTENTIAL`, `INCONCLUSIVE`, `REJECTED` |
| `severity` | `info`, `low`, `medium`, `high`, `critical` |
| `confidence` | `low`, `medium`, `high` |

Severity answers "how bad if true"; confidence answers "how sure are we".
A `CONFIRMED` finding may still be `low` severity. An `INCONCLUSIVE`
observation can be retained without ever becoming a finding. The database
enforces the enumerations with `CHECK` constraints so an invalid state cannot be
persisted even if application code regresses.

Every finding carries: public ID, title, description, affected asset, evidence
references, technical explanation, impact, remediation, limitations, timestamps.

---

## 8. Data model (schema v1)

```text
assessments ──┬── scope_targets
              ├── assets ──┬── observations ── evidence
              │            └── findings ────── evidence
              ├── module_runs
              └── errors
```

- Cascading deletes: children are removed with their assessment.
- `assets` are unique per `(assessment, url)`.
- `module_runs.status` distinguishes `completed`, `skipped`, `failed`,
  `unavailable`, `not_implemented` — the report's "what did not run" section is
  fed from this table, not guessed.
- Evidence must reference either a finding or an observation (table-level
  `CHECK`).

Migration policy: append-only, forward-only, tracked in `PRAGMA user_version`.
A database written by a newer build is refused rather than downgraded.

---

## 9. Cross-platform strategy

| Concern | Approach |
|---|---|
| Paths | `pathlib`, no hardcoded separators or `/tmp` |
| Workspace | `AURORA_HOME` → platform default; `--home` for isolation |
| Native library | `libaurora.so` / `aurora.dll` / `libaurora.dylib`; absolute validated paths; no CWD search |
| Console | encoding probed with a strict encode of the banner glyphs; ASCII rendering and plain writer fall back cleanly |
| Colour | TTY + `NO_COLOR` + `TERM=dumb` honoured; `--no-color` forces plain |
| Filesystem permissions | POSIX `0700`/`0600` best effort; Windows documents the ACL difference instead of pretending chmod works |
| SQLite | Same schema and pragmas; WAL attempted, silently downgraded where the filesystem refuses it |
| asyncio | No selectors-only assumptions; cancellation tested on both event loops when the async engine lands |
| CI | `ubuntu-latest` and `windows-latest` jobs run the same suite |

`PlatformInfo` is a pure value object so Windows and Linux naming rules are
tested on any host; the Windows CI job is what proves the host behaviour.

---

## 10. Testing strategy

| Level | What it proves |
|---|---|
| Unit | Validation, path rules, terminal detection, banner variants, redaction, migrations, constraints |
| Integration (subprocess) | `python -m aurora` under an ASCII-only stdout encoding; init → version workflow; no traceback escapes |
| Local HTTP fixtures (Phase 4) | Redirect chains, scope rejection, size/timeout enforcement, cancellation |
| Native parity (Phase 5) | C and Python parsers agree on a shared malformed-input corpus |
| CI matrix | Ubuntu and Windows execute the same commands |

Rules: tests are never weakened to make implementations agree; a check that
cannot run is reported as `SKIPPED` with a reason; network tests use local
fixtures only.

---

## 11. Extension point: an assessment check (planned interface)

A check will be a small object with a declared identity and a declared cost:

```python
class Check(Protocol):
    check_id: str          # stable, e.g. "HDR-001"
    title: str
    requires: frozenset[str]   # capabilities, e.g. {"http"}
    def run(self, context: AssessmentContext) -> list[Observation]: ...
```

A check returns observations only. It cannot write findings and cannot label
severity — that belongs to verification. This is the structural guarantee that
keeps a check from inflating its own importance.
