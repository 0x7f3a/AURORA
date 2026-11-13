"""Terminal capability detection, including degraded consoles."""

from __future__ import annotations

from aurora.platform.terminal import TerminalInfo


class FakeStream:
    """Minimal stand-in for a text stream (``encoding`` is read-only on StringIO)."""

    def __init__(self, encoding: str | None, tty: bool) -> None:
        self.encoding = encoding
        self.written: list[str] = []
        self._tty = tty

    def write(self, text: str) -> int:  # noqa: D102 - stdlib API
        self.written.append(text)
        return len(text)

    def flush(self) -> None:  # noqa: D102 - stdlib API
        return None

    def isatty(self) -> bool:  # noqa: D102 - stdlib API
        return self._tty


def _detect(encoding="utf-8", tty=True, environ=None, **kwargs):
    stream = FakeStream(encoding, tty)
    return TerminalInfo.detect(stream=stream, environ=environ or {}, **kwargs)


def test_utf8_terminal_supports_unicode():
    info = _detect()
    assert info.unicode_ok is True
    assert info.encoding == "utf-8"


def test_ascii_terminal_disables_unicode_art():
    info = _detect(encoding="ascii")
    assert info.unicode_ok is False


def test_legacy_windows_code_page_disables_unicode_art():
    info = _detect(encoding="cp1252")
    assert info.unicode_ok is False


def test_unknown_encoding_disables_unicode_art():
    info = _detect(encoding="not-a-real-codec")
    assert info.unicode_ok is False


def test_ascii_flag_forces_plain_output():
    info = _detect(ascii_only=True)
    assert info.unicode_ok is False


def test_no_color_environment_variable_disables_colour():
    assert _detect(environ={"NO_COLOR": "1"}).color_ok is False


def test_dumb_terminal_disables_colour():
    assert _detect(environ={"TERM": "dumb"}).color_ok is False


def test_simple_terminal_allows_colour():
    assert _detect(environ={"TERM": "xterm-256color"}).color_ok is True


def test_non_tty_disables_colour():
    assert _detect(tty=False).color_ok is False


def test_no_color_flag_disables_colour():
    assert _detect(no_color=True).color_ok is False


def test_width_has_a_sane_floor():
    info = _detect()
    assert info.width >= 20


def test_can_render_reflects_encoding():
    plain = _detect(encoding="ascii")
    assert plain.can_render("plain text") is True
    assert plain.can_render("█") is False
