# Sprint 1 Acceptance

## Quick Start (Windows)

1) Create venv and install deps:

python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install -r requirements-dev.txt

2) Start acquisition (30 min by default):

.\scripts\run_acq_dev.bat

3) Replay the latest run:

.\scripts\run_replay.bat

## Expected Outputs

- runs/<run_id>/run_meta.json
- runs/<run_id>/video/video.mp4
- runs/<run_id>/video/frame_index.jsonl
- runs/<run_id>/telemetry/telemetry.jsonl
- runs/<run_id>/audio/audio.wav (if audio enabled)
- runs/<run_id>/audio/audio_index.jsonl (if audio enabled)

## Required Logs

Every 5 seconds the console log should show:

- video fps and dropped frames
- audio block count and overrun count (if enabled)
- telemetry message rate and drop count

## Common Issues

- No camera: set camera.mode to mock
- No microphone: set audio.mode to disabled or wav_file
- No MAVLink: set telemetry.mode to mock
