from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import numpy as np

from .stats import StatsCounter


class CameraCapture:
    def __init__(self, config: dict, output_dir: Path, timebase, logger) -> None:
        self.config = config
        self.output_dir = output_dir
        self.timebase = timebase
        self.logger = logger
        self.stats = StatsCounter()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="camera-capture", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def _run(self) -> None:
        if not self.config.get("enabled", True):
            self.logger.info("Camera disabled")
            return

        mode = self.config.get("mode", "device")
        width = int(self.config.get("width", 1280))
        height = int(self.config.get("height", 720))
        fps = int(self.config.get("fps", 30))
        codec = str(self.config.get("codec", "mp4v"))
        snapshot_interval = float(self.config.get("snapshot_interval_sec", 0))
        device_index = int(self.config.get("device_index", 0))

        video_path = self.output_dir / "video.mp4"
        index_path = self.output_dir / "frame_index.jsonl"
        snapshot_dir = self.output_dir / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        try:
            import cv2
        except Exception as exc:
            self.logger.error("OpenCV not available: %s", exc)
            return

        cap = None
        if mode == "device":
            cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, fps)
            if not cap.isOpened():
                self.logger.error("Failed to open camera device %s", device_index)
                return
        elif mode == "mock":
            cap = None
        else:
            self.logger.error("Unsupported camera mode: %s", mode)
            return

        fourcc = cv2.VideoWriter_fourcc(*codec)
        writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))
        if not writer.isOpened():
            self.logger.error("Failed to open video writer: %s", video_path)
            if cap is not None:
                cap.release()
            return

        frame_id = 0
        last_snapshot = 0.0
        interval_sec = 1.0 / fps if fps > 0 else 0.0
        next_tick = time.perf_counter()

        with index_path.open("w", encoding="utf-8") as index_handle:
            while not self._stop_event.is_set():
                start = time.perf_counter()
                if mode == "mock":
                    frame = np.zeros((height, width, 3), dtype=np.uint8)
                    ret = True
                else:
                    ret, frame = cap.read()

                if not ret:
                    self.stats.drop()
                    time.sleep(0.05)
                    continue

                times = self.timebase.now()
                writer.write(frame)
                write_ms = int((time.perf_counter() - start) * 1000)

                if snapshot_interval > 0:
                    now_wall = time.time()
                    if now_wall - last_snapshot >= snapshot_interval:
                        snapshot_path = snapshot_dir / f"frame_{frame_id:06d}.jpg"
                        cv2.imwrite(str(snapshot_path), frame)
                        last_snapshot = now_wall

                record = {
                    "frame_id": frame_id,
                    "t_mono_ms": times["t_mono_ms"],
                    "t_wall_ms": times["t_wall_ms"],
                    "write_ms": write_ms,
                    "width": int(frame.shape[1]),
                    "height": int(frame.shape[0]),
                }
                index_handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                frame_id += 1
                self.stats.increment()

                if interval_sec > 0:
                    next_tick += interval_sec
                    time.sleep(max(0.0, next_tick - time.perf_counter()))

        writer.release()
        if cap is not None:
            cap.release()
