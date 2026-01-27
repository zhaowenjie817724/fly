# Architecture & Interface Specification v0.2

## 1. Purpose

This document freezes the v0.2 interfaces and PC-equivalent port plan so Sprint 1 development can proceed without hardware.

Key principles:
- Clear module boundaries (no direct shared state)
- Message contract first
- Degradation paths defined
- Replayable logs with stable schemas

## 2. System Boundary

- Companion Computer: runs this repo (PC now, SBC later)
- Flight Controller: MAVLink connection
- Sensors: camera / mic array (optional)
- External client: Mission Planner / future mini program

## 3. Module Map (unchanged)

See v0.1 for full module table. v0.2 keeps the same module boundaries.

## 4. Ports & Protocols (PC-equivalent)

MAVLink UDP plan (PC + SITL):
- `udp:127.0.0.1:14550` -> Ground station (Mission Planner)
- `udp:127.0.0.1:14551` -> Companion app (this repo)

Recommended routing:
- SITL outputs to 14550 and 14551 directly (multi-endpoint), or
- Use `mavlink-router` to fan-out to both ports.

This avoids link contention and keeps Mission Planner and local software running in parallel.

## 5. Message Spec v0.2

### 5.1 Common
All messages include:
- `version`: "0.1"
- `time`:
  - `epoch_ms`: int64 (Unix ms)
  - `mono_ms`: int64 (monotonic ms)

### 5.2 ObservationMsg
Fields:
- `version`
- `time`
- `source`: "vision" | "audio" | "thermal" | "fusion"
- `bearing_deg`: float | null (0-360, forward=0, clockwise positive)
- `roi`: object | null (x, y, w, h, frame_w, frame_h)
- `confidence`: float | null (0-1)
- `status`: "OK" | "DEGRADED" | "INVALID" | "NO_SIGNAL"
- `extras`: object (optional)

### 5.3 TelemetryMsg
Fields:
- `version`
- `time`
- `link_status`: "OK" | "DEGRADED" | "LOST"
- `battery` (optional): { voltage_v, remaining_pct }
- `attitude` (optional): { roll_deg, pitch_deg, yaw_deg }
- `gps` (optional): { lat, lon, alt_m }

### 5.4 CommandMsg / EventMsg
Same as v0.1 (no schema changes).

## 6. Run Logging v0.2

Each run creates:

```
runs/<run_id>/
  run_meta.json
  events.jsonl
  metrics.jsonl
  video/video.mp4
  video/frame_index.jsonl
  audio/audio.wav
  audio/audio_index.jsonl
  telemetry/telemetry.jsonl
  observations/observations.jsonl
```

Notes:
- JSONL records use monotonic time for replay ordering.
- Extra files are allowed, but core files must exist for tooling to work.
