from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("Config must be a mapping")
    return data


def read_git_commit(repo_root: Path) -> str:
    head_path = repo_root / ".git" / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "unknown"

    if head.startswith("ref:"):
        ref = head.split(" ", 1)[1].strip()
        ref_path = repo_root / ".git" / ref
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8").strip()

        packed_refs = repo_root / ".git" / "packed-refs"
        if packed_refs.exists():
            for line in packed_refs.read_text(encoding="utf-8").splitlines():
                if not line or line.startswith("#") or line.startswith("^"):
                    continue
                sha, ref_name = line.split(" ", 1)
                if ref_name.strip() == ref:
                    return sha

        return "unknown"

    return head


def make_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def envelope(record_type: str, source: str, payload: dict) -> dict:
    return {
        "version": "0.1",
        "type": record_type,
        "epoch_ms": int(time.time() * 1000),
        "source": source,
        "payload": payload,
    }


def build_manifest(
    run_id: str,
    config_path: Path,
    config: dict,
    git_commit: str,
    start_time: datetime,
    end_time: datetime,
    telemetry_mode: str,
    telemetry_source: str,
    sample_hz: float,
) -> dict:
    return {
        "run_id": run_id,
        "created_at_utc": start_time.isoformat(),
        "finished_at_utc": end_time.isoformat(),
        "git_commit": git_commit,
        "config_path": str(config_path),
        "config": config,
        "telemetry": {
            "mode": telemetry_mode,
            "source_used": telemetry_source,
            "sample_hz": sample_hz,
        },
        "files": {
            "telemetry": "telemetry.jsonl",
            "events": "events.jsonl",
            "metrics": "metrics.jsonl",
        },
    }


def write_mock_telemetry(path: Path, duration_sec: float, interval_sec: float) -> int:
    start = time.time()
    next_tick = start
    seq = 0
    with path.open("w", encoding="utf-8") as handle:
        while time.time() - start < duration_sec:
            payload = {
                "seq": seq,
                "lat": 31.2304 + seq * 0.00001,
                "lon": 121.4737 + seq * 0.00001,
                "alt_m": 10.0 + seq * 0.05,
                "vx": 0.2,
                "vy": 0.0,
                "vz": -0.01,
                "battery_v": 12.2 - seq * 0.001,
                "heading_deg": (seq * 3) % 360,
            }
            record = envelope("telemetry", "mock", payload)
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
            seq += 1
            next_tick += interval_sec
            time.sleep(max(0.0, next_tick - time.time()))
    return seq


def main() -> int:
    parser = argparse.ArgumentParser(description="Sprint 0 dev run")
    parser.add_argument("--config", default="configs/dev.yaml", help="Config file")
    parser.add_argument("--duration", type=float, help="Override duration (sec)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()

    config = load_config(config_path)
    run_cfg = config.get("run", {})
    output_root = run_cfg.get("output_root", "runs")
    duration_sec = float(args.duration) if args.duration is not None else float(run_cfg.get("duration_sec", 20))
    interval_sec = 0.5

    output_root_path = (repo_root / output_root).resolve()
    output_root_path.mkdir(parents=True, exist_ok=True)

    run_id = make_run_id()
    run_dir = output_root_path / run_id
    for _ in range(5):
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            run_id = make_run_id()
            run_dir = output_root_path / run_id
    else:
        raise RuntimeError("Failed to create a unique run directory")

    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    (run_dir / "metrics.jsonl").write_text("", encoding="utf-8")

    telemetry_mode = str(config.get("telemetry", {}).get("mode", "mock"))
    if telemetry_mode != "mock":
        print(f"telemetry.mode={telemetry_mode} not supported in dev_run; using mock telemetry")
    telemetry_source = "mock"

    start_time = datetime.now(timezone.utc)
    sample_count = write_mock_telemetry(run_dir / "telemetry.jsonl", duration_sec, interval_sec)
    end_time = datetime.now(timezone.utc)

    manifest = build_manifest(
        run_id=run_id,
        config_path=config_path,
        config=config,
        git_commit=read_git_commit(repo_root),
        start_time=start_time,
        end_time=end_time,
        telemetry_mode=telemetry_mode,
        telemetry_source=telemetry_source,
        sample_hz=0.0 if duration_sec <= 0 else sample_count / duration_sec,
    )

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    print(f"Run complete: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
