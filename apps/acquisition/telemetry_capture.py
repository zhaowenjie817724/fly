from __future__ import annotations

import json
import math
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
        fault_after = float(self.config.get("fault_after_sec", 0))
        fault_duration = float(self.config.get("fault_duration_sec", 0))
        telemetry_path = self.output_dir / "telemetry.jsonl"
        seq = 0
        next_tick = time.perf_counter()
        start_time = time.monotonic()
        fault_active = False
        with telemetry_path.open("w", encoding="utf-8") as handle:
            while not self._stop_event.is_set():
                elapsed = time.monotonic() - start_time
                if fault_after > 0 and fault_duration > 0 and fault_after <= elapsed < fault_after + fault_duration:
                    if not fault_active:
                        self.logger.warning("Telemetry fault injected (drop messages)")
                    fault_active = True
                else:
                    if fault_active:
                        self.logger.info("Telemetry fault cleared")
                    fault_active = False

                if fault_active:
                    self.stats.drop()
                    time.sleep(0.05)
                    continue

                times = self.timebase.now()
                record = {
                    "version": "0.1",
                    "time": times,
                    "link_status": "OK",
                    "battery": {
                        "voltage_v": round(12.2 - seq * 0.001, 3),
                        "remaining_pct": max(0, 100 - seq),
                    },
                    "attitude": {
                        "roll_deg": 0.5,
                        "pitch_deg": -1.0,
                        "yaw_deg": float((seq * 3) % 360),
                    },
                    "gps": {
                        "lat": 31.2304 + seq * 0.00001,
                        "lon": 121.4737 + seq * 0.00001,
                        "alt_m": 10.0 + seq * 0.05,
                    },
                }
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                self.stats.increment()
                seq += 1
                next_tick += interval
                time.sleep(max(0.0, next_tick - time.perf_counter()))

    def _run_mavlink(self, mavutil, conn_str: str, baud: int | None = None) -> None:
        telemetry_path = self.output_dir / "telemetry.jsonl"
        emit_hz = float(self.config.get("emit_hz", 2))
        emit_interval = 1.0 / emit_hz if emit_hz > 0 else 0.0
        degraded_after = float(self.config.get("link_degraded_after_sec", 2.0))
        lost_after = float(self.config.get("link_lost_after_sec", 5.0))

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
            last_msg = time.monotonic()
            last_emit = 0.0
            link_status = "OK"
            state: dict[str, dict | None] = {"battery": None, "attitude": None, "gps": None}

            with telemetry_path.open("a", encoding="utf-8") as handle:
                while not self._stop_event.is_set():
                    now = time.monotonic()
                    msg = master.recv_match(blocking=True, timeout=1)
                    if msg and msg.get_type() != "BAD_DATA":
                        last_msg = now
                        msg_type = msg.get_type()
                        battery = self._battery_from_msg(msg_type, msg)
                        if battery:
                            state["battery"] = battery
                        attitude = self._attitude_from_msg(msg_type, msg)
                        if attitude:
                            state["attitude"] = attitude
                        gps = self._gps_from_msg(msg_type, msg)
                        if gps:
                            state["gps"] = gps

                    since_last = now - last_msg
                    desired_status = "OK"
                    if lost_after > 0 and since_last >= lost_after:
                        desired_status = "LOST"
                    elif degraded_after > 0 and since_last >= degraded_after:
                        desired_status = "DEGRADED"

                    should_emit = False
                    if desired_status != link_status:
                        link_status = desired_status
                        should_emit = True
                    if emit_interval > 0 and now - last_emit >= emit_interval:
                        should_emit = True

                    if should_emit:
                        times = self.timebase.now()
                        record = {
                            "version": "0.1",
                            "time": times,
                            "link_status": link_status,
                        }
                        if state["battery"]:
                            record["battery"] = state["battery"]
                        if state["attitude"]:
                            record["attitude"] = state["attitude"]
                        if state["gps"]:
                            record["gps"] = state["gps"]
                        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                        self.stats.increment()
                        last_emit = now
            time.sleep(1)

    def _battery_from_msg(self, msg_type: str, msg) -> dict | None:
        if msg_type != "SYS_STATUS":
            return None
        voltage_mv = getattr(msg, "voltage_battery", None)
        remaining = getattr(msg, "battery_remaining", None)
        battery = {}
        if voltage_mv is not None and voltage_mv >= 0:
            battery["voltage_v"] = round(voltage_mv / 1000.0, 3)
        if remaining is not None and remaining >= 0:
            battery["remaining_pct"] = int(remaining)
        return battery or None

    def _attitude_from_msg(self, msg_type: str, msg) -> dict | None:
        if msg_type != "ATTITUDE":
            return None
        return {
            "roll_deg": math.degrees(msg.roll),
            "pitch_deg": math.degrees(msg.pitch),
            "yaw_deg": math.degrees(msg.yaw),
        }

    def _gps_from_msg(self, msg_type: str, msg) -> dict | None:
        if msg_type == "GLOBAL_POSITION_INT":
            return {
                "lat": msg.lat / 1e7,
                "lon": msg.lon / 1e7,
                "alt_m": msg.relative_alt / 1000.0,
            }
        if msg_type == "GPS_RAW_INT":
            return {
                "lat": msg.lat / 1e7,
                "lon": msg.lon / 1e7,
                "alt_m": msg.alt / 1000.0,
            }
        return None
