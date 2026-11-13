"""Local server fixtures for the transport integration tests."""

from __future__ import annotations

import pytest

from fixtures.http_server import FixtureServer, server_tls_context


@pytest.fixture
def server() -> FixtureServer:
    instance = FixtureServer().start()
    try:
        yield instance
    finally:
        instance.stop()


@pytest.fixture
def other_server() -> FixtureServer:
    instance = FixtureServer().start()
    try:
        yield instance
    finally:
        instance.stop()


@pytest.fixture
def tls_server() -> FixtureServer:
    instance = FixtureServer(tls_context=server_tls_context()).start()
    try:
        yield instance
    finally:
        instance.stop()
