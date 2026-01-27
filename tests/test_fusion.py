"""
Unit tests for fusion module.
Tests: weighted fusion, degradation strategies, edge cases.
"""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.fusion.simple_fusion import Observation, fuse, _weight


class TestWeightFunction:
    """Tests for _weight() helper function."""

    def test_none_returns_default(self):
        """None confidence should return 0.5."""
        assert _weight(None) == 0.5

    def test_clamp_minimum(self):
        """Confidence below 0.05 should clamp to 0.05."""
        assert _weight(0.0) == 0.05
        assert _weight(-0.5) == 0.05

    def test_clamp_maximum(self):
        """Confidence above 1.0 should clamp to 1.0."""
        assert _weight(1.5) == 1.0
        assert _weight(2.0) == 1.0

    def test_normal_range(self):
        """Normal confidence values should pass through."""
        assert _weight(0.5) == 0.5
        assert _weight(0.8) == 0.8
        assert _weight(0.1) == 0.1


class TestFusion:
    """Tests for fuse() function."""

    def test_both_none_returns_none(self):
        """No inputs should return None."""
        result = fuse(None, None)
        assert result is None

    def test_vision_only(self):
        """Vision-only input should return degraded observation."""
        vision = Observation(
            time={"epoch_ms": 1000},
            source="vision",
            bearing_deg=45.0,
            roi={"x": 100, "y": 100, "w": 50, "h": 50},
            confidence=0.9,
            status="OK",
        )
        result = fuse(vision, None)

        assert result is not None
        assert result.source == "fusion"
        assert result.bearing_deg == 45.0
        assert result.status == "DEGRADED"
        assert result.extras["sources"] == ["vision"]

    def test_audio_only(self):
        """Audio-only input should return degraded observation."""
        audio = Observation(
            time={"epoch_ms": 1000},
            source="audio",
            bearing_deg=60.0,
            roi=None,
            confidence=0.5,
            status="OK",
        )
        result = fuse(None, audio)

        assert result is not None
        assert result.source == "fusion"
        assert result.bearing_deg == 60.0
        assert result.status == "DEGRADED"
        assert result.roi is None
        assert result.extras["sources"] == ["audio"]

    def test_weighted_fusion(self):
        """Both inputs should produce weighted average."""
        vision = Observation(
            time={"epoch_ms": 1000},
            source="vision",
            bearing_deg=40.0,
            roi={"x": 100, "y": 100, "w": 50, "h": 50},
            confidence=0.8,
            status="OK",
        )
        audio = Observation(
            time={"epoch_ms": 1000},
            source="audio",
            bearing_deg=50.0,
            roi=None,
            confidence=0.4,
            status="OK",
        )
        result = fuse(vision, audio)

        assert result is not None
        assert result.source == "fusion"
        assert result.status == "OK"
        # Weighted: (40*0.8 + 50*0.4) / (0.8+0.4) = 52/1.2 = 43.33
        assert 43.0 < result.bearing_deg < 44.0
        assert result.extras["sources"] == ["vision", "audio"]

    def test_equal_weights(self):
        """Equal confidence should produce simple average."""
        vision = Observation(
            time={"epoch_ms": 1000},
            source="vision",
            bearing_deg=30.0,
            roi={"x": 100, "y": 100, "w": 50, "h": 50},
            confidence=0.7,
            status="OK",
        )
        audio = Observation(
            time={"epoch_ms": 1000},
            source="audio",
            bearing_deg=50.0,
            roi=None,
            confidence=0.7,
            status="OK",
        )
        result = fuse(vision, audio)

        assert result is not None
        # Equal weights: (30+50)/2 = 40
        assert result.bearing_deg == 40.0

    def test_vision_no_bearing(self):
        """Vision with no bearing should fall back to audio."""
        vision = Observation(
            time={"epoch_ms": 1000},
            source="vision",
            bearing_deg=None,
            roi={"x": 100, "y": 100, "w": 50, "h": 50},
            confidence=0.9,
            status="NO_DETECTION",
        )
        audio = Observation(
            time={"epoch_ms": 1000},
            source="audio",
            bearing_deg=45.0,
            roi=None,
            confidence=0.6,
            status="OK",
        )
        result = fuse(vision, audio)

        assert result is not None
        assert result.bearing_deg == 45.0
        assert result.status == "DEGRADED"

    def test_audio_no_bearing(self):
        """Audio with no bearing should fall back to vision."""
        vision = Observation(
            time={"epoch_ms": 1000},
            source="vision",
            bearing_deg=30.0,
            roi={"x": 100, "y": 100, "w": 50, "h": 50},
            confidence=0.85,
            status="OK",
        )
        audio = Observation(
            time={"epoch_ms": 1000},
            source="audio",
            bearing_deg=None,
            roi=None,
            confidence=0.3,
            status="NO_SIGNAL",
        )
        result = fuse(vision, audio)

        assert result is not None
        assert result.bearing_deg == 30.0
        assert result.status == "DEGRADED"

    def test_both_no_bearing(self):
        """Both with no bearing should return None."""
        vision = Observation(
            time={"epoch_ms": 1000},
            source="vision",
            bearing_deg=None,
            roi=None,
            confidence=None,
            status="NO_DETECTION",
        )
        audio = Observation(
            time={"epoch_ms": 1000},
            source="audio",
            bearing_deg=None,
            roi=None,
            confidence=None,
            status="NO_SIGNAL",
        )
        result = fuse(vision, audio)

        assert result is None

    def test_roi_preserved_from_vision(self):
        """ROI should be preserved from vision source."""
        vision = Observation(
            time={"epoch_ms": 1000},
            source="vision",
            bearing_deg=45.0,
            roi={"x": 200, "y": 150, "w": 60, "h": 80},
            confidence=0.9,
            status="OK",
        )
        audio = Observation(
            time={"epoch_ms": 1000},
            source="audio",
            bearing_deg=50.0,
            roi=None,
            confidence=0.6,
            status="OK",
        )
        result = fuse(vision, audio)

        assert result is not None
        assert result.roi == {"x": 200, "y": 150, "w": 60, "h": 80}

    def test_confidence_max_preserved(self):
        """Result confidence should be max of inputs."""
        vision = Observation(
            time={"epoch_ms": 1000},
            source="vision",
            bearing_deg=45.0,
            roi={"x": 100, "y": 100, "w": 50, "h": 50},
            confidence=0.7,
            status="OK",
        )
        audio = Observation(
            time={"epoch_ms": 1000},
            source="audio",
            bearing_deg=50.0,
            roi=None,
            confidence=0.9,
            status="OK",
        )
        result = fuse(vision, audio)

        assert result is not None
        assert result.confidence == 0.9


class TestObservationDataclass:
    """Tests for Observation dataclass."""

    def test_create_observation(self):
        """Test basic observation creation."""
        obs = Observation(
            time={"epoch_ms": 1000},
            source="test",
            bearing_deg=45.0,
            roi=None,
            confidence=0.8,
            status="OK",
        )
        assert obs.time == {"epoch_ms": 1000}
        assert obs.source == "test"
        assert obs.bearing_deg == 45.0
        assert obs.confidence == 0.8

    def test_extras_default_none(self):
        """Extras should default to None."""
        obs = Observation(
            time={"epoch_ms": 1000},
            source="test",
            bearing_deg=45.0,
            roi=None,
            confidence=0.8,
            status="OK",
        )
        assert obs.extras is None

    def test_extras_with_value(self):
        """Extras can be set."""
        obs = Observation(
            time={"epoch_ms": 1000},
            source="test",
            bearing_deg=45.0,
            roi=None,
            confidence=0.8,
            status="OK",
            extras={"key": "value"},
        )
        assert obs.extras == {"key": "value"}
