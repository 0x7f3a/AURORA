# Connection boundary experiment

This document records what was measured about AURORA's connection boundary, on
which platform, and what remains unverified. It exists because validating a DNS
answer and then letting the HTTP stack resolve the name again is the standard way
"SSRF protection" turns out to be decorative.

- **Date:** 2026-11-13
- **Host:** Ubuntu 24.04.5 LTS, x86_64, Python 3.12.3
- **HTTP stack:** HTTPX 0.28.1 → httpcore 1.0.9 → AnyIO
- **Run with:** `python -m pytest tests/integration/test_pinning_experiment.py -v`
- **Result:** all experiments passed on Linux; Windows not executed.

---

## 1. Design under test

```text
logical URL            https://pin.test:8443/admin
        │
        ├─ normalise ────────────────────────► https://pin.test:8443/admin
        ├─ scope decision ───────────────────► allowed, allow_private=True
        ├─ resolve once ─────────────────────► 127.0.0.1
        ├─ address policy ───────────────────► loopback allowed by that rule
        └─ pin ──► connect to   https://127.0.0.1:8443/admin
                   extensions: sni_hostname = pin.test
                   header:    Host: pin.test:8443
```

Pinning is implemented in `src/aurora/net/pinning.py`; the client
(`src/aurora/net/client.py`) never passes a hostname to the socket layer after
validation. httpcore connects to the origin host of the rewritten URL (the IP
literal) and uses the `sni_hostname` request extension for the TLS handshake.

## 2. Experiments and observations

Every observation below is read from the **server side** of a real socket
(`tests/fixtures/http_server.py` records the peer address, the received `Host`
header, the SNI name presented during the handshake and the request log).

| # | Experiment | Observation |
|---|---|---|
| 1 | Hostname `pin.test` resolves to `127.0.0.1`; request `http://pin.test:<port>/echo` | Server saw peer `127.0.0.1`, `Host: pin.test:<port>`; resolver called exactly once. |
| 2 | DNS rebinding: resolver answers `127.0.0.1` on the validation call and `127.0.0.2` on any later call, with a second server listening on `127.0.0.2:<same port>` | Request was served by the validated server; the `127.0.0.2` server recorded **zero** requests; resolver called exactly once. |
| 3 | TLS: fixture certificate is valid for `pin.test` only, server bound to `127.0.0.1` | Handshake presented SNI `pin.test`; server saw peer `127.0.0.1`; request succeeded with the fixture CA. |
| 4 | TLS verification is really active | Same request with the system trust store (which does not contain the fixture CA) fails with a transport error. |
| 5 | Verification uses the original hostname, not the literal | The certificate has no SAN for `127.0.0.1`; success in experiment 3 therefore requires verification against `pin.test`. |
| 6 | Address literal avoids resolution entirely | `http://127.0.0.1:<port>/` completes with a resolver double that raises if called; the literal still passes the address policy. |
| 7 | Private-network permission applies to hostnames too | `pin.test → 127.0.0.1` with a rule lacking `allow_private` is refused before any connection (`AddressNotAllowed`), server log empty. |

## 3. What this establishes

- The TCP connection goes to the address that was validated, not to a second
  resolution of the name (experiments 1, 2, 6).
- The original hostname is preserved for the HTTP `Host` header, including a
  non-default port (experiments 1, 3).
- The original hostname is preserved for TLS SNI and certificate verification,
  and verification is not disabled by pinning (experiments 3–5).
- Redirect hops are not exempt: each hop is re-normalised, re-evaluated and
  re-pinned (covered by `tests/integration/test_net_scope.py`).

## 4. What this does **not** establish

| Gap | Detail |
|---|---|
| Windows execution | Not run. The rebinding experiment needs `127.0.0.2`; on Windows the test **skips** with that reason instead of silently passing. |
| IPv6 over a socket | Bracketing and URL construction are unit-tested; no IPv6 fixture connection was executed. |
| HTTP/2 | Disabled (`http2=False`). Multiplexed streams are not exercised. |
| Proxies | `trust_env=False` and no proxy support. An operator behind a mandatory proxy cannot use the transport yet. |
| TLS beyond a self-signed fixture | No public-CA, client-certificate or pinning-by-public-key scenarios. |
| Address failover | Only the first authorised address is used; there is no retry against a second validated address. |
| Connection reuse | Disabled deliberately (one connection per hop). A persistent pooled connection cannot outlive a scope decision, but the cost is a handshake per request. |
| Header size limit | Enforced after HTTPX has parsed the header block; it bounds what AURORA accepts, not library parser memory. |
| Dependency semantics | Pinning relies on httpcore's `sni_hostname` extension and on connecting to the URL origin. Both are asserted by tests, so an upgrade that changes them fails the suite rather than degrading silently. |

## 5. Interpretation

On Linux, with this stack, DNS rebinding through a second resolution is not
possible: there is no second resolution. The remaining exposure is the general
one of any HTTP client — a server choosing malicious response content, or an
operator authorising a target that is not what they think it is. Both are
outside the connection boundary and are handled (or not) elsewhere.
