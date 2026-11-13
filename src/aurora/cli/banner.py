"""The AURORA CLI banner.

The official artwork and wording are preserved verbatim in
:data:`_UNICODE_ART`. Three renderings exist:

* the full banner, when the terminal can encode the artwork and is wide enough;
* an ASCII rendering, when it cannot — the artwork is replaced by an ASCII
  frame while all wording is kept, so nothing is emitted as ``?`` characters;
* a compact rendering for narrow terminals.

The platform line is always supplied by the caller from
:class:`aurora.platform.detect.PlatformInfo`; nothing here hardcodes a host.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["BannerContext", "render_banner", "banner_width"]

_UNICODE_ART: tuple[str, ...] = (
    "     █████╗ ██╗   ██╗██████╗  ██████╗ ██████╗  █████╗",
    "    ██╔══██╗██║   ██║██╔══██╗██╔═══██╗██╔══██╗██╔══██╗",
    "    ███████║██║   ██║██████╔╝██║   ██║██████╔╝███████║",
    "    ██╔══██╗██║   ██║██╔══██╗██║   ██║██╔══██╗██╔══██║",
    "    ██║  ██║╚██████╔╝██║  ██║╚████╔╝██║  ██║██║  ██║",
    "    ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝",
)

_HEAVY_WIDTH = 55
_LIGHT_WIDTH = 53
_ASCII_FRAME_WIDTH = 53
_TITLE_INDENT = "       "
_LABEL_WIDTH = 14


def _ascii_art() -> tuple[str, ...]:
    title = "A U R O R A"
    width = _ASCII_FRAME_WIDTH
    left = max(0, (width - len(title)) // 2)
    body = " " * left + title
    body = body + " " * max(0, width - len(body))
    frame = "+" + "-" * width + "+"
    return ("    " + frame, "    |" + body + "|", "    " + frame)


@dataclass(frozen=True, slots=True)
class BannerContext:
    version: str
    operator: str
    build: str
    platform_label: str


def _full_banner(context: BannerContext, *, ascii_only: bool) -> list[str]:
    art = _ascii_art() if ascii_only else _UNICODE_ART
    heavy_char, light_char, dot = ("=", "-", "/") if ascii_only else ("━", "─", "·")

    lines: list[str] = list(art)
    lines.append("")
    lines.append("    " + heavy_char * _HEAVY_WIDTH)
    lines.append("")
    lines.append(f"{_TITLE_INDENT}WEB APPLICATION PENETRATION TESTING FRAMEWORK")
    lines.append("")
    lines.append(
        f"{_TITLE_INDENT}PYTHON CORE  {dot}  NATIVE C ENGINE  {dot}  MODULAR ARCHITECTURE"
    )
    lines.append("")
    lines.append("    " + heavy_char * _HEAVY_WIDTH)
    lines.append("")
    lines.append("       [01] RECONNAISSANCE       [02] ANALYSIS")
    lines.append("       [03] SECURITY TESTING     [04] VERIFICATION")
    lines.append("       [05] REPORT GENERATION")
    lines.append("")
    lines.append("    " + light_char * _LIGHT_WIDTH)
    lines.append("")
    for label, value in (
        ("VERSION", context.version),
        ("OPERATOR", context.operator),
        ("BUILD", context.build),
        ("PLATFORM", context.platform_label),
    ):
        lines.append(f"{_TITLE_INDENT}{label:<{_LABEL_WIDTH}}{value}")
    lines.append("")
    lines.append("    " + light_char * _LIGHT_WIDTH)
    return lines


def _compact_banner(context: BannerContext) -> list[str]:
    return [
        f"AURORA {context.version}",
        "WEB APPLICATION PENETRATION TESTING FRAMEWORK",
        f"operator {context.operator} / platform {context.platform_label}",
        "phases: reconnaissance / analysis / security testing / verification / reporting",
    ]


def banner_width(context: BannerContext, *, ascii_only: bool = False) -> int:
    """Width of the full banner for this context and rendering."""

    return max(len(line) for line in _full_banner(context, ascii_only=ascii_only))


def render_banner(
    context: BannerContext,
    *,
    width: int = 80,
    ascii_only: bool = False,
) -> str:
    """Render the banner for a terminal of *width* columns."""

    lines = _full_banner(context, ascii_only=ascii_only)
    required = max(len(line) for line in lines)
    if width < required:
        lines = _compact_banner(context)
    return "\n".join(lines)
