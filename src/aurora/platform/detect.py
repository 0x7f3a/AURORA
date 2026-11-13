"""Operating-system and architecture detection.

``PlatformInfo`` is a frozen value object. :meth:`PlatformInfo.collect` reads
the host, while :meth:`PlatformInfo.from_values` accepts explicit values so the
Windows and Linux naming rules can be tested on any single host.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass

from aurora.errors import PlatformError

__all__ = ["SUPPORTED_SYSTEMS", "PlatformInfo"]

#: Systems AURORA 0.1 explicitly targets. Other systems may work but are not
#: supported and are reported as such.
SUPPORTED_SYSTEMS: tuple[str, ...] = ("Linux", "Windows")

_MACHINE_ALIASES = {
    "amd64": "x86_64",
    "x64": "x86_64",
    "x86-64": "x86_64",
    "x86_64": "x86_64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "i386": "x86",
    "i486": "x86",
    "i586": "x86",
    "i686": "x86",
    "x86": "x86",
}

_NATIVE_LIBRARY_NAMES = {
    "Windows": "aurora.dll",
    "Linux": "libaurora.so",
    "Darwin": "libaurora.dylib",
}


@dataclass(frozen=True, slots=True)
class PlatformInfo:
    """A snapshot of the hosting platform."""

    system: str
    release: str
    machine: str
    python_implementation: str
    python_version: str

    @classmethod
    def collect(cls) -> "PlatformInfo":
        """Detect the current interpreter and host."""

        return cls(
            system=platform.system() or "Unknown",
            release=platform.release() or "",
            machine=platform.machine() or "",
            python_implementation=platform.python_implementation() or "CPython",
            python_version=platform.python_version() or "",
        )

    @classmethod
    def from_values(
        cls,
        *,
        system: str,
        release: str = "",
        machine: str = "",
        python_implementation: str = "CPython",
        python_version: str = "",
    ) -> "PlatformInfo":
        return cls(
            system=system,
            release=release,
            machine=machine,
            python_implementation=python_implementation,
            python_version=python_version,
        )

    @property
    def normalized_machine(self) -> str:
        """Canonical architecture name (``x86_64``, ``arm64``, ``x86``)."""

        key = self.machine.strip().lower()
        return _MACHINE_ALIASES.get(key, key or "unknown")

    @property
    def is_windows(self) -> bool:
        return self.system == "Windows"

    @property
    def is_linux(self) -> bool:
        return self.system == "Linux"

    @property
    def is_supported(self) -> bool:
        return self.system in SUPPORTED_SYSTEMS

    @property
    def native_library_name(self) -> str:
        """File name the native component must have on this platform."""

        try:
            return _NATIVE_LIBRARY_NAMES[self.system]
        except KeyError:
            raise PlatformError(
                f"no native component is defined for platform {self.system!r}",
                hint="Windows and Linux are the supported targets",
            ) from None

    @property
    def native_compiler_hint(self) -> str:
        """Documented compiler preference for this platform."""

        if self.is_windows:
            return "MSVC (primary), MinGW-w64 (secondary)"
        if self.is_linux:
            return "GCC (primary), Clang (secondary)"
        return "not supported"

    @property
    def banner_label(self) -> str:
        """Upper-case label shown in the CLI banner, e.g. ``LINUX X86_64``."""

        return f"{self.system} {self.normalized_machine}".upper()

    def describe(self) -> str:
        """One-line human readable description."""

        parts = [self.system]
        if self.release:
            parts.append(self.release)
        parts.append(self.normalized_machine)
        os_line = " ".join(parts)
        runtime = f"{self.python_implementation} {self.python_version}".strip()
        # ASCII only: this string is printed by ``aurora version`` and ends up in
        # reports, both of which must survive a non-Unicode console.
        return f"{os_line} | {runtime}" if runtime else os_line
