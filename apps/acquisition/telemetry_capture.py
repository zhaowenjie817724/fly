from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .stats import StatsCounter


class TelemetryCapture:
    def __init__(self, config: dict, output_dir: Path, timebase, logger) -> None:
        self.config = config
        self.output_dir = output_dir
        self.timebase = timebase
        self.logger = logger
        self.stats = StatsCounter()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="telemetry-capture", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def _run(self) -> None:
        if not self.config.get("enabled", True):
            self.logger.info("Telemetry disabled")
            return

        mode = self.config.get("mode", "mock")
        if mode == "mock":
            self._run_mock()
            return

        try:
            from pymavlink import mavutil
        except Exception as exc:
            self.logger.error("pymavlink not available: %s", exc)
            return

        if mode == "mavlink_udp":
            conn_str = self.config.get("mavlink", {}).get("udp")
            if not conn_str:
                self.logger.error("telemetry.mavlink.udp is required")
                return
            self._run_mavlink(mavutil, conn_str)
        elif mode == "mavlink_serial":
            mav_cfg = self.config.get("mavlink", {})
            port = mav_cfg.get("serial_port")
            baud = int(mav_cfg.get("baud", 115200))
            if not port:
                self.logger.error("telemetry.mavlink.serial_port is required")
                return
            self._run_mavlink(mavutil, port, baud=baud)
        else:
            self.logger.error("Unsupported telemetry mode: %s", mode)

    def _run_mock(self) -> None:
        hz = float(self.config.get("mock_hz", 2))
        interval = 1.0 / hz if hz > 0 else 1.0
        telemetry_path = self.output_dir / "telemetry.jsonl"
        seq = 0
        next_tick = time.perf_counter()
        with telemetry_path.open("w", encoding="utf-8") as handle:
            while not self._stop_event.is_set():
                times = self.timebase.now()
                payload = {
                    "seq": seq,
                    "lat": 31.2304 + seq * 0.00001,
                    "lon": 121.4737 + seq * 0.00001,
                    "alt_m": 10.0 + seq * 0.05,
                    "battery_v": 12.2 - seq * 0.001,
                }
                record = {
                    "t_mono_ms": times["t_mono_ms"],
                    "t_wall_ms": times["t_wall_ms"],
                    "msg_type": "MOCK",
                    "payload": payload,
                }
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                self.stats.increment()
                seq += 1
                next_tick += interval
                time.sleep(max(0.0, next_tick - time.perf_counter()))

    def _run_mavlink(self, mavutil, conn_str: str, baud: int | None = None) -> None:
        telemetry_path = self.output_dir / "telemetry.jsonl"
        while not self._stop_event.is_set():
            try:
                if baud is None:
                    master = mavutil.mavlink_connection(conn_str)
                else:
                    master = mavutil.mavlink_connection(conn_str, baud=baud)
            except Exception as exc:
                self.logger.error("MAVLink connection failed: %s", exc)
                time.sleep(2)
                continue

            self.logger.info("Waiting for heartbeat...")
            heartbeat = master.wait_heartbeat(timeout=10)
            if not heartbeat:
                self.logger.warning("No heartbeat received. Retrying...")
                time.sleep(2)
                continue

            self.logger.info("Heartbeat received. Streaming telemetry...")
            with telemetry_path.open("a", encoding="utf-8") as handle:
                while not self._stop_event.is_set():
                    msg = master.recv_match(blocking=True, timeout=1)
                    if not msg:
                        continue
                    if msg.get_type() == "BAD_DATA":
                        continue
                    times = self.timebase.now()
                    record = {
                        "t_mono_ms": times["t_mono_ms"],
                        "t_wall_ms": times["t_wall_ms"],
                        "msg_type": msg.get_type(),
                        "payload": msg.to_dict(),
                    }
                    handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                    self.stats.increment()
            time.sleep(1)
