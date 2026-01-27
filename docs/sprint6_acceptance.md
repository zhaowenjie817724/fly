# Sprint 6 Acceptance (PC)

## Fault Injection

Inject camera/audio/telemetry dropouts by adding to `configs/dev.yaml`:

```
camera:
  fault_after_sec: 10
  fault_duration_sec: 5
audio:
  fault_after_sec: 10
  fault_duration_sec: 5
telemetry:
  fault_after_sec: 10
  fault_duration_sec: 5
```

Then run:

```
scripts\run_acq_dev.bat
```

Expect:
- Drop warnings in logs
- No crash; run completes

## WS Disconnect

- Start `apps/service/server.py`
- Kill the process; reconnect from client; server restart should be clean

## Mission Planner Disconnect

- Stop SITL; telemetry link should degrade to LOST in logs

## Cleanup

```
scripts\cleanup_runs.ps1 -KeepLast 5 -DryRun
```

## Run Validation

```
scripts\validate_run.ps1 -Run latest
```
