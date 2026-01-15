from __future__ import annotations

import json
import platform
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .git_info import read_git_commit


def make_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


@dataclass
class RunPaths:
    root: Path
    video: Path
    audio: Path
    telemetry: Path


class RunManager:
    def __init__(self, repo_root: Path, output_root: Path, config: dict):
        self.repo_root = repo_root
        self.output_root = output_root
        self.config = config
        self.run_id = make_run_id()
        self.paths = self._create_paths()
        self.meta_path = self.paths.root / "run_meta.json"

    def _create_paths(self) -> RunPaths:
        self.output_root.mkdir(parents=True, exist_ok=True)
        run_dir = self.output_root / self.run_id
        for _ in range(5):
            try:
                run_dir.mkdir(parents=True, exist_ok=False)
                break
            except FileExistsError:
                self.run_id = make_run_id()
                run_dir = self.output_root / self.run_id
        else:
            raise RuntimeError("Failed to create a unique run directory")

        video_dir = run_dir / "video"
        audio_dir = run_dir / "audio"
        telemetry_dir = run_dir / "telemetry"
        video_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)
        telemetry_dir.mkdir(parents=True, exist_ok=True)

        return RunPaths(root=run_dir, video=video_dir, audio=audio_dir, telemetry=telemetry_dir)

    def write_meta(self, extra: dict | None = None) -> None:
        meta = {
            "run_id": self.run_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "git_commit": read_git_commit(self.repo_root),
            "host": {
                "platform": platform.platform(),
                "python": sys.version.replace("\n", " "),
            },
            "config": self.config,
        }
        if extra:
            meta["extra"] = extra

        self.meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
