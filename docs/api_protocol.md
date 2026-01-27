# API Protocol (Sprint 5)

## WebSocket `/ws`

Server sends JSON messages:

```
{ "type": "telemetry", "payload": { ...TelemetryMsg... } }
{ "type": "event", "payload": { ...EventMsg... } }
{ "type": "observation:<stream>", "payload": { ...ObservationMsg... } }
{ "type": "status", "payload": { "link_status": "OK|DEGRADED|LOST|UNKNOWN", "telemetry_age_sec": 0.5, "gcs_label": "地面站" } }
```

## HTTP

### `GET /health`
Returns `{ "status": "ok" }`.

### `GET /status`
Returns active run paths and link status.

### `POST /command`
Body example:

```
{ "type": "SET_YAW", "params": { "yaw_deg": 10, "duration_ms": 500 } }
```

Appends to `runs/<run_id>/commands.jsonl`.
