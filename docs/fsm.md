# FSM Design (Sprint 4)

## States

- SEARCH: waiting for observations
- SCAN: yaw toward bearing from observation
- LOCKED: stable target tracking
- DEGRADED: fallback after lost target, then return to SEARCH

## Transitions

```
SEARCH -> SCAN      (observation OK)
SCAN -> LOCKED      (confidence >= lock_conf)
SCAN/LOCKED -> DEGRADED  (lost_timeout)
DEGRADED -> SEARCH  (after stop)
```

## Safety Rules

- Command whitelist: SET_YAW / SET_MODE / STOP
- Rate limit: <= 5Hz (configurable)
- TTL: no command for >1s triggers stop/hold
- Link lost: block all commands
- Audio-only observation triggers scan; vision confirms lock
- Commands are logged to commands.jsonl for audit

## Control Outputs

- Yaw: MAV_CMD_CONDITION_YAW
- Stop: mode to LOITER/HOLD
