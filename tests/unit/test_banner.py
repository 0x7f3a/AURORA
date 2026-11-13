"""Banner rendering: artwork fidelity, dynamic platform line, graceful fallback."""

from __future__ import annotations

from aurora import BUILD, DISPLAY_VERSION, OPERATOR
from aurora.cli.banner import BannerContext, banner_width, render_banner

LINUX = BannerContext(
    version=DISPLAY_VERSION,
    operator=OPERATOR,
    build=BUILD,
    platform_label="LINUX X86_64",
)
WINDOWS = BannerContext(
    version=DISPLAY_VERSION,
    operator=OPERATOR,
    build=BUILD,
    platform_label="WINDOWS X86_64",
)


def test_full_banner_keeps_official_artwork():
    rendered = render_banner(LINUX, width=120)
    assert "█████╗ ██╗   ██╗██████╗  ██████╗ ██████╗  █████╗" in rendered
    assert "╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝" in rendered


def test_full_banner_keeps_official_wording():
    rendered = render_banner(LINUX, width=120)
    assert "WEB APPLICATION PENETRATION TESTING FRAMEWORK" in rendered
    assert "PYTHON CORE  ·  NATIVE C ENGINE  ·  MODULAR ARCHITECTURE" in rendered
    assert "[01] RECONNAISSANCE       [02] ANALYSIS" in rendered
    assert "[03] SECURITY TESTING     [04] VERIFICATION" in rendered
    assert "[05] REPORT GENERATION" in rendered


def test_platform_line_is_dynamic():
    linux_banner = render_banner(LINUX, width=120)
    windows_banner = render_banner(WINDOWS, width=120)
    assert "PLATFORM      LINUX X86_64" in linux_banner
    assert "PLATFORM      WINDOWS X86_64" in windows_banner
    assert "WINDOWS" not in linux_banner


def test_metadata_values_are_aligned_at_column_21():
    rendered = render_banner(LINUX, width=120)
    lines = rendered.splitlines()
    version_line = next(line for line in lines if "VERSION" in line)
    operator_line = next(line for line in lines if "OPERATOR" in line)
    platform_line = next(line for line in lines if "PLATFORM" in line)
    assert version_line.index(DISPLAY_VERSION) == 21
    assert operator_line.index(OPERATOR) == 21
    assert platform_line.index("LINUX X86_64") == 21


def test_ascii_rendering_contains_no_non_ascii_characters():
    rendered = render_banner(LINUX, width=120, ascii_only=True)
    assert rendered.isascii()
    assert "A U R O R A" in rendered
    assert "PYTHON CORE  /  NATIVE C ENGINE  /  MODULAR ARCHITECTURE" in rendered
    assert "PLATFORM      LINUX X86_64" in rendered


def test_narrow_terminal_uses_compact_banner():
    rendered = render_banner(LINUX, width=40)
    lines = rendered.splitlines()
    assert len(lines) == 4
    assert lines[0] == f"AURORA {DISPLAY_VERSION}"
    assert "WEB APPLICATION PENETRATION TESTING FRAMEWORK" in rendered
    assert "█████" not in rendered


def test_banner_width_is_reported_consistently():
    rendered = render_banner(LINUX, width=1000)
    assert banner_width(LINUX) == max(len(line) for line in rendered.splitlines())
    assert banner_width(LINUX) > 40
    assert banner_width(LINUX, ascii_only=True) > 40
    # Exactly at the reported width, the full banner is still used.
    at_limit = render_banner(LINUX, width=banner_width(LINUX))
    assert "█████" in at_limit
    # One column narrower falls back to the compact rendering.
    assert "█████" not in render_banner(LINUX, width=banner_width(LINUX) - 1)


def test_banner_fits_a_standard_eighty_column_terminal():
    assert banner_width(LINUX) <= 80
    assert banner_width(WINDOWS) <= 80
