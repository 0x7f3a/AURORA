"""Exit codes shared by the CLI and the error hierarchy.

Values are part of AURORA's command-line contract: they are stable across
releases so that scripts and CI jobs can branch on them.
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Process exit codes.

    ``argparse`` emits :attr:`USAGE` itself for malformed command lines, which
    keeps the contract consistent for errors raised before dispatch.
    """

    OK = 0
    ERROR = 1
    USAGE = 2
    CONFIG = 3
    STORAGE = 4
    PLATFORM = 5
    NETWORK = 6
