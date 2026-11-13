"""Platform detection: operating system, architecture, terminal, native names."""

from __future__ import annotations

from aurora.platform.detect import SUPPORTED_SYSTEMS, PlatformInfo
from aurora.platform.terminal import TerminalInfo

__all__ = ["SUPPORTED_SYSTEMS", "PlatformInfo", "TerminalInfo"]
