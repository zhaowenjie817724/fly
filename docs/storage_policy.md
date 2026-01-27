# Storage & Log Policy (Sprint 6)

## Retention

- Keep the newest N runs (default 5).
- Optionally delete runs older than N days.
- Event snapshots are retained with their run.

## Cleanup

Use:

```
scripts\cleanup_runs.ps1 -KeepLast 5 -DryRun
scripts\cleanup_runs.ps1 -KeepLast 5 -MaxAgeDays 7
```

## Log Structure

Each run:
- events.jsonl / metrics.jsonl
- telemetry/telemetry.jsonl
- observations/*.jsonl
- video/* and audio/* as available
