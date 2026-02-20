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
    """两路融合：视觉 + 音频（保留原有接口）。"""
    return fuse3(vision, None, audio)


def fuse3(
    vision: Observation | None,
    thermal: Observation | None,
    audio: Observation | None,
) -> Observation | None:
    """三路融合：视觉 + 热成像 + 音频。

    方位角计算采用置信度加权均值。
    信号质量策略：
      - 2 路及以上有效 → status="OK"
      - 仅 1 路有效    → status="DEGRADED"
      - 全部无信号     → None
    """
    # 收集有效来源（bearing 不为 None 且状态 OK）
    candidates: list[tuple[str, Observation]] = []
    for src, obs in (("vision", vision), ("thermal", thermal), ("audio", audio)):
        if obs is not None and obs.bearing_deg is not None:
            candidates.append((src, obs))

    if not candidates:
        return None

    total_w = sum(_weight(obs.confidence) for _, obs in candidates)
    if total_w <= 0:
        return None

    bearing = sum(obs.bearing_deg * _weight(obs.confidence) for _, obs in candidates) / total_w
    max_conf = max(_weight(obs.confidence) for _, obs in candidates)
    sources_used = [src for src, _ in candidates]

    # 时间戳：优先视觉，其次热成像，最后音频
    time_obj: dict = {}
    for preferred in ("vision", "thermal", "audio"):
        for src, obs in candidates:
            if src == preferred:
                time_obj = obs.time
                break
        if time_obj:
            break

    # ROI：优先视觉，其次热成像
    roi = None
    for src, obs in candidates:
        if src in ("vision", "thermal") and obs.roi is not None:
            roi = obs.roi
            break

    status = "OK" if len(candidates) >= 2 else "DEGRADED"

    return Observation(
        time=time_obj,
        source="fusion",
        bearing_deg=round(bearing, 2),
        roi=roi,
        confidence=round(max_conf, 3),
        status=status,
        extras={"sources": sources_used},
    )
