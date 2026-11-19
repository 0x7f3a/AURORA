"""A small, recording HTTP server used by the transport integration tests.

Everything the tests assert about connection behaviour is observed *here*, on
the server side of a real socket: which peer address connected, what ``Host``
header arrived, which SNI name was presented, how many requests were made and
how many ran concurrently. Nothing is inferred from client-side declarations.
"""

from __future__ import annotations

import json
import ssl
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import parse_qs, urlsplit

__all__ = ["CERT_DIR", "FixtureServer", "RequestRecord", "server_tls_context"]

CERT_DIR = Path(__file__).resolve().parent / "certs"


def server_tls_context() -> ssl.SSLContext:
    """Server context for the throwaway ``pin.test`` certificate."""

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(
        certfile=str(CERT_DIR / "pin-test-cert.pem"),
        keyfile=str(CERT_DIR / "pin-test-key.pem"),
    )
    return context


@dataclass(frozen=True, slots=True)
class RequestRecord:
    method: str
    path: str
    host: str | None
    user_agent: str | None
    peer: tuple[str, int]
    sni: str | None


class FixtureState:
    """Thread-safe observations shared with the test body."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests: list[RequestRecord] = []
        self.active = 0
        self.max_active = 0
        self.sni_names: list[str | None] = []

    def record(self, record: RequestRecord) -> None:
        with self._lock:
            self.requests.append(record)

    def enter(self) -> None:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)

    def leave(self) -> None:
        with self._lock:
            self.active -= 1

    def record_sni(self, server_name: str | None) -> None:
        with self._lock:
            self.sni_names.append(server_name)

    @property
    def paths(self) -> list[str]:
        return [record.path for record in self.requests]

    def reset(self) -> None:
        with self._lock:
            self.requests.clear()
            self.sni_names.clear()
            self.max_active = 0


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AuroraFixture/1.0"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib API
        pass

    def do_GET(self) -> None:  # noqa: N802 - stdlib API
        self._dispatch(body_allowed=True)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib API
        self._dispatch(body_allowed=False)

    def _dispatch(self, *, body_allowed: bool) -> None:
        state: FixtureState = self.server.state  # type: ignore[attr-defined]
        sni = getattr(self.connection, "_aurora_sni", None)
        if sni is None and state.sni_names:
            sni = state.sni_names[-1]
        state.record(
            RequestRecord(
                method=self.command,
                path=self.path,
                host=self.headers.get("Host"),
                user_agent=self.headers.get("User-Agent"),
                peer=self.client_address,
                sni=sni,
            )
        )
        state.enter()
        try:
            self._route(body_allowed=body_allowed, sni=sni)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            state.leave()

    def _route(self, *, body_allowed: bool, sni: str | None) -> None:
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)
        route = parsed.path

        if route == "/ok":
            self._send(200, b"ok")
        elif route == "/echo":
            payload = json.dumps(
                {
                    "host": self.headers.get("Host"),
                    "path": self.path,
                    "method": self.command,
                    "sni": sni,
                    "server": self.headers.get("Server"),
                }
            ).encode("utf-8")
            self._send(200, payload, content_type="application/json")
        elif route == "/redirect":
            self._send(302, b"", extra=(("Location", query["to"][0]),))
        elif route == "/redirect-loop":
            self._send(302, b"", extra=(("Location", "/redirect-loop"),))
        elif route == "/big":
            self._stream_bytes(int(query.get("size", ["65536"])[0]), body_allowed)
        elif route == "/slow":
            time.sleep(float(query.get("delay", ["0.25"])[0]))
            self._send(200, b"slow")
        elif route == "/huge-header":
            extra = tuple((f"X-Pad-{index}", "p" * 256) for index in range(8))
            self._send(200, b"ok", extra=extra)
        elif route == "/status":
            self._send(int(query.get("code", ["200"])[0]), b"", send_body=False)
        elif route == "/dup-headers":
            self._send(
                200,
                b"ok",
                extra=(("Set-Cookie", "a=1; Path=/"), ("Set-Cookie", "b=2; Path=/")),
            )
        elif route == "/truncated-body":
            self._truncated_body(body_allowed)
        elif route == "/stall-body":
            self._stall_body(float(query.get("delay", ["0.5"])[0]), body_allowed)
        else:
            self._send(404, b"not found")

    def _send(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str = "text/plain; charset=utf-8",
        extra: Sequence[tuple[str, str]] = (),
        send_body: bool = True,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        for name, value in extra:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body and self.command != "HEAD" and body:
            self.wfile.write(body)

    def _truncated_body(self, body_allowed: bool) -> None:
        """Promise a long body, send a short one, then drop the connection."""

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "100")
        self.end_headers()
        if self.command != "HEAD" and body_allowed:
            self.wfile.write(b"short")
        self.close_connection = True

    def _stall_body(self, delay: float, body_allowed: bool) -> None:
        """Send the headers, then stall before any body byte arrives."""

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "100")
        self.end_headers()
        if self.command != "HEAD" and body_allowed:
            time.sleep(delay)
            self.wfile.write(b"x" * 100)

    def _stream_bytes(self, size: int, body_allowed: bool) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.end_headers()
        if self.command == "HEAD" or not body_allowed:
            return
        chunk = b"x" * 8192
        remaining = size
        while remaining > 0:
            piece = chunk[: min(len(chunk), remaining)]
            self.wfile.write(piece)
            remaining -= len(piece)


class FixtureServer:
    """A recording HTTP(S) server bound to a loopback address."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        tls_context: ssl.SSLContext | None = None,
    ) -> None:
        self.state = FixtureState()
        self._httpd = ThreadingHTTPServer((host, port), _Handler)
        self._httpd.daemon_threads = True
        self._httpd.block_on_close = False
        self._httpd.state = self.state  # type: ignore[attr-defined]

        self.host = host
        self.port = int(self._httpd.server_address[1])
        self.tls = tls_context is not None
        self._thread: threading.Thread | None = None

        if tls_context is not None:
            previous = tls_context.sni_callback

            def _capture(sslsocket, server_name, context, _previous=previous):  # noqa: ANN001
                try:
                    sslsocket._aurora_sni = server_name  # type: ignore[attr-defined]
                except AttributeError:  # pragma: no cover - stdlib SSLSocket is writable
                    pass
                self.state.record_sni(server_name)
                if _previous is not None:
                    return _previous(sslsocket, server_name, context)
                return None

            tls_context.sni_callback = _capture
            self._httpd.socket = tls_context.wrap_socket(self._httpd.socket, server_side=True)

    @property
    def base_url(self) -> str:
        scheme = "https" if self.tls else "http"
        return f"{scheme}://{self.host}:{self.port}"

    def url(self, path: str) -> str:
        if not path.startswith("/"):
            raise ValueError("fixture path must start with '/'")
        return f"{self.base_url}{path}"

    @property
    def certificate(self) -> str | None:
        return str(CERT_DIR / "pin-test-cert.pem") if self.tls else None

    def start(self) -> "FixtureServer":
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="aurora-http-fixture",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> "FixtureServer":
        return self.start()

    def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001 - protocol
        self.stop()
