from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

def _add_repo_to_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


repo_root = _add_repo_to_path()

from apps.acquisition.config_utils import load_config  # noqa: E402
from src.fusion.simple_fusion import Observation, fuse  # noqa: E402


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


def load_observations(obs_dir: Path) -> list[dict]:
    records: list[dict] = []
    if not obs_dir.exists():
        return records
    for path in obs_dir.glob("*.jsonl"):
        if path.name == "fused.jsonl":
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                records.append(record)
    records.sort(key=get_mono_ms)
    return records


def to_obs(record: dict) -> Observation:
    return Observation(
        time=record.get("time", {}),
        source=str(record.get("source", "")),
        bearing_deg=record.get("bearing_deg"),
        roi=record.get("roi"),
        confidence=record.get("confidence"),
        status=str(record.get("status", "")),
        extras=record.get("extras"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fuse observations offline (Sprint 4)")
    parser.add_argument("--config", default="configs/fsm.yaml", help="Config file")
    parser.add_argument("--run", default="latest", help="Run id/path for output")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()
    config = load_config(config_path)
    fuse_cfg = config.get("fusion", {})
    window_ms = int(fuse_cfg.get("max_gap_ms", 200))

    runs_root = repo_root / "runs"
    if args.run == "latest":
        run_dirs = [p for p in runs_root.iterdir() if p.is_dir()] if runs_root.exists() else []
        if not run_dirs:
            raise RuntimeError("No runs found for --run latest")
        run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        run_dir = run_dirs[0]
    else:
        run_dir = Path(args.run)
        if not run_dir.is_absolute():
            run_dir = runs_root / args.run
        if not run_dir.exists():
            raise RuntimeError(f"Run not found: {run_dir}")

    obs_dir = run_dir / "observations"
    records = load_observations(obs_dir)
    if not records:
        raise RuntimeError("No observations found to fuse")

    latest: dict[str, Observation] = {}
    fused_path = obs_dir / "fused.jsonl"
    with fused_path.open("w", encoding="utf-8") as handle:
        for record in records:
            obs = to_obs(record)
            latest[obs.source] = obs
            vision = latest.get("vision")
            audio = latest.get("audio")
            if vision and audio:
                delta = abs(get_mono_ms({"time": vision.time}) - get_mono_ms({"time": audio.time}))
                if delta > window_ms:
                    continue
            fused = fuse(vision, audio)
            if not fused:
                continue
            payload = {
                "version": "0.1",
                "time": fused.time,
                "source": "fusion",
                "bearing_deg": fused.bearing_deg,
                "roi": fused.roi,
                "confidence": fused.confidence,
                "status": fused.status,
                "extras": fused.extras or {},
            }
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
