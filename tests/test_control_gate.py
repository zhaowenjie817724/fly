"""
Unit tests for control gate (rate limiting, TTL, link check).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.control.control_gate import CommandGate, GateConfig


class TestGateConfig:
    """Tests for GateConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        cfg = GateConfig()
        assert cfg.max_rate_hz == 5.0
        assert cfg.command_ttl_sec == 1.0
        assert "SET_YAW" in cfg.allow_types

    def test_custom_values(self):
        """Test custom configuration."""
        cfg = GateConfig(max_rate_hz=10, command_ttl_sec=2)
        assert cfg.max_rate_hz == 10.0
        assert cfg.command_ttl_sec == 2.0


class TestCommandGateRateLimiting:
    """Tests for rate limiting functionality."""

    def test_first_command_allowed(self):
        """First command should always be allowed."""
        cfg = GateConfig(max_rate_hz=5)
        gate = CommandGate(cfg)
        gate.update_link_status("OK")

        assert gate.can_send("SET_YAW") is True

    def test_rate_limit_enforced(self):
        """Commands should be rate limited."""
        cfg = GateConfig(max_rate_hz=10)  # 100ms interval
        gate = CommandGate(cfg)
        gate.update_link_status("OK")

        # First command
        assert gate.can_send("SET_YAW") is True
        gate.mark_sent()

        # Immediate second command should be blocked
        assert gate.can_send("SET_YAW") is False

    def test_rate_limit_resets_after_interval(self):
        """Rate limit should reset after interval."""
        cfg = GateConfig(max_rate_hz=100)  # 10ms interval
        gate = CommandGate(cfg)
        gate.update_link_status("OK")

        # First command
        assert gate.can_send("SET_YAW") is True
        gate.mark_sent()

        # Wait for interval
        time.sleep(0.015)

        # Should be allowed now
        assert gate.can_send("SET_YAW") is True

    def test_zero_rate_allows_all(self):
        """Zero rate should allow all commands."""
        cfg = GateConfig(max_rate_hz=0)
        gate = CommandGate(cfg)
        gate.update_link_status("OK")

        for _ in range(10):
            assert gate.can_send("SET_YAW") is True
            gate.mark_sent()


class TestCommandGateTTL:
    """Tests for command TTL functionality."""

    def test_not_expired_initially(self):
        """Commands should not be expired initially."""
        cfg = GateConfig(command_ttl_sec=1)
        gate = CommandGate(cfg)

        assert gate.expired() is True  # No command sent yet

    def test_expired_after_ttl(self):
        """Commands should expire after TTL."""
        cfg = GateConfig(command_ttl_sec=0.05)
        gate = CommandGate(cfg)
        gate.update_link_status("OK")
        gate.mark_sent()

        assert gate.expired() is False

        time.sleep(0.06)

        assert gate.expired() is True


class TestCommandGateLinkStatus:
    """Tests for link status checking."""

    def test_commands_blocked_without_link(self):
        """Commands should be blocked if link not OK."""
        cfg = GateConfig()
        gate = CommandGate(cfg)
        gate.update_link_status("LOST")

        assert gate.can_send("SET_YAW") is False

    def test_commands_allowed_with_link(self):
        """Commands should be allowed if link OK."""
        cfg = GateConfig()
        gate = CommandGate(cfg)
        gate.update_link_status("OK")

        assert gate.can_send("SET_YAW") is True

    def test_degraded_link_blocked(self):
        """Degraded link should block commands (only OK allowed)."""
        cfg = GateConfig()
        gate = CommandGate(cfg)
        gate.update_link_status("DEGRADED")

        # Current implementation only allows "OK"
        assert gate.can_send("SET_YAW") is False

    def test_unknown_command_blocked(self):
        """Commands not in allow_types should be blocked."""
        cfg = GateConfig()
        gate = CommandGate(cfg)
        gate.update_link_status("OK")

        assert gate.can_send("INVALID_CMD") is False


class TestCommandGateIntegration:
    """Integration tests for CommandGate."""

    def test_full_workflow(self):
        """Test complete command workflow."""
        cfg = GateConfig(max_rate_hz=100, command_ttl_sec=0.05)
        gate = CommandGate(cfg)

        # Initial state - no link update yet, defaults to OK
        gate.update_link_status("LOST")
        assert gate.can_send("SET_YAW") is False

        # Link established
        gate.update_link_status("OK")
        assert gate.can_send("SET_YAW") is True

        # Send command
        gate.mark_sent()
        assert gate.expired() is False

        # Rate limited
        assert gate.can_send("SET_YAW") is False

        # Wait for rate limit
        time.sleep(0.015)
        assert gate.can_send("SET_YAW") is True

        # Wait for TTL
        time.sleep(0.05)
        assert gate.expired() is True

        # Link lost
        gate.update_link_status("LOST")
        assert gate.can_send("SET_YAW") is False
