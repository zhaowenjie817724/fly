from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .stats import StatsCounter


class ObservationCapture:
    def __init__(self, config: dict, output_dir: Path, timebase, logger) -> None:
        self.config = config
        self.output_dir = output_dir
        self.timebase = timebase
        self.logger = logger
        self.stats = StatsCounter()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="observation-capture", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def _run(self) -> None:
        if not self.config.get("enabled", True):
            self.logger.info("Observation disabled")
            return

        mode = self.config.get("mode", "mock")
        if mode == "disabled":
            self.logger.info("Observation mode disabled")
            return
        if mode != "mock":
            self.logger.error("Unsupported observation mode: %s", mode)
            return

        self._run_mock()

    def _run_mock(self) -> None:
        hz = float(self.config.get("mock_hz", 1))
        interval = 1.0 / hz if hz > 0 else 1.0
        source = str(self.config.get("mock_source", "vision"))
        status = str(self.config.get("mock_status", "NO_SIGNAL")).upper()
        bearing_start = float(self.config.get("mock_bearing_deg_start", 0.0))
        bearing_step = float(self.config.get("mock_bearing_deg_step", 10.0))
        confidence = float(self.config.get("mock_confidence", 0.5))
        roi = self.config.get(
            "mock_roi",
            {"x": 320, "y": 180, "w": 200, "h": 200, "frame_w": 1280, "frame_h": 720},
        )

        output_path = self.output_dir / "observations.jsonl"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        seq = 0
        next_tick = time.perf_counter()
        with output_path.open("w", encoding="utf-8") as handle:
            while not self._stop_event.is_set():
                times = self.timebase.now()
                bearing = None
                use_roi = None
                use_conf = None
                if status == "OK":
                    bearing = (bearing_start + seq * bearing_step) % 360
                    use_roi = roi
                    use_conf = confidence
                record = {
                    "version": "0.1",
                    "time": times,
                    "source": source,
                    "bearing_deg": bearing,
                    "roi": use_roi,
                    "confidence": use_conf,
                    "status": status,
                    "extras": {"mock_seq": seq},
                }
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                self.stats.increment()
                seq += 1
                next_tick += interval
                time.sleep(max(0.0, next_tick - time.perf_counter()))
