# Sprint 0 Run Spec

Each run produces a new directory:

runs/<run_id>/

Required files in each run directory:

- manifest.json (config summary + git commit + timestamps)
- telemetry.jsonl (one JSON object per line)
- events.jsonl (may be empty, but must exist)
- metrics.jsonl (may be empty, but must exist)

Notes:

- run_id must be unique per execution
- telemetry.jsonl timestamps must be monotonic increasing
