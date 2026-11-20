#!/usr/bin/env python3
"""Run AURORA straight from a checkout.

    python3 run.py init --home ./lab
    python3 run.py version
    python3 run.py scope add https://lab.test/app

Python 3.11 or newer is the only requirement: the package is imported from
``src/`` and every command implemented today runs on the standard library
alone, so no virtual environment and no ``pip install`` are needed. On Windows
the interpreter is usually called ``python``: ``python run.py version``.

The file is deliberately not called ``aurora.py``: a module with that name in
the repository root would shadow the ``aurora`` package for anything imported
from here, including ``python -m aurora``. Installing the project
(``pip install -e .``) still gives you the ``aurora`` command; this launcher is
the zero-setup path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(_SRC))
    from aurora.cli.main import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
