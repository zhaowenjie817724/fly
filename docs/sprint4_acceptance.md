# Sprint 4 Acceptance (PC)

## Quick Start

1) Fuse observations:

```
python apps/fusion/fuse_replay.py --config configs/fsm.yaml --run latest
```

2) Run FSM (dry run):

```
python apps/control/fsm_runner.py --config configs/fsm.yaml --run latest --dry-run
```

3) Run FSM with SITL:

```
python apps/control/fsm_runner.py --config configs/fsm.yaml --run latest
```

## Expected Outputs

- runs/<run_id>/observations/fused.jsonl
- runs/<run_id>/events.jsonl (MODE_CHANGED / TARGET_LOST)
- runs/<run_id>/commands.jsonl (command audit)

## Notes

- Keep Mission Planner on UDP 14550 and control on UDP 14551.
- Use `--dry-run` to validate logic without MAVLink commands.
