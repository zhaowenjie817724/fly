# Sprint 0 Run Spec (v0.2)

Each run produces a new directory:

```
runs/<run_id>/
```

## Minimal Sprint 0 (dev_run.py)

Required files:
- manifest.json (config summary + git commit + timestamps)
- telemetry.jsonl (one JSON object per line)
- events.jsonl (may be empty, but must exist)
- metrics.jsonl (may be empty, but must exist)

## Sprint 1+ Acquisition (run_acq.py)

Required files:
- run_meta.json
- events.jsonl (may be empty, but must exist)
- metrics.jsonl (may be empty, but must exist)
- telemetry/telemetry.jsonl
- observations/observations.jsonl
- video/video.mp4
- video/frame_index.jsonl
- audio/audio.wav (if enabled)
- audio/audio_index.jsonl (if enabled)

Notes:
- run_id must be unique per execution
- JSONL records use monotonic time for replay ordering
