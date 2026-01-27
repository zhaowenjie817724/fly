# Mission Planner + SITL (PC-equivalent)

## Goal

Verify Mission Planner telemetry link and tlog recording while the local app connects to a separate UDP port.

## Steps (SITL multi-endpoint)

1) Start ArduPilot SITL with multiple outputs:

```
sim_vehicle.py -v ArduCopter \
  --out=udp:127.0.0.1:14550 \
  --out=udp:127.0.0.1:14551 \
  --out=udp:127.0.0.1:14552
```

2) Mission Planner:
- Connect to `udp:127.0.0.1:14550`
- Start tlog recording (Data -> TLog)

3) Local app:
- Set `telemetry.mode = mavlink_udp`
- Set `telemetry.mavlink.udp = udp:127.0.0.1:14551`
- Run `python apps/acquisition/run_acq.py --config configs/pc_mavlink.yaml`

4) Optional command bridge (Miniapp -> MAVLink):
- Use `configs/control_bridge.yaml` with `udp:127.0.0.1:14552`
- Run `python apps/control/command_bridge.py --config configs/control_bridge.yaml --run latest`

## Notes
- Keep GCS, telemetry capture, and command bridge on separate ports.
- If you must use mavlink-router, see `docs/MAVLink_Ports_Plan.md`.
