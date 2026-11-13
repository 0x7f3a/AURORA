# AURORA Security Policy

## 1. Authorisation is a prerequisite

AURORA is an active testing tool. Using it against a system without written
permission is unlawful in most jurisdictions and is not a supported use.

Before a run, the operator must be able to state:

- who authorised the assessment,
- which hosts, ports and paths are in scope,
- the testing window,
- which classes of testing are permitted (safe checks only, at this stage).

Scope configuration and target allowlists are enforced by the tool (Phase 4);
they do not replace the operator's own authorisation.

## 2. What AURORA will not do

By design and by policy, AURORA 0.1 does not implement:

- denial-of-service or load testing,
- destructive requests (deletion, state corruption),
- persistence or installed implants,
- credential theft, password spraying or brute force,
- evasion, obfuscation or stealth,
- automated exploitation or destructive payload execution,
- unbounded crawling or unbounded request generation.

Requests are rate-limited, size-capped, time-bounded, and cancellable by
default. A check that cannot run inside those limits is skipped and reported as
skipped, not run unbounded.

## 3. Scope model

Private and loopback addresses are **not** blocked unconditionally: an
authorised local lab is a legitimate target. Instead the policy distinguishes:

- explicitly allowed hosts, ports and path prefixes (the scope),
- explicitly excluded entries,
- everything else — not authorised, therefore not contacted.

Every redirect hop is validated independently against the same policy. A server
must not be able to redirect the assessment out of scope.

DNS-rebinding protection (IP pinning) is **not implemented and not claimed**.
See `ARCHITECTURE.md` §6 for the design gate that must be passed before any such
claim is made.

## 4. Data handling

| Item | Current behaviour |
|---|---|
| Credentials in logs | Redacted by a logging filter on every handler (`Authorization`, cookies, URL userinfo, common token query keys) |
| Credentials in reports | No report generator exists yet; redaction helpers are ready for it |
| Workspace permissions | POSIX directories `0700`, config `0600`; Windows ACLs are **not** managed by AURORA |
| Database encryption | None. The SQLite file is plaintext at rest |
| Secrets in the database | None are stored deliberately; the schema has no credential column |
| Evidence storage | Not implemented yet; evidence hashing (`sha256`) is part of the schema |

Redaction is pattern-based and therefore incomplete. Do not paste live
credentials into a workspace you intend to share.

## 5. Threat model (current scope)

Untrusted inputs AURORA must handle safely as it grows:

1. **Target responses** — malformed headers, huge bodies, endless streams,
   redirect loops, invalid TLS. Treated as hostile bytes; parsed with size caps
   and timeouts, never `eval`'d or deserialised into objects.
2. **Target HTML** — parsed for links and text only. No script execution, no
   automatic rendering.
3. **Local files** — configuration is validated by schema; JSON parsing is
   bounded by the file being local and operator-controlled.
4. **Terminal output** — server-controlled strings are printed as data, never
   interpreted as terminal escape sequences. (Control-character filtering is
   planned with the reporting layer; it is not implemented yet, so do not pipe
   untrusted output into a terminal you cannot reset.)

## 6. Reporting a vulnerability in AURORA

Please report security issues privately through a GitHub security advisory on
the project repository rather than a public issue. Include the version
(`aurora version`), platform, configuration (with credentials removed) and a
minimal reproduction. Do not include live target data from an assessment you are
not authorised to share.

## 7. Dependency policy

Dependencies are pinned by range in `pyproject.toml` and installed from the
lockfile state documented in the installation guides. HTTP transport and TLS are
delegated to HTTPX rather than reimplemented. A dependency that cannot be
installed in an environment is reported as a limitation; it is never replaced by
an improvised local implementation.
