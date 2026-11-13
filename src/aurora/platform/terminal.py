"""Terminal capability detection.

Unicode and colour support are detected rather than assumed, because AURORA has
to run in Windows PowerShell, ``cmd.exe`` with a legacy code page, over SSH in a
``TERM=dumb`` session, and in CI where stdout is a pipe. When the terminal
cannot represent the banner artwork the CLI switches to its ASCII rendering
instead of emitting replacement characters or raising ``UnicodeEncodeError``.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from typing import Mapping, TextIO

__all__ = ["UNICODE_PROBE", "TerminalInfo"]

#: Characters used by the banner: block art, box drawing, and the middle dot.
UNICODE_PROBE = "\u2588\u2557\u2554\u2550\u255d\u2551\u00b7\u2501\u2500"

_MIN_WIDTH = 20
_FALLBACK_SIZE = (80, 24)


def _can_encode(text: str, encoding: str) -> bool:
    try:
        text.encode(encoding, errors="strict")
    except (LookupError, UnicodeEncodeError):
        return False
    return True


@dataclass(frozen=True, slots=True)
class TerminalInfo:
    """What the current output stream can render."""

    width: int
    is_tty: bool
    encoding: str
    unicode_ok: bool
    color_ok: bool

    @classmethod
    def detect(
        cls,
        *,
        stream: TextIO | None = None,
        environ: Mapping[str, str] | None = None,
        ascii_only: bool = False,
        no_color: bool = False,
    ) -> "TerminalInfo":
        """Detect capabilities of *stream* (defaults to ``sys.stdout``)."""

        out = stream if stream is not None else sys.stdout
        env = os.environ if environ is None else environ

        encoding = getattr(out, "encoding", None) or "utf-8"
        is_tty = bool(getattr(out, "isatty", lambda: False)())
        width = max(_MIN_WIDTH, shutil.get_terminal_size(_FALLBACK_SIZE).columns)

        unicode_ok = not ascii_only and _can_encode(UNICODE_PROBE, encoding)

        color_ok = (
            not no_color
            and is_tty
            and not env.get("NO_COLOR", "").strip()
            and env.get("TERM", "").strip().lower() != "dumb"
        )

        return cls(
            width=width,
            is_tty=is_tty,
            encoding=encoding,
            unicode_ok=unicode_ok,
            color_ok=color_ok,
        )

    def can_render(self, text: str) -> bool:
        """Whether *text* survives a strict encode to the terminal encoding."""

        return _can_encode(text, self.encoding)
