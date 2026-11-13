"""Output abstraction for the CLI.

Rich is used only when styled output is actually possible. When colour is
disabled or the stream is not a terminal, output goes through a plain writer
that also survives a strict terminal encoding (it replaces unrepresentable
characters instead of raising ``UnicodeEncodeError``). That combination is what
makes the CLI usable from Windows PowerShell, redirected files and CI logs.
"""

from __future__ import annotations

import sys
from typing import TextIO

__all__ = ["CliConsole"]


class CliConsole:
    """A tiny output façade with a colour-aware and a plain backend."""

    def __init__(
        self,
        *,
        color: bool = False,
        ascii_only: bool = False,
        out: TextIO | None = None,
        err: TextIO | None = None,
    ) -> None:
        self._out = out if out is not None else sys.stdout
        self._err = err if err is not None else sys.stderr
        self.color = color
        self.ascii_only = ascii_only
        self._rich = self._build_rich(self._out) if color else None
        self._rich_err = self._build_rich(self._err) if color else None

    @staticmethod
    def _build_rich(stream: TextIO):  # noqa: ANN205 - optional dependency
        try:
            from rich.console import Console as RichConsole
        except Exception:  # pragma: no cover - rich is a declared dependency
            return None
        try:
            return RichConsole(
                file=stream,
                markup=False,
                highlight=False,
                soft_wrap=True,
                no_color=False,
            )
        except Exception:  # pragma: no cover - defensive
            return None

    def out(self, message: str = "") -> None:
        """Write a normal line of output."""

        self._write(self._out, self._rich, message)

    def err(self, message: str = "") -> None:
        """Write a diagnostic line to standard error."""

        self._write(self._err, self._rich_err, message)

    def rule(self, character: str, width: int = 53) -> None:
        """Write a horizontal rule of *width* characters."""

        self.out("    " + character * width)

    def _write(self, stream: TextIO, rich_console, message: str) -> None:  # noqa: ANN001
        if rich_console is not None:
            try:
                rich_console.print(message, markup=False, highlight=False, soft_wrap=True, crop=False)
                return
            except UnicodeEncodeError:
                pass
        _plain_write(stream, message)


def _plain_write(stream: TextIO, message: str) -> None:
    text = message + "\n"
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        stream.write(text.encode(encoding, "replace").decode(encoding, "replace"))
    try:
        stream.flush()
    except Exception:  # pragma: no cover - closed streams
        pass
