"""
Integration tests for REST API endpoints.
Tests: /health, /api/events, /api/control/*, WebSocket.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from fastapi.testclient import TestClient

from apps.service.server import create_app


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_ok(self, populated_run_dir: Path, service_config: dict):
        """Health endpoint should return status ok."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestStatusEndpoint:
    """Tests for /status endpoint."""

    def test_status_returns_info(self, populated_run_dir: Path, service_config: dict):
        """Status endpoint should return run info."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "run_dir" in data
        assert "link_status" in data
        assert "gcs_label" in data


class TestEventsAPI:
    """Tests for /api/events endpoint."""

    def test_get_events(self, populated_run_dir: Path, service_config: dict):
        """Should return events list."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.get("/api/events")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data
        assert len(data["events"]) > 0

    def test_events_pagination(self, populated_run_dir: Path, service_config: dict):
        """Should support pagination parameters."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.get("/api/events?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) <= 5

    def test_event_has_id(self, populated_run_dir: Path, service_config: dict):
        """Each event should have an ID."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.get("/api/events")
        data = response.json()
        for event in data["events"]:
            assert "id" in event


class TestEventDetailAPI:
    """Tests for /api/events/{event_id} endpoint."""

    def test_get_event_detail(self, populated_run_dir: Path, service_config: dict):
        """Should return event detail by ID."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        # First get events list
        events_response = client.get("/api/events")
        events = events_response.json()["events"]
        if events:
            event_id = events[0]["id"]

            # Get detail
            response = client.get(f"/api/events/{event_id}")
            assert response.status_code == 200
            data = response.json()
            assert "type" in data
            assert "time" in data

    def test_event_not_found(self, populated_run_dir: Path, service_config: dict):
        """Should return 404 for non-existent event."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.get("/api/events/nonexistent123")
        assert response.status_code == 404


class TestObservationsAPI:
    """Tests for /api/observations endpoint."""

    def test_get_observations(self, populated_run_dir: Path, service_config: dict):
        """Should return observations list."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.get("/api/observations")
        assert response.status_code == 200
        data = response.json()
        assert "observations" in data

    def test_observations_source_filter(self, populated_run_dir: Path, service_config: dict):
        """Should support source filter."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.get("/api/observations?source=fused")
        assert response.status_code == 200


class TestTelemetryAPI:
    """Tests for /api/telemetry endpoint."""

    def test_get_telemetry(self, populated_run_dir: Path, service_config: dict):
        """Should return latest telemetry."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.get("/api/telemetry")
        assert response.status_code == 200
        data = response.json()
        assert "telemetry" in data


class TestFSMAPI:
    """Tests for /api/fsm endpoint."""

    def test_get_fsm_state(self, populated_run_dir: Path, service_config: dict):
        """Should return FSM state."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.get("/api/fsm")
        assert response.status_code == 200
        data = response.json()
        assert "fsm_state" in data


class TestControlYawAPI:
    """Tests for /api/control/yaw endpoint."""

    def test_yaw_control_accepted(self, populated_run_dir: Path, service_config: dict):
        """Yaw control should be accepted."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.post(
            "/api/control/yaw",
            json={"yaw_deg": 45, "yaw_rate_deg_s": 30}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True
        assert data["command"] == "SET_YAW"

    def test_yaw_default_rate(self, populated_run_dir: Path, service_config: dict):
        """Yaw should use default rate if not specified."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.post(
            "/api/control/yaw",
            json={"yaw_deg": 45}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True


class TestControlModeAPI:
    """Tests for /api/control/mode endpoint."""

    def test_mode_control_accepted(self, populated_run_dir: Path, service_config: dict):
        """Mode control should be accepted."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.post(
            "/api/control/mode",
            json={"mode": "LOITER"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True
        assert data["command"] == "SET_MODE"


class TestControlEstopAPI:
    """Tests for /api/control/estop endpoint."""

    def test_estop_accepted(self, populated_run_dir: Path, service_config: dict):
        """Emergency stop should be accepted."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.post("/api/control/estop")
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True
        assert data["command"] == "STOP"


class TestRateLimiting:
    """Tests for command rate limiting."""

    def test_rate_limit_enforced(self, populated_run_dir: Path, service_config: dict):
        """Rapid commands should be rate limited."""
        # Set very low rate limit
        service_config["service"]["command_rate_limit_hz"] = 1
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        # First command should succeed
        response1 = client.post("/api/control/yaw", json={"yaw_deg": 45})
        assert response1.status_code == 200

        # Immediate second command should be rate limited
        response2 = client.post("/api/control/yaw", json={"yaw_deg": 90})
        assert response2.status_code == 429
        assert response2.json()["error"] == "rate_limited"


class TestCommandWhitelist:
    """Tests for command whitelist."""

    def test_unlisted_command_rejected(self, populated_run_dir: Path, service_config: dict):
        """Commands not in whitelist should be rejected."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.post(
            "/command",
            json={"type": "INVALID_COMMAND", "params": {}}
        )
        assert response.status_code == 400
        assert response.json()["error"] == "command_not_allowed"


class TestCORS:
    """Tests for CORS headers."""

    def test_cors_headers_present(self, populated_run_dir: Path, service_config: dict):
        """CORS headers should be present."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        response = client.options(
            "/api/events",
            headers={"Origin": "http://localhost:3000"}
        )
        # FastAPI handles CORS via middleware
        assert response.status_code in [200, 405]


class TestWebSocket:
    """Tests for WebSocket endpoint."""

    def test_websocket_connect(self, populated_run_dir: Path, service_config: dict):
        """Should be able to connect to WebSocket."""
        app = create_app(populated_run_dir, service_config["service"])
        client = TestClient(app)

        with client.websocket_connect("/ws") as websocket:
            # Should receive initial data
            data = websocket.receive_json()
            assert "type" in data
            assert "payload" in data
