"""Platform value-object behaviour, including native naming rules."""

from __future__ import annotations

import platform

import pytest

from aurora.errors import PlatformError
from aurora.platform.detect import SUPPORTED_SYSTEMS, PlatformInfo


def test_collect_matches_stdlib():
    info = PlatformInfo.collect()
    assert info.system == platform.system()
    assert info.machine == platform.machine()
    assert info.python_version == platform.python_version()
    assert info.python_implementation == platform.python_implementation()


def test_linux_native_library_name():
    info = PlatformInfo.from_values(system="Linux", machine="x86_64")
    assert info.native_library_name == "libaurora.so"
    assert info.is_linux
    assert not info.is_windows
    assert info.is_supported


def test_windows_native_library_name():
    info = PlatformInfo.from_values(system="Windows", machine="AMD64")
    assert info.native_library_name == "aurora.dll"
    assert info.is_windows
    assert info.is_supported
    assert info.normalized_machine == "x86_64"


def test_macos_is_detectable_but_unsupported():
    info = PlatformInfo.from_values(system="Darwin", machine="arm64")
    assert info.native_library_name == "libaurora.dylib"
    assert not info.is_supported


def test_unknown_platform_has_no_native_component():
    info = PlatformInfo.from_values(system="Plan9", machine="mips")
    with pytest.raises(PlatformError):
        _ = info.native_library_name
    assert not info.is_supported


@pytest.mark.parametrize(
    ("machine", "expected"),
    [
        ("AMD64", "x86_64"),
        ("x86_64", "x86_64"),
        ("aarch64", "arm64"),
        ("arm64", "arm64"),
        ("i686", "x86"),
        ("", "unknown"),
        ("riscv64", "riscv64"),
    ],
)
def test_machine_normalisation(machine, expected):
    info = PlatformInfo.from_values(system="Linux", machine=machine)
    assert info.normalized_machine == expected


def test_banner_label_is_dynamic():
    linux = PlatformInfo.from_values(system="Linux", machine="x86_64")
    windows = PlatformInfo.from_values(system="Windows", machine="AMD64")
    assert linux.banner_label == "LINUX X86_64"
    assert windows.banner_label == "WINDOWS X86_64"
    assert "Linux" not in windows.banner_label


def test_describe_includes_system_and_runtime():
    info = PlatformInfo.from_values(
        system="Linux",
        release="6.1.0",
        machine="x86_64",
        python_version="3.12.3",
    )
    described = info.describe()
    assert "Linux 6.1.0 x86_64" in described
    assert "CPython 3.12.3" in described


def test_supported_systems_contract():
    assert SUPPORTED_SYSTEMS == ("Linux", "Windows")


def test_compiler_hints_name_primary_compilers():
    assert "MSVC" in PlatformInfo.from_values(system="Windows").native_compiler_hint
    assert "GCC" in PlatformInfo.from_values(system="Linux").native_compiler_hint
