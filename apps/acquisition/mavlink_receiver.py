"""
MAVLink 遥测接收器
实时接收来自Mission Planner/SITL的遥测数据并写入JSONL

功能：
- 接收姿态、位置、电池、系统状态
- 自动重连
- 写入telemetry.jsonl供后端服务读取
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from queue import Queue


def _add_repo_to_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


repo_root = _add_repo_to_path()

from src.common.timebase import TimeBase  # noqa: E402


@dataclass
class TelemetryData:
    """遥测数据结构"""
    # 时间
    time: dict

    # 姿态
    roll_deg: float
    pitch_deg: float
    yaw_deg: float

    # 位置
    lat: float | None
    lon: float | None
    alt_m: float | None
    relative_alt_m: float | None

    # 速度
    vx: float | None
    vy: float | None
    vz: float | None
    groundspeed: float | None

    # 电池
    battery_voltage: float | None
    battery_remaining_pct: int | None

    # 系统状态
    armed: bool
    mode: str
    link_status: str


class MavlinkTelemetryReceiver:
    """MAVLink遥测接收器"""

    def __init__(
        self,
        conn_str: str,
        output_path: Path,
        reconnect_interval: float = 5.0,
    ):
        self._conn_str = conn_str
        self._output_path = output_path
        self._reconnect_interval = reconnect_interval
        self._timebase = TimeBase()
        self._running = False
        self._master = None
        self._queue: Queue[TelemetryData] = Queue(maxsize=100)

        # 缓存最新数据
        self._attitude = {"roll": 0, "pitch": 0, "yaw": 0}
        self._position = {"lat": None, "lon": None, "alt": None, "rel_alt": None}
        self._velocity = {"vx": None, "vy": None, "vz": None, "gs": None}
        self._battery = {"voltage": None, "remaining": None}
        self._status = {"armed": False, "mode": "UNKNOWN"}

    def _connect(self) -> bool:
        """建立MAVLink连接"""
        try:
            from pymavlink import mavutil
            print(f"连接MAVLink: {self._conn_str}")
            self._master = mavutil.mavlink_connection(self._conn_str)
            hb = self._master.wait_heartbeat(timeout=10)
            if hb:
                print(f"✓ 连接成功 - 系统ID: {self._master.target_system}")
                return True
            else:
                print("✗ 心跳超时")
                return False
        except Exception as e:
            print(f"✗ 连接失败: {e}")
            return False

    def _process_message(self, msg) -> None:
        """处理MAVLink消息"""
        msg_type = msg.get_type()

        if msg_type == "ATTITUDE":
            self._attitude["roll"] = round(msg.roll * 57.2958, 2)  # rad to deg
            self._attitude["pitch"] = round(msg.pitch * 57.2958, 2)
            self._attitude["yaw"] = round(msg.yaw * 57.2958, 2)

        elif msg_type == "GLOBAL_POSITION_INT":
            self._position["lat"] = msg.lat / 1e7
            self._position["lon"] = msg.lon / 1e7
            self._position["alt"] = msg.alt / 1000.0
            self._position["rel_alt"] = msg.relative_alt / 1000.0
            self._velocity["vx"] = msg.vx / 100.0
            self._velocity["vy"] = msg.vy / 100.0
            self._velocity["vz"] = msg.vz / 100.0

        elif msg_type == "VFR_HUD":
            self._velocity["gs"] = msg.groundspeed

        elif msg_type == "SYS_STATUS":
            self._battery["voltage"] = msg.voltage_battery / 1000.0
            self._battery["remaining"] = msg.battery_remaining

        elif msg_type == "HEARTBEAT":
            self._status["armed"] = (msg.base_mode & 128) != 0
            # 获取模式名称
            mode_mapping = self._master.mode_mapping()
            mode_mapping_rev = {v: k for k, v in mode_mapping.items()}
            self._status["mode"] = mode_mapping_rev.get(msg.custom_mode, f"MODE_{msg.custom_mode}")

    def _build_telemetry(self) -> TelemetryData:
        """构建遥测数据"""
        return TelemetryData(
            time=self._timebase.now(),
            roll_deg=self._attitude["roll"],
            pitch_deg=self._attitude["pitch"],
            yaw_deg=self._attitude["yaw"],
            lat=self._position["lat"],
            lon=self._position["lon"],
            alt_m=self._position["alt"],
            relative_alt_m=self._position["rel_alt"],
            vx=self._velocity["vx"],
            vy=self._velocity["vy"],
            vz=self._velocity["vz"],
            groundspeed=self._velocity["gs"],
            battery_voltage=self._battery["voltage"],
            battery_remaining_pct=self._battery["remaining"],
            armed=self._status["armed"],
            mode=self._status["mode"],
            link_status="OK",
        )

    def _receive_loop(self) -> None:
        """接收循环"""
        last_write = 0
        write_interval = 0.5  # 500ms写入一次

        while self._running:
            if self._master is None:
                if not self._connect():
                    time.sleep(self._reconnect_interval)
                    continue

            try:
                msg = self._master.recv_match(blocking=True, timeout=1)
                if msg:
                    self._process_message(msg)

                # 定期写入
                now = time.monotonic()
                if now - last_write >= write_interval:
                    telemetry = self._build_telemetry()
                    try:
                        self._queue.put_nowait(telemetry)
                    except:
                        pass
                    last_write = now

            except Exception as e:
                print(f"接收错误: {e}")
                self._master = None
                time.sleep(1)

    def _write_loop(self) -> None:
        """写入循环"""
        while self._running:
            try:
                telemetry = self._queue.get(timeout=1)
                data = {
                    "version": "0.1",
                    "time": telemetry.time,
                    "attitude": {
                        "roll_deg": telemetry.roll_deg,
                        "pitch_deg": telemetry.pitch_deg,
                        "yaw_deg": telemetry.yaw_deg,
                    },
                    "position": {
                        "lat": telemetry.lat,
                        "lon": telemetry.lon,
                        "alt_m": telemetry.alt_m,
                        "relative_alt_m": telemetry.relative_alt_m,
                    },
                    "velocity": {
                        "vx": telemetry.vx,
                        "vy": telemetry.vy,
                        "vz": telemetry.vz,
                        "groundspeed": telemetry.groundspeed,
                    },
                    "battery": {
                        "voltage": telemetry.battery_voltage,
                        "remaining_pct": telemetry.battery_remaining_pct,
                    },
                    "armed": telemetry.armed,
                    "mode": telemetry.mode,
                    "link_status": telemetry.link_status,
                }
                self._output_path.parent.mkdir(parents=True, exist_ok=True)
                with self._output_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(data, ensure_ascii=True) + "\n")
            except:
                pass

    def start(self) -> None:
        """启动接收器"""
        self._running = True
        self._recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._write_thread = threading.Thread(target=self._write_loop, daemon=True)
        self._recv_thread.start()
        self._write_thread.start()
        print(f"遥测接收器已启动，输出: {self._output_path}")

    def stop(self) -> None:
        """停止接收器"""
        self._running = False
        if self._recv_thread:
            self._recv_thread.join(timeout=2)
        if self._write_thread:
            self._write_thread.join(timeout=2)

    def get_latest(self) -> TelemetryData:
        """获取最新遥测数据"""
        return self._build_telemetry()


def main() -> int:
    parser = argparse.ArgumentParser(description="MAVLink遥测接收器")
    parser.add_argument("--udp", default="udp:127.0.0.1:14551", help="MAVLink UDP地址")
    parser.add_argument("--run", default="latest", help="Run目录")
    parser.add_argument("--duration", type=int, default=0, help="运行时长(秒)，0=永久")
    args = parser.parse_args()

    runs_root = repo_root / "runs"
    if args.run == "latest":
        run_dirs = [p for p in runs_root.iterdir() if p.is_dir()] if runs_root.exists() else []
        if not run_dirs:
            # 创建新的run目录
            from src.common.run_manager import RunManager
            rm = RunManager(runs_root)
            run_dir = rm.create_run()
        else:
            run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            run_dir = run_dirs[0]
    else:
        run_dir = runs_root / args.run

    output_path = run_dir / "telemetry" / "telemetry.jsonl"

    print("=" * 60)
    print("MAVLink 遥测接收器")
    print("=" * 60)
    print(f"MAVLink: {args.udp}")
    print(f"输出:    {output_path}")
    print("=" * 60)

    receiver = MavlinkTelemetryReceiver(args.udp, output_path)

    try:
        receiver.start()
        if args.duration > 0:
            time.sleep(args.duration)
        else:
            print("按 Ctrl+C 停止...")
            while True:
                time.sleep(1)
                tel = receiver.get_latest()
                print(f"\r姿态: R={tel.roll_deg:6.1f}° P={tel.pitch_deg:6.1f}° Y={tel.yaw_deg:6.1f}° | 模式: {tel.mode:10s} | {'ARMED' if tel.armed else 'DISARMED'}", end="")
    except KeyboardInterrupt:
        print("\n停止...")
    finally:
        receiver.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
