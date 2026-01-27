from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Observation:
    time: dict
    source: str
    bearing_deg: float | None
    roi: dict | None
    confidence: float | None
    status: str
    extras: dict | None = None


def _weight(conf: float | None) -> float:
    if conf is None:
        return 0.5
    return max(0.05, min(1.0, conf))


def fuse(vision: Observation | None, audio: Observation | None) -> Observation | None:
    if not vision and not audio:
        return None

    if vision and audio and vision.bearing_deg is not None and audio.bearing_deg is not None:
        wv = _weight(vision.confidence)
        wa = _weight(audio.confidence)
        bearing = (vision.bearing_deg * wv + audio.bearing_deg * wa) / (wv + wa)
        return Observation(
            time=vision.time,
            source="fusion",
            bearing_deg=bearing,
            roi=vision.roi,
            confidence=max(_weight(vision.confidence), _weight(audio.confidence)),
            status="OK",
            extras={"sources": ["vision", "audio"]},
        )

    if vision and vision.bearing_deg is not None:
        return Observation(
            time=vision.time,
            source="fusion",
            bearing_deg=vision.bearing_deg,
            roi=vision.roi,
            confidence=vision.confidence,
            status="DEGRADED",
            extras={"sources": ["vision"]},
        )

    if audio and audio.bearing_deg is not None:
        return Observation(
            time=audio.time,
            source="fusion",
            bearing_deg=audio.bearing_deg,
            roi=None,
            confidence=audio.confidence,
            status="DEGRADED",
            extras={"sources": ["audio"]},
        )

    return None
