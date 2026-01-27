"""
Unit tests for FSM state machine.
Tests: state transitions, degradation strategies, sensor health.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from apps.control.fsm_runner import FSM, SensorHealth, TelemetryMonitor
from src.control.control_gate import CommandGate, GateConfig
from tests.conftest import MockMavlinkControl


class TestSensorHealth:
    """Tests for SensorHealth class."""

    def test_initial_state_both_fail(self):
        """Initially both sensors should be in fail state."""
        health = SensorHealth(timeout_sec=1.0)
        # Without updates, both should be considered failed (no data received)
        assert health.status() == "BOTH_FAIL"

    def test_vision_ok_after_update(self):
        """Vision should be OK after update."""
        health = SensorHealth(timeout_sec=5.0)
        health.update_vision()
        # Only vision updated
        assert health.vision_ok() is True
        assert health.audio_ok() is False
        assert health.status() == "AUDIO_FAIL"

    def test_audio_ok_after_update(self):
        """Audio should be OK after update."""
        health = SensorHealth(timeout_sec=5.0)
        health.update_audio()
        # Only audio updated
        assert health.vision_ok() is False
        assert health.audio_ok() is True
        assert health.status() == "VISION_FAIL"

    def test_all_ok_after_both_update(self):
        """Both OK after both updates."""
        health = SensorHealth(timeout_sec=5.0)
        health.update_vision()
        health.update_audio()
        assert health.status() == "ALL_OK"

    def test_timeout_detection(self):
        """Sensor should fail after timeout."""
        health = SensorHealth(timeout_sec=0.1)
        health.update_vision()
        health.update_audio()
        assert health.status() == "ALL_OK"

        # Wait for timeout
        time.sleep(0.15)
        assert health.status() == "BOTH_FAIL"


class TestFSMStateTransitions:
    """Tests for FSM state transitions."""

    @pytest.fixture
    def fsm_setup(self, temp_run_dir: Path, fsm_config: dict):
        """Create FSM instance for testing."""
        events_path = temp_run_dir / "events.jsonl"
        commands_path = temp_run_dir / "commands.jsonl"
        events_path.touch()
        commands_path.touch()

        gate_cfg = GateConfig(max_rate_hz=5, command_ttl_sec=1)
        gate = CommandGate(gate_cfg)
        mock_control = MockMavlinkControl()

        fsm = FSM(
            config=fsm_config,
            gate=gate,
            control=mock_control,
            events_path=events_path,
            commands_path=commands_path,
        )
        return fsm, mock_control, events_path, commands_path

    def test_initial_state_is_idle(self, fsm_setup):
        """FSM should start in IDLE state."""
        fsm, _, _, _ = fsm_setup
        assert fsm._state == FSM.IDLE

    def test_idle_to_search_on_observation(self, fsm_setup):
        """IDLE -> SEARCH -> SCAN -> ... on receiving observation."""
        fsm, _, _, _ = fsm_setup
        # Initialize sensor health
        fsm._sensor.update_vision()
        fsm._sensor.update_audio()

        obs = {
            "status": "OK",
            "bearing_deg": 45.0,
            "confidence": 0.7,
            "source": "fusion",
            "extras": {"sources": ["vision", "audio"]},
        }
        fsm.step(obs)
        # FSM transitions quickly through multiple states
        assert fsm._state in (FSM.SCAN, FSM.LOCKED, FSM.TRACK)

    def test_scan_to_locked_on_high_confidence(self, fsm_setup):
        """SCAN -> LOCKED -> TRACK when vision confirms with high confidence."""
        fsm, _, _, _ = fsm_setup
        fsm._state = FSM.SCAN
        fsm._sensor.update_vision()
        fsm._sensor.update_audio()

        obs = {
            "status": "OK",
            "bearing_deg": 45.0,
            "confidence": 0.8,  # > lock_conf (0.6)
            "source": "fusion",
            "extras": {"sources": ["vision", "audio"]},
        }
        fsm.step(obs)
        # May transition to LOCKED then TRACK in same step
        assert fsm._state in (FSM.LOCKED, FSM.TRACK)

    def test_locked_to_track_on_continuous(self, fsm_setup):
        """LOCKED -> TRACK on continuous tracking."""
        fsm, _, _, _ = fsm_setup
        fsm._state = FSM.LOCKED
        fsm._sensor.update_vision()
        fsm._sensor.update_audio()

        obs = {
            "status": "OK",
            "bearing_deg": 45.0,
            "confidence": 0.8,
            "source": "fusion",
            "extras": {"sources": ["vision", "audio"]},
        }
        fsm.step(obs)
        assert fsm._state == FSM.TRACK

    def test_track_to_lost_on_timeout(self, fsm_setup):
        """TRACK -> LOST -> SEARCH when observation times out."""
        fsm, _, _, _ = fsm_setup
        fsm._state = FSM.TRACK
        fsm._lost_timeout = 0.1
        fsm._sensor.update_vision()
        fsm._sensor.update_audio()
        fsm._last_seen = time.monotonic() - 0.5  # Simulate old last seen

        # No valid observation
        fsm.step(None)
        # FSM goes TRACK -> LOST -> SEARCH quickly
        assert fsm._state in (FSM.LOST, FSM.SEARCH)

    def test_lost_to_search_resume(self, fsm_setup):
        """LOST -> SEARCH to resume searching."""
        fsm, _, _, _ = fsm_setup
        fsm._state = FSM.LOST
        fsm._sensor.update_vision()
        fsm._sensor.update_audio()

        fsm.step(None)
        assert fsm._state == FSM.SEARCH

    def test_yaw_command_sent(self, fsm_setup):
        """Yaw command should be sent in SCAN state."""
        fsm, mock_control, _, _ = fsm_setup
        fsm._state = FSM.SCAN
        fsm._sensor.update_vision()
        fsm._sensor.update_audio()

        obs = {
            "status": "OK",
            "bearing_deg": 45.0,
            "confidence": 0.5,
            "source": "fusion",
            "extras": {"sources": ["vision"]},
        }
        fsm.step(obs)

        assert len(mock_control.commands) > 0
        assert mock_control.commands[0]["type"] == "SET_YAW"
        assert mock_control.commands[0]["yaw_deg"] == 45.0


class TestFSMDegradation:
    """Tests for FSM degradation strategies."""

    @pytest.fixture
    def fsm_setup(self, temp_run_dir: Path, fsm_config: dict):
        """Create FSM instance for testing."""
        events_path = temp_run_dir / "events.jsonl"
        commands_path = temp_run_dir / "commands.jsonl"
        events_path.touch()
        commands_path.touch()

        gate_cfg = GateConfig(max_rate_hz=5, command_ttl_sec=1)
        gate = CommandGate(gate_cfg)
        mock_control = MockMavlinkControl()

        fsm = FSM(
            config=fsm_config,
            gate=gate,
            control=mock_control,
            events_path=events_path,
            commands_path=commands_path,
        )
        return fsm, mock_control

    def test_vision_fail_triggers_degraded_or_return(self, fsm_setup):
        """Vision failure should trigger DEGRADED or RETURN state."""
        fsm, _ = fsm_setup
        fsm._state = FSM.TRACK
        fsm._sensor._timeout = 0.1

        # Only update audio, not vision
        fsm._sensor.update_audio()
        time.sleep(0.15)

        fsm.step(None)
        # Depending on timing, may go to DEGRADED or RETURN
        assert fsm._state in (FSM.DEGRADED, FSM.RETURN)

    def test_audio_fail_triggers_degraded_or_return(self, fsm_setup):
        """Audio failure should trigger DEGRADED or RETURN state."""
        fsm, _ = fsm_setup
        fsm._state = FSM.TRACK
        fsm._sensor._timeout = 0.1

        # Only update vision, not audio
        fsm._sensor.update_vision()
        time.sleep(0.15)

        fsm.step(None)
        # Depending on timing, may go to DEGRADED or RETURN
        assert fsm._state in (FSM.DEGRADED, FSM.RETURN)

    def test_both_fail_triggers_return(self, fsm_setup):
        """Both sensor failure should trigger RETURN state."""
        fsm, mock_control = fsm_setup
        fsm._state = FSM.TRACK
        fsm._sensor._timeout = 0.1

        # Don't update either sensor
        time.sleep(0.15)

        fsm.step(None)
        assert fsm._state == FSM.RETURN

        # RTL command should be sent
        rtl_cmds = [c for c in mock_control.commands if c.get("type") == "SET_MODE"]
        assert len(rtl_cmds) > 0
        assert rtl_cmds[0]["mode"] == "RTL"

    def test_auto_recover_from_degraded(self, fsm_setup):
        """Should auto-recover when sensors come back online."""
        fsm, _ = fsm_setup
        fsm._state = FSM.DEGRADED
        fsm._active_source = "audio_only"
        fsm._degraded_since = time.monotonic()

        # Both sensors now OK
        fsm._sensor.update_vision()
        fsm._sensor.update_audio()

        fsm.step(None)
        assert fsm._state == FSM.SEARCH
        assert fsm._active_source == "fused"

    def test_degraded_timeout_triggers_return(self, fsm_setup):
        """Prolonged degraded state should trigger RETURN."""
        fsm, _ = fsm_setup
        fsm._state = FSM.DEGRADED
        fsm._max_degraded_sec = 0.1
        fsm._degraded_since = time.monotonic() - 0.5

        # Keep one sensor alive but not both
        fsm._sensor.update_audio()

        fsm.step(None)
        assert fsm._state == FSM.RETURN


class TestFSMEventLogging:
    """Tests for FSM event logging."""

    @pytest.fixture
    def fsm_setup(self, temp_run_dir: Path, fsm_config: dict):
        """Create FSM instance for testing."""
        events_path = temp_run_dir / "events.jsonl"
        commands_path = temp_run_dir / "commands.jsonl"
        events_path.touch()
        commands_path.touch()

        # Disable event cooldown for testing
        fsm_config["fsm"]["event_cooldown_sec"] = 0

        gate_cfg = GateConfig(max_rate_hz=5, command_ttl_sec=1)
        gate = CommandGate(gate_cfg)

        fsm = FSM(
            config=fsm_config,
            gate=gate,
            control=None,  # Dry run
            events_path=events_path,
            commands_path=commands_path,
        )
        return fsm, events_path, commands_path

    def test_state_transition_logged(self, fsm_setup):
        """State transitions should be logged to events.jsonl."""
        fsm, events_path, _ = fsm_setup
        fsm._sensor.update_vision()
        fsm._sensor.update_audio()

        obs = {
            "status": "OK",
            "bearing_deg": 45.0,
            "confidence": 0.7,
            "source": "fusion",
            "extras": {"sources": ["vision", "audio"]},
        }
        fsm.step(obs)

        # Read events
        with events_path.open("r") as f:
            events = [json.loads(line) for line in f if line.strip()]

        assert len(events) > 0
        mode_events = [e for e in events if e["type"] == "MODE_CHANGED"]
        assert len(mode_events) > 0
        assert "IDLE -> SEARCH" in mode_events[0]["note"]

    def test_command_logged(self, fsm_setup):
        """Commands should be logged to commands.jsonl."""
        fsm, _, commands_path = fsm_setup
        fsm._state = FSM.SCAN
        fsm._sensor.update_vision()
        fsm._sensor.update_audio()

        obs = {
            "status": "OK",
            "bearing_deg": 45.0,
            "confidence": 0.5,
            "source": "fusion",
            "extras": {"sources": ["vision"]},
        }
        fsm.step(obs)

        # Read commands
        with commands_path.open("r") as f:
            commands = [json.loads(line) for line in f if line.strip()]

        assert len(commands) > 0
        yaw_cmds = [c for c in commands if c["type"] == "SET_YAW"]
        assert len(yaw_cmds) > 0


class TestTelemetryMonitor:
    """Tests for TelemetryMonitor class."""

    def test_empty_file_returns_ok(self, temp_run_dir: Path):
        """Empty telemetry file should return default OK."""
        tel_path = temp_run_dir / "telemetry" / "telemetry.jsonl"
        tel_path.touch()

        monitor = TelemetryMonitor(tel_path)
        assert monitor.update() == "OK"

    def test_reads_latest_status(self, temp_run_dir: Path):
        """Should read latest link status from file."""
        tel_path = temp_run_dir / "telemetry" / "telemetry.jsonl"
        with tel_path.open("w") as f:
            f.write(json.dumps({"link_status": "OK"}) + "\n")
            f.write(json.dumps({"link_status": "DEGRADED"}) + "\n")
            f.write(json.dumps({"link_status": "LOST"}) + "\n")

        monitor = TelemetryMonitor(tel_path)
        assert monitor.update() == "LOST"
