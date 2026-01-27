from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path


def should_delete(path: Path, keep_last: int, max_age_days: float | None, index: int) -> bool:
    if index >= keep_last:
        return True
    if max_age_days is None:
        return False
    age_sec = time.time() - path.stat().st_mtime
    return age_sec > (max_age_days * 86400)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup old runs")
    parser.add_argument("--runs", default="runs", help="Runs root")
    parser.add_argument("--keep-last", type=int, default=5, help="Keep newest N runs")
    parser.add_argument("--max-age-days", type=float, default=None, help="Delete runs older than N days")
    parser.add_argument("--dry-run", action="store_true", help="Show deletions without removing")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    runs_root = Path(args.runs)
    if not runs_root.is_absolute():
        runs_root = (repo_root / runs_root).resolve()
    if not runs_root.exists():
        print(f"No runs directory: {runs_root}")
        return 0

    run_dirs = [p for p in runs_root.iterdir() if p.is_dir()]
    run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for idx, run_dir in enumerate(run_dirs):
        if should_delete(run_dir, args.keep_last, args.max_age_days, idx):
            if args.dry_run:
                print(f"Would delete: {run_dir}")
            else:
                print(f"Deleting: {run_dir}")
                shutil.rmtree(run_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
