"""URL normalisation for scope decisions and pinning.

Scope must compare apples to apples. Before any policy decision, a URL is
reduced to a canonical form:

* scheme lower-cased and restricted to ``http``/``https``;
* host IDNA-encoded, lower-cased and canonicalised (IP literals included);
* default ports made explicit internally, and omitted from emitted URLs;
* dot segments resolved so ``/admin/../public`` cannot masquerade as ``/admin``;
* fragments dropped, query preserved verbatim;
* ambiguous percent-encoding (encoded dot, slash, backslash or NUL) refused
  outright rather than guessed at;
* percent-escapes that stand for unreserved characters are decoded (RFC 3986
  section 6.2.2.2), so ``/admin`` and ``/%61dmin`` are the same path and cannot
  be distinguished by a scope rule;
* embedded credentials and backslashes refused: different HTTP stacks disagree
  about them, and a disagreement is exactly how scope checks get bypassed.

The normalised form is what scope rules match and what the transport builds its
requests from.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from aurora.errors import UrlError

__all__ = [
    "NormalizedURL",
    "normalize_host",
    "normalize_path_prefix",
    "normalize_url",
    "path_prefix_matches",
]

_DEFAULT_PORTS = {"http": 80, "https": 443}
_FORBIDDEN_CHARACTERS = re.compile(r"[\x00-\x20\x7f]")
_AMBIGUOUS_ENCODING = re.compile(r"(?i)%(2e|2f|5c|00)")
_NUMERIC_HOST = re.compile(r"^[0-9.]+$")
_HEX_LABEL = re.compile(r"(?i)^0x[0-9a-f]+$")
_PERCENT_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")
_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)


def normalize_host(raw: str) -> str:
    """Canonicalise a host name or IP literal.

    Wildcards are *not* accepted here; scope rules handle them explicitly so a
    wildcard can never leak into a request URL.
    """

    candidate = raw.strip().rstrip(".").lower()
    if not candidate:
        raise UrlError("host is empty")
    if "*" in candidate:
        raise UrlError(f"host {raw!r} contains a wildcard, which is only valid in scope rules")
    if "%" in candidate:
        raise UrlError(f"host {raw!r} contains a zone or percent-encoding, which is not supported")
    if any(character in candidate for character in " /\\@?#[]"):
        raise UrlError(f"host {raw!r} contains characters that are not valid in a host name")

    if ":" in candidate and not candidate.startswith("["):
        # A colon outside an IPv6 literal is never valid in a host name; the
        # hostname property has already stripped a legitimate port.
        try:
            ipaddress.IPv6Address(candidate)
        except ValueError:
            raise UrlError(f"host {raw!r} is not a valid IPv6 literal") from None

    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        # Non-canonical numeric forms (127.1, 0177.0.0.1, 2130706433) resolve
        # differently across platforms and are a classic scope bypass.
        if _NUMERIC_HOST.match(candidate):
            raise UrlError(
                f"host {raw!r} looks like a non-canonical IPv4 address and is refused"
            ) from None
        if ".." in candidate or candidate.startswith(".") or candidate.endswith("."):
            raise UrlError(f"host {raw!r} contains an empty label")
        if any(_HEX_LABEL.match(label) for label in candidate.split(".")):
            raise UrlError(
                f"host {raw!r} contains a hexadecimal label, which some resolvers treat as an address"
            )
        try:
            candidate = candidate.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise UrlError(f"host {raw!r} is not a valid DNS name: {exc}") from exc
        if not candidate:
            raise UrlError(f"host {raw!r} is not a valid DNS name")
    else:
        if "%" in str(address):
            raise UrlError(f"host {raw!r} uses an IPv6 zone identifier, which is not supported")
        candidate = str(address)

    return candidate


def _remove_dot_segments(path: str) -> str:
    """RFC 3986 section 5.2.4, operating on a path with no query.

    Implemented as the specification's state machine rather than as a
    split/filter/join: the join loses empty segments in ways the algorithm does
    not (``//a/..`` is ``//``, not ``/``), and a path that is normalised
    differently from the one the server sees is exactly the disagreement scope
    checking exists to prevent.
    """

    remaining = path
    output = ""
    while remaining:
        if remaining.startswith("../"):
            remaining = remaining[3:]
        elif remaining.startswith("./"):
            remaining = remaining[2:]
        elif remaining.startswith("/./"):
            remaining = "/" + remaining[3:]
        elif remaining == "/.":
            remaining = "/"
        elif remaining.startswith("/../"):
            remaining = "/" + remaining[4:]
            output = output[: output.rfind("/")] if "/" in output else ""
        elif remaining == "/..":
            remaining = "/"
            output = output[: output.rfind("/")] if "/" in output else ""
        elif remaining in (".", ".."):
            remaining = ""
        else:
            start = 1 if remaining.startswith("/") else 0
            segment_end = remaining.find("/", start)
            if segment_end == -1:
                output += remaining
                remaining = ""
            else:
                output += remaining[:segment_end]
                remaining = remaining[segment_end:]

    return output if output.startswith("/") else "/" + output


def _decode_unreserved(text: str) -> str:
    """Decode percent-escapes that stand for unreserved characters.

    RFC 3986 section 6.2.2.2 makes these equivalent to the literal character, so
    ``/%61dmin`` and ``/admin`` address the same resource. Leaving them distinct
    would let a percent-encoded path walk past an exclusion rule. Reserved
    escapes (``%2f``, ``%3f``, ...) are left alone: the ambiguous ones are
    refused outright before this runs.
    """

    def replace(match: re.Match[str]) -> str:
        character = chr(int(match.group(1), 16))
        return character if character in _UNRESERVED else match.group(0)

    return _PERCENT_ESCAPE.sub(replace, text)


def normalize_path_prefix(raw: str) -> str:
    """Canonicalise a scope path prefix."""

    candidate = raw.strip()
    if not candidate:
        return "/"
    if _FORBIDDEN_CHARACTERS.search(candidate):
        raise UrlError(f"path prefix {raw!r} contains whitespace or control characters")
    if _AMBIGUOUS_ENCODING.search(candidate):
        raise UrlError(f"path prefix {raw!r} contains ambiguous percent-encoding")
    if "\\" in candidate:
        raise UrlError(f"path prefix {raw!r} contains a backslash")
    if not candidate.startswith("/"):
        raise UrlError(f"path prefix {raw!r} must start with '/'")
    return _remove_dot_segments(_decode_unreserved(candidate))


def path_prefix_matches(prefix: str, path: str) -> bool:
    """Whether *path* falls under *prefix* on a segment boundary."""

    if prefix == "/":
        return True
    trimmed = prefix.rstrip("/")
    if not trimmed:
        return True
    return path == trimmed or path.startswith(trimmed + "/")


@dataclass(frozen=True, slots=True)
class NormalizedURL:
    """A canonical URL. Ports are always explicit in :attr:`origin`."""

    scheme: str
    host: str
    port: int
    path: str
    query: str = ""

    @property
    def default_port(self) -> int:
        return _DEFAULT_PORTS[self.scheme]

    @property
    def is_default_port(self) -> bool:
        return self.port == self.default_port

    @property
    def bracket_host(self) -> str:
        return f"[{self.host}]" if ":" in self.host else self.host

    @property
    def host_header(self) -> str:
        """Value for the HTTP ``Host`` header (default port omitted)."""

        return self.bracket_host if self.is_default_port else f"{self.bracket_host}:{self.port}"

    @property
    def origin(self) -> str:
        """``scheme://host:port`` with the port always present, for comparison."""

        return f"{self.scheme}://{self.bracket_host}:{self.port}"

    def to_url(self) -> str:
        """Re-emit the canonical URL (default port omitted)."""

        base = f"{self.scheme}://{self.host_header}{self.path}"
        return f"{base}?{self.query}" if self.query else base

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.to_url()


def normalize_url(raw: str, *, base: str | None = None) -> NormalizedURL:
    """Parse and canonicalise *raw*, resolving it against *base* when relative."""

    if not isinstance(raw, str):
        raise UrlError(f"URL must be a string, got {type(raw).__name__}")
    candidate = raw.strip()
    if not candidate:
        raise UrlError("URL is empty")
    if _FORBIDDEN_CHARACTERS.search(candidate):
        raise UrlError("URL contains whitespace or control characters")
    if "\\" in candidate:
        raise UrlError(
            "URL contains a backslash; HTTP stacks interpret it differently, so it is refused"
        )

    if base is not None:
        try:
            candidate = urljoin(base, candidate)
        except ValueError as exc:
            raise UrlError(f"cannot resolve relative URL {raw!r}: {exc}") from exc

    try:
        parts = urlsplit(candidate)
    except ValueError as exc:
        raise UrlError(f"cannot parse URL {raw!r}: {exc}") from exc

    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        shown = parts.scheme or "<none>"
        raise UrlError(f"unsupported URL scheme {shown!r}; only http and https are allowed")

    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise UrlError("URLs with embedded credentials are not allowed")

    if not parts.hostname:
        raise UrlError(f"URL {raw!r} has no host")

    host = normalize_host(parts.hostname)

    try:
        explicit_port = parts.port
    except ValueError as exc:
        raise UrlError(f"URL {raw!r} has an invalid port: {exc}") from exc
    port = _DEFAULT_PORTS[scheme] if explicit_port is None else explicit_port
    if not 1 <= port <= 65535:
        raise UrlError(f"URL {raw!r} has a port outside 1-65535")

    path = parts.path or "/"
    if _AMBIGUOUS_ENCODING.search(path):
        raise UrlError(
            "URL path contains ambiguous percent-encoding (encoded dot, slash or NUL)"
        )
    path = _remove_dot_segments(_decode_unreserved(path))

    return NormalizedURL(scheme=scheme, host=host, port=port, path=path, query=parts.query)
