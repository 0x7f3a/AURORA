"""Transport construction failures that must not surface as raw exceptions."""

from __future__ import annotations

import pytest

from aurora.config.models import NetworkLimits, RunLimits
from aurora.errors import ConfigError
from aurora.net.client import AuroraClient
from aurora.scope.policy import ScopePolicy


def _client(**overrides) -> AuroraClient:
    return AuroraClient(
        policy=ScopePolicy(),
        network_limits=NetworkLimits(requests_per_second=10.0),
        run_limits=RunLimits(),
        user_agent="aurora-test/0.0",
        **overrides,
    )


def test_unreadable_ca_bundle_is_reported_as_a_configuration_error(tmp_path):
    missing = tmp_path / "no-such-ca.pem"

    with pytest.raises(ConfigError) as excinfo:
        _client(verify=str(missing))

    assert "cannot load CA bundle" in str(excinfo.value)
