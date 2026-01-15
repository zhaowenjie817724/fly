# Sprint 0 Architecture and Interface v0.1

## Modules (minimal, for alignment)

- TelemetryCapture: read MAVLink or mock telemetry
- VideoCapture: placeholder (future)
- AudioCapture: placeholder (future)
- Perception-Vision: placeholder (future)
- Perception-Audio: placeholder (future)
- Fusion: placeholder (future)
- FSM/Decision: placeholder (future)
- Control: placeholder (future)
- Service/API: placeholder (future)
- Logger/Storage: write run artifacts to disk

## Message Envelope (JSONL)

All JSONL records must follow this envelope:

{
  "version": "0.1",
  "type": "telemetry|observation|event|command",
  "epoch_ms": 1730000000000,
  "source": "mock|mavlink|vision|audio|fusion",
  "payload": {}
}

## Ports and Protocols (Sprint 0 minimum)

- Sprint 0 requires only local disk logging and replay from runs/<run_id>/
- Live streaming (WS/HTTP) is deferred to later sprints

## Versioning Rules

- Every message must include a version field
- Any schema change or semantic change requires a version bump (0.1 -> 0.2)
