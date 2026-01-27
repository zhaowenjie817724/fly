# MAVLink Ports Plan (PC-equivalent)

## Target Ports

- Ground station (Mission Planner): UDP 14550
- Local companion software (this repo): UDP 14551
- Command bridge (miniapp -> MAVLink): UDP 14552 (optional)

## Option A: SITL multi-endpoint (recommended on PC)

Example (ArduPilot SITL):

```
sim_vehicle.py -v ArduCopter \
  --out=udp:127.0.0.1:14550 \
  --out=udp:127.0.0.1:14551 \
  --out=udp:127.0.0.1:14552
```

Mission Planner connects to `udp:127.0.0.1:14550`.
This repo uses `telemetry.mavlink.udp = udp:127.0.0.1:14551`.

## Option B: mavlink-router fan-out

Use mavlink-router to forward a single upstream link to two UDP ports.
See `configs/mavlink-router.conf` for a starter config template.

Notes:
- Keep GCS on 14550, telemetry capture on 14551, and command bridge on 14552.
- Avoid binding multiple processes to the same UDP port to prevent conflicts.
