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
        if mode == "mock":
            self._run_mock()
        elif mode == "vision_live":
            self._run_vision_live()
        elif mode == "fused_live":
            self._run_fused_live()
        else:
            self.logger.error(
                "Unsupported observation mode: %s (supported: mock, vision_live, fused_live, disabled)",
                mode,
            )

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

    def _run_vision_live(self) -> None:
        """Tail vision_yolo.jsonl written by yolo_infer.py and forward to observations.jsonl."""
        poll_interval = float(self.config.get("vision_live_poll_sec", 0.1))
        source_filename = str(self.config.get("vision_live_source", "vision_yolo.jsonl"))

        source_path = self.output_dir / source_filename
        output_path = self.output_dir / "observations.jsonl"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.logger.info("ObservationCapture vision_live: tailing %s", source_path)

        wait_start = time.monotonic()
        while not source_path.exists():
            if self._stop_event.is_set():
                return
            if time.monotonic() - wait_start > 60:
                self.logger.error("vision_live: source file not found after 60s: %s", source_path)
                return
            time.sleep(1.0)

        self.logger.info("ObservationCapture vision_live: source file found, streaming")

        file_pos = 0
        with output_path.open("w", encoding="utf-8") as out_handle:
            while not self._stop_event.is_set():
                with source_path.open("r", encoding="utf-8") as src_handle:
                    src_handle.seek(file_pos)
                    for line in src_handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        out_handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                        out_handle.flush()
                        self.stats.increment()
                    file_pos = src_handle.tell()
                time.sleep(poll_interval)

    def _run_fused_live(self) -> None:
        """实时融合三路观测：vision_yolo + thermal_obs + doa_obs → fused.jsonl。

        每路独立 tail，按最新记录取置信度加权均值方位角。
        某路文件不存在时降级处理（不报错，直接跳过该路信号）。
        """
        from src.fusion.simple_fusion import Observation, fuse3  # 延迟导入避免循环

        poll_interval = float(self.config.get("fused_live_poll_sec", 0.1))
        emit_interval = float(self.config.get("fused_emit_interval_sec", 0.2))
        max_gap_ms = int(self.config.get("fused_max_gap_ms", 600))
        no_signal_interval = float(self.config.get("no_signal_interval_sec", 2.0))

        # 源文件映射：逻辑名 → 文件名
        source_files: dict[str, str] = {
            "vision": "vision_yolo.jsonl",
            "thermal": "thermal_obs.jsonl",
            "audio": "doa_obs.jsonl",
        }

        obs_dir = self.output_dir
        output_path = obs_dir / "fused.jsonl"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        positions: dict[str, int] = {k: 0 for k in source_files}
        latest: dict[str, dict | None] = {k: None for k in source_files}

        last_emit = 0.0
        last_no_signal = 0.0

        self.logger.info("ObservationCapture fused_live: fusing %s", list(source_files.keys()))

        with output_path.open("w", encoding="utf-8") as out_handle:
            while not self._stop_event.is_set():
                now_ms = int(time.time() * 1000)

                # Tail 每个来源文件
                for src, filename in source_files.items():
                    path = obs_dir / filename
                    if not path.exists():
                        continue
                    try:
                        with path.open("r", encoding="utf-8") as f:
                            f.seek(positions[src])
                            for line in f:
                                line = line.strip()
                                if line:
                                    try:
                                        latest[src] = json.loads(line)
                                    except json.JSONDecodeError:
                                        pass
                            positions[src] = f.tell()
                    except OSError:
                        pass

                now = time.time()
                if now - last_emit < emit_interval:
                    time.sleep(poll_interval)
                    continue

                last_emit = now

                # 将最新记录转为 Observation，超时或无信号则置 None
                def to_obs(rec: dict | None) -> Observation | None:
                    if rec is None:
                        return None
                    if rec.get("bearing_deg") is None:
                        return None
                    rec_ms = rec.get("time", {}).get("epoch_ms", 0)
                    if now_ms - rec_ms > max_gap_ms:
                        return None  # 数据过旧
                    return Observation(
                        time=rec.get("time", {}),
                        source=rec.get("source", "unknown"),
                        bearing_deg=rec.get("bearing_deg"),
                        roi=rec.get("roi"),
                        confidence=rec.get("confidence"),
                        status=rec.get("status", "NO_SIGNAL"),
                        extras=rec.get("extras"),
                    )

                vis = to_obs(latest.get("vision"))
                therm = to_obs(latest.get("thermal"))
                aud = to_obs(latest.get("audio"))

                fused = fuse3(vis, therm, aud)

                if fused is not None:
                    record = {
                        "version": "0.1",
                        "time": fused.time,
                        "source": "fusion",
                        "bearing_deg": fused.bearing_deg,
                        "roi": fused.roi,
                        "confidence": fused.confidence,
                        "status": fused.status,
                        "extras": fused.extras,
                    }
                    out_handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                    out_handle.flush()
                    self.stats.increment()
                else:
                    # 全路 NO_SIGNAL，限速发送
                    if now - last_no_signal >= no_signal_interval:
                        record = {
                            "version": "0.1",
                            "time": self.timebase.now(),
                            "source": "fusion",
                            "bearing_deg": None,
                            "roi": None,
                            "confidence": None,
                            "status": "NO_SIGNAL",
                            "extras": {"sources": []},
                        }
                        out_handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                        out_handle.flush()
                        self.stats.increment()
                        last_no_signal = now

                time.sleep(poll_interval)
