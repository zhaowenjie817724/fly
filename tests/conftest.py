"""
Pytest fixtures for 通感之眼 2.0 test suite.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest

# Add repo root to path
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))


@pytest.fixture
def temp_run_dir() -> Generator[Path, None, None]:
    """Create a temporary run directory with standard structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir)
        (run_dir / "telemetry").mkdir()
        (run_dir / "observations").mkdir()
        (run_dir / "video").mkdir()
        (run_dir / "audio").mkdir()
        (run_dir / "events" / "vision").mkdir(parents=True)
        yield run_dir


@pytest.fixture
def sample_telemetry() -> dict:
    """Sample telemetry record."""
    return {
        "version": "0.1",
        "time": {"epoch_ms": 1706300000000, "mono_ms": 1000, "t_boot_ms": 5000},
        "attitude": {"roll_deg": 0.5, "pitch_deg": -1.2, "yaw_deg": 45.0},
        "position": {"lat": 31.2304, "lon": 121.4737, "alt_m": 50.0},
        "velocity": {"vx": 1.0, "vy": 0.5, "vz": -0.1},
        "battery": {"voltage": 11.8, "remaining_pct": 75},
        "link_status": "OK",
    }


@pytest.fixture
def sample_vision_observation() -> dict:
    """Sample vision observation."""
    return {
        "version": "0.1",
        "time": {"epoch_ms": 1706300000000, "mono_ms": 1000},
        "source": "vision",
        "bearing_deg": 30.0,
        "roi": {"x": 320, "y": 240, "w": 50, "h": 80},
        "confidence": 0.85,
        "status": "OK",
    }


@pytest.fixture
def sample_audio_observation() -> dict:
    """Sample audio observation."""
    return {
        "version": "0.1",
        "time": {"epoch_ms": 1706300000000, "mono_ms": 1000},
        "source": "audio",
        "bearing_deg": 35.0,
        "roi": None,
        "confidence": 0.6,
        "status": "OK",
    }


@pytest.fixture
def sample_fused_observation() -> dict:
    """Sample fused observation."""
    return {
        "version": "0.1",
        "time": {"epoch_ms": 1706300000000, "mono_ms": 1000},
        "source": "fusion",
        "bearing_deg": 32.0,
        "roi": {"x": 320, "y": 240, "w": 50, "h": 80},
        "confidence": 0.85,
        "status": "OK",
        "extras": {"sources": ["vision", "audio"]},
    }


@pytest.fixture
def sample_event() -> dict:
    """Sample event record."""
    return {
        "version": "0.1",
        "time": {"epoch_ms": 1706300000000, "mono_ms": 1000},
        "type": "TARGET_DETECTED",
        "severity": "INFO",
        "note": "Person detected at bearing 32deg",
        "ref": {"observation_id": "000001-v"},
    }


@pytest.fixture
def fsm_config() -> dict:
    """FSM configuration for testing."""
    return {
        "fusion": {"max_gap_ms": 200},
        "fsm": {
            "lock_conf": 0.6,
            "audio_trigger_conf": 0.3,
            "lost_timeout_sec": 3,
            "yaw_rate_deg_s": 30,
            "max_cmd_rate_hz": 5,
            "command_ttl_sec": 1,
            "event_cooldown_sec": 0.1,
            "states": [
                "IDLE", "SEARCH", "SCAN", "LOCKED",
                "TRACK", "LOST", "DEGRADED", "RETURN"
            ],
            "degradation": {
                "vision_fail_action": "audio_only",
                "audio_fail_action": "vision_only",
                "both_fail_action": "return",
                "max_degraded_sec": 30,
                "auto_recover": True,
            },
        },
        "control": {
            "mode": "mavlink_udp",
            "mavlink": {"udp": "udp:127.0.0.1:14551"},
        },
    }


@pytest.fixture
def service_config() -> dict:
    """Service configuration for testing."""
    return {
        "service": {
            "host": "127.0.0.1",
            "port": 8000,
            "status_interval_sec": 1,
            "telemetry_timeout_sec": 3,
            "command_rate_limit_hz": 5,
            "command_whitelist": ["SET_YAW", "STOP", "SET_MODE"],
            "default_yaw_rate_deg_s": 30,
            "gcs_label": "Test GCS",
        }
    }


@pytest.fixture
def populated_run_dir(
    temp_run_dir: Path,
    sample_telemetry: dict,
    sample_fused_observation: dict,
    sample_event: dict,
) -> Path:
    """Create a run directory with sample data."""
    # Write telemetry
    tel_path = temp_run_dir / "telemetry" / "telemetry.jsonl"
    with tel_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(sample_telemetry) + "\n")

    # Write fused observation
    obs_path = temp_run_dir / "observations" / "fused.jsonl"
    with obs_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(sample_fused_observation) + "\n")

    # Write events
    events_path = temp_run_dir / "events.jsonl"
    with events_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(sample_event) + "\n")

    # Write run metadata
    meta_path = temp_run_dir / "run_meta.json"
    meta = {
        "run_id": "test_run_001",
        "created_at": "2026-01-27T00:00:00Z",
        "config": "test_config.yaml",
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f)

    return temp_run_dir


class MockMavlinkControl:
    """Mock MAVLink control for testing."""

    def __init__(self):
        self.commands: list[dict] = []

    def send_yaw(self, yaw_deg: float, yaw_rate: float, relative: bool = False) -> None:
        self.commands.append({
            "type": "SET_YAW",
            "yaw_deg": yaw_deg,
            "yaw_rate": yaw_rate,
            "relative": relative,
        })

    def set_mode(self, mode: str) -> None:
        self.commands.append({"type": "SET_MODE", "mode": mode})

    def send_stop(self) -> None:
        self.commands.append({"type": "STOP"})


@pytest.fixture
def mock_mavlink() -> MockMavlinkControl:
    """Create a mock MAVLink control."""
    return MockMavlinkControl()
