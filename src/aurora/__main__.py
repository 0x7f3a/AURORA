"""Allow ``python -m aurora`` to behave exactly like the ``aurora`` script."""

from __future__ import annotations

import sys

from aurora.cli.main import main

if __name__ == "__main__":
    sys.exit(int(main()))
