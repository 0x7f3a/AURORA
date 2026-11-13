"""Pytest bootstrap.

The package is normally installed with ``pip install -e .``. The ``src``
fallback keeps the suite runnable from a plain checkout (for example when an
offline host has all dependencies but no install step), without masking a
broken install: it only applies when ``aurora`` cannot be imported at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"

try:  # pragma: no cover - depends on environment
    import aurora  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    sys.path.insert(0, str(_SRC))
