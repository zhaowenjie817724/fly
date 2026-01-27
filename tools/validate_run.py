from __future__ import annotations

import argparse
import json
from pathlib import Path


def get_mono_ms(record: dict) -> int | None:
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
    return None


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records
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


def check_monotonic(path: Path) -> tuple[int, int]:
    records = load_jsonl(path)
    if not records:
        return 0, 0
    last = None
    violations = 0
    for record in records:
        mono = get_mono_ms(record)
        if mono is None:
            continue
        if last is not None and mono < last:
            violations += 1
        last = mono
    return len(records), violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate run artifacts")
    parser.add_argument("--run", default="latest", help="Run id/path")
    parser.add_argument("--strict", action="store_true", help="Fail on missing optional files")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    runs_root = repo_root / "runs"
    if args.run == "latest":
        run_dirs = [p for p in runs_root.iterdir() if p.is_dir()] if runs_root.exists() else []
        if not run_dirs:
            print("No runs found")
            return 1
        run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        run_dir = run_dirs[0]
    else:
        run_dir = Path(args.run)
        if not run_dir.is_absolute():
            run_dir = runs_root / args.run
        if not run_dir.exists():
            print(f"Run not found: {run_dir}")
            return 1

    required = [
        run_dir / "events.jsonl",
        run_dir / "metrics.jsonl",
        run_dir / "telemetry" / "telemetry.jsonl",
    ]
    optional = [
        run_dir / "run_meta.json",
        run_dir / "video" / "video.mp4",
        run_dir / "video" / "frame_index.jsonl",
        run_dir / "audio" / "audio.wav",
        run_dir / "audio" / "audio_index.jsonl",
    ]
    obs_dir = run_dir / "observations"
    if obs_dir.exists():
        optional.extend(list(obs_dir.glob("*.jsonl")))

    ok = True
    for path in required:
        if not path.exists():
            print(f"Missing required: {path}")
            ok = False

    for path in optional:
        if not path.exists():
            if args.strict:
                print(f"Missing optional: {path}")
                ok = False
            else:
                print(f"Missing optional: {path}")

    for path in required:
        count, violations = check_monotonic(path)
        print(f"{path.name}: records={count} monotonic_violations={violations}")
        if violations > 0:
            ok = False

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
