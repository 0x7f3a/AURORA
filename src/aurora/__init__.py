"""AURORA — web application penetration testing framework.

The public identity of the framework lives here so that every other module,
report, and banner reads the same values.
"""

from __future__ import annotations

__all__ = [
    "BUILD",
    "DISPLAY_VERSION",
    "OPERATOR",
    "PROGRAM_NAME",
    "__version__",
]

PROGRAM_NAME = "AURORA"

#: PEP 440 version used for packaging.
__version__ = "0.1.0.dev0"

#: Human-facing version string used in the CLI banner and in reports.
DISPLAY_VERSION = "0.1.0-dev"

#: Default operator identity recorded in assessments.
OPERATOR = "0x7f3a"

#: Build channel shown in the banner.
BUILD = "DEVELOPMENT"
