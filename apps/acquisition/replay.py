from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def get_mono_ms(record: dict) -> int:
    time_obj = record.get("time")
    if isinstance(time_obj, dict):
        mono = time_obj.get("mono_ms")
        if mono is None:
            mono = time_obj.get("t_mono_ms")
        if mono is not None:
            return int(mono)
    if "mono_ms" in record:
        return int(record["mono_ms"])
    if "t_mono_ms" in record:
        return int(record["t_mono_ms"])
    return 0


def find_latest_run(runs_root: Path) -> Path | None:
    if not runs_root.exists():
        return None
    candidates = [p for p in runs_root.iterdir() if p.is_dir()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def build_events(run_dir: Path) -> list[dict]:
    events = []
    video_index = run_dir / "video" / "frame_index.jsonl"
    audio_index = run_dir / "audio" / "audio_index.jsonl"
    telemetry_path = run_dir / "telemetry" / "telemetry.jsonl"
    observations_dir = run_dir / "observations"
    event_path = run_dir / "events.jsonl"

    for record in load_jsonl(video_index):
        events.append({"stream": "video", **record})
    for record in load_jsonl(audio_index):
        events.append({"stream": "audio", **record})
    for record in load_jsonl(telemetry_path):
        events.append({"stream": "telemetry", **record})
    if observations_dir.exists():
        for obs_file in observations_dir.glob("*.jsonl"):
            for record in load_jsonl(obs_file):
                events.append({"stream": f"observation:{obs_file.stem}", **record})
    for record in load_jsonl(event_path):
        events.append({"stream": "event", **record})

    events.sort(key=get_mono_ms)
    return events


def replay_events(events: list[dict], speed: float, output_path: Path | None) -> None:
    if not events:
        print("No events to replay")
        return

    handle = None
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        handle = output_path.open("w", encoding="utf-8")

    start_mono = get_mono_ms(events[0])
    start_time = time.perf_counter()

    for event in events:
        t_mono = get_mono_ms(event) or start_mono
        if speed > 0:
            target_elapsed = (t_mono - start_mono) / 1000.0 / speed
            while True:
                now = time.perf_counter() - start_time
                if now >= target_elapsed:
                    break
                time.sleep(0.001)
        line = json.dumps(event, ensure_ascii=True)
        if handle:
            handle.write(line + "\n")
        else:
            print(line)

    if handle:
        handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a recorded run")
    parser.add_argument("--run", default="latest", help="Run id or path, or 'latest'")
    parser.add_argument("--speed", type=float, default=1.0, help="Replay speed (0=fast)")
    parser.add_argument("--output", help="Optional JSONL output path")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    runs_root = repo_root / "runs"

    if args.run == "latest":
        run_dir = find_latest_run(runs_root)
        if not run_dir:
            print("No runs found")
            return 1
    else:
        run_path = Path(args.run)
        run_dir = run_path if run_path.is_dir() else runs_root / args.run
        if not run_dir.exists():
            print(f"Run not found: {run_dir}")
            return 1

    events = build_events(run_dir)
    output_path = Path(args.output) if args.output else None
    replay_events(events, args.speed, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
