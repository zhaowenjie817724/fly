from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

def _add_repo_to_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


repo_root = _add_repo_to_path()

from apps.acquisition.config_utils import load_config  # noqa: E402
from src.control.control_gate import CommandGate, GateConfig  # noqa: E402
from src.control.mavlink_control import MavlinkControl  # noqa: E402
from src.common.timebase import TimeBase  # noqa: E402


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


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


class SensorHealth:
    """Sprint 4: 传感器健康监测"""
    def __init__(self, timeout_sec: float = 5.0) -> None:
        self._timeout = timeout_sec
        self._last_vision: float = 0.0
        self._last_audio: float = 0.0

    def update_vision(self) -> None:
        self._last_vision = time.monotonic()

    def update_audio(self) -> None:
        self._last_audio = time.monotonic()

    def vision_ok(self) -> bool:
        return (time.monotonic() - self._last_vision) < self._timeout

    def audio_ok(self) -> bool:
        return (time.monotonic() - self._last_audio) < self._timeout

    def status(self) -> str:
        v = self.vision_ok()
        a = self.audio_ok()
        if v and a:
            return "ALL_OK"
        if v and not a:
            return "AUDIO_FAIL"
        if not v and a:
            return "VISION_FAIL"
        return "BOTH_FAIL"


class TelemetryMonitor:
    def __init__(self, telemetry_path: Path) -> None:
        self.telemetry_path = telemetry_path
        self._last_status = "OK"

    def update(self) -> str:
        records = load_jsonl(self.telemetry_path)
        if not records:
            return self._last_status
        latest = records[-1]
        self._last_status = str(latest.get("link_status", "OK"))
        return self._last_status


class FSM:
    """Sprint 4: 完整状态机 with 降级策略"""

    # 状态常量
    IDLE = "IDLE"
    SEARCH = "SEARCH"
    SCAN = "SCAN"
    LOCKED = "LOCKED"
    TRACK = "TRACK"
    LOST = "LOST"
    DEGRADED = "DEGRADED"
    RETURN = "RETURN"

    def __init__(
        self,
        config: dict,
        gate: CommandGate,
        control: MavlinkControl | None,
        events_path: Path,
        commands_path: Path,
    ) -> None:
        fsm_cfg = config.get("fsm", {})
        self._lock_conf = float(fsm_cfg.get("lock_conf", 0.6))
        self._audio_trigger_conf = float(fsm_cfg.get("audio_trigger_conf", 0.3))
        self._lost_timeout = float(fsm_cfg.get("lost_timeout_sec", 3))
        self._yaw_rate = float(fsm_cfg.get("yaw_rate_deg_s", 30))
        self._event_cooldown = float(fsm_cfg.get("event_cooldown_sec", 1.0))

        # Sprint 4: 降级配置
        degrade_cfg = fsm_cfg.get("degradation", {})
        self._vision_fail_action = str(degrade_cfg.get("vision_fail_action", "audio_only"))
        self._audio_fail_action = str(degrade_cfg.get("audio_fail_action", "vision_only"))
        self._both_fail_action = str(degrade_cfg.get("both_fail_action", "return"))
        self._max_degraded_sec = float(degrade_cfg.get("max_degraded_sec", 30))
        self._auto_recover = bool(degrade_cfg.get("auto_recover", True))

        self._gate = gate
        self._control = control
        self._events_path = events_path
        self._commands_path = commands_path
        self._state = self.IDLE
        self._prev_state = self.IDLE
        self._last_seen = time.monotonic()
        self._degraded_since: float | None = None
        self._timebase = TimeBase()
        self._last_event: dict[str, float] = {}
        self._sensor = SensorHealth(timeout_sec=self._lost_timeout)
        self._active_source: str = "fused"  # fused | vision_only | audio_only

    def _emit_event(self, event_type: str, note: str) -> None:
        now = time.monotonic()
        last = self._last_event.get(event_type, 0.0)
        if self._event_cooldown > 0 and (now - last) < self._event_cooldown:
            return
        record = {
            "version": "0.1",
            "time": self._timebase.now(),
            "type": event_type,
            "severity": "INFO",
            "note": note,
        }
        with self._events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        self._last_event[event_type] = now

    def _log_command(self, cmd_type: str, params: dict, allowed: bool, note: str) -> None:
        record = {
            "version": "0.1",
            "time": self._timebase.now(),
            "type": cmd_type,
            "params": params,
            "allowed": allowed,
            "note": note,
        }
        with self._commands_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    def _send_yaw(self, bearing: float) -> None:
        allowed = self._gate.can_send("SET_YAW")
        self._log_command("SET_YAW", {"yaw_deg": bearing, "yaw_rate_deg_s": self._yaw_rate}, allowed, "fsm")
        if not allowed:
            return
        if self._control:
            self._control.send_yaw(bearing, self._yaw_rate, relative=False)
        self._gate.mark_sent()

    def _send_return(self) -> None:
        """Sprint 4: 发送返航指令"""
        allowed = self._gate.can_send("SET_MODE")
        self._log_command("SET_MODE", {"mode": "RTL"}, allowed, "fsm-return")
        if not allowed:
            return
        if self._control:
            self._control.set_mode("RTL")
        self._gate.mark_sent()

    def _transition(self, new_state: str, reason: str) -> None:
        """状态转换并记录事件"""
        if new_state != self._state:
            self._prev_state = self._state
            old_state = self._state
            self._state = new_state
            self._emit_event("MODE_CHANGED", f"{old_state} -> {new_state}: {reason}")

    def _check_degradation(self) -> str | None:
        """Sprint 4: 检查是否需要降级，返回降级动作"""
        status = self._sensor.status()
        if status == "ALL_OK":
            return None
        if status == "VISION_FAIL":
            return self._vision_fail_action
        if status == "AUDIO_FAIL":
            return self._audio_fail_action
        if status == "BOTH_FAIL":
            return self._both_fail_action
        return None

    def step(self, obs: dict | None) -> None:
        now = time.monotonic()

        # 更新传感器健康状态
        if obs and obs.get("status") == "OK":
            source = obs.get("source", "")
            extras = obs.get("extras") or {}
            sources = extras.get("sources", []) if isinstance(extras, dict) else []
            if source == "vision" or "vision" in sources:
                self._sensor.update_vision()
            if source == "audio" or "audio" in sources:
                self._sensor.update_audio()
            if source == "fusion" or source == "fused":
                self._sensor.update_vision()
                self._sensor.update_audio()

        # Sprint 4: 降级检查
        degrade_action = self._check_degradation()
        if degrade_action:
            if self._state != self.DEGRADED and self._state != self.RETURN:
                if degrade_action == "return":
                    self._transition(self.RETURN, "both_sensors_fail")
                    self._send_return()
                    return
                else:
                    self._transition(self.DEGRADED, f"sensor_fail:{degrade_action}")
                    self._degraded_since = now
                    self._active_source = degrade_action

            # 降级超时检查
            if self._state == self.DEGRADED and self._degraded_since:
                if (now - self._degraded_since) > self._max_degraded_sec:
                    self._transition(self.RETURN, "degraded_timeout")
                    self._send_return()
                    return

        # 自动恢复
        if self._state == self.DEGRADED and self._auto_recover:
            if self._sensor.status() == "ALL_OK":
                self._transition(self.SEARCH, "sensors_recovered")
                self._active_source = "fused"
                self._degraded_since = None

        # 状态机主逻辑
        if obs and obs.get("status") == "OK" and obs.get("bearing_deg") is not None:
            extras = obs.get("extras") or {}
            sources = extras.get("sources", []) if isinstance(extras, dict) else []
            conf = float(obs.get("confidence") or 0.0)
            bearing = float(obs["bearing_deg"])

            self._last_seen = now

            # IDLE -> SEARCH
            if self._state == self.IDLE:
                self._transition(self.SEARCH, "observation_received")

            # SEARCH -> SCAN
            if self._state == self.SEARCH:
                self._transition(self.SCAN, "target_detected")

            # SCAN/LOCKED/TRACK 处理
            if self._state in (self.SCAN, self.LOCKED, self.TRACK, self.DEGRADED):
                should_yaw = False

                # 降级模式下的源过滤
                if self._active_source == "audio_only":
                    should_yaw = ("audio" in sources) and conf >= self._audio_trigger_conf
                elif self._active_source == "vision_only":
                    should_yaw = ("vision" in sources)
                else:
                    # 正常融合模式
                    if "audio" in sources and "vision" not in sources:
                        should_yaw = conf >= self._audio_trigger_conf
                    elif "vision" in sources:
                        should_yaw = True

                if should_yaw:
                    self._send_yaw(bearing)

                # SCAN -> LOCKED (视觉确认)
                if self._state == self.SCAN and "vision" in sources and conf >= self._lock_conf:
                    self._transition(self.LOCKED, f"vision_confirmed(conf={conf:.2f})")

                # LOCKED -> TRACK (持续追踪)
                if self._state == self.LOCKED and conf >= self._lock_conf:
                    self._transition(self.TRACK, "continuous_tracking")

        else:
            # 无有效观测
            if self._state in (self.SCAN, self.LOCKED, self.TRACK):
                if (now - self._last_seen) > self._lost_timeout:
                    self._transition(self.LOST, "observation_timeout")

            # LOST -> SEARCH (重新搜索)
            if self._state == self.LOST:
                if self._gate.expired():
                    allowed = self._gate.can_send("STOP")
                    self._log_command("STOP", {}, allowed, "fsm-lost")
                    if allowed and self._control:
                        self._control.send_stop()
                        self._gate.mark_sent()
                self._transition(self.SEARCH, "resume_search")


def main() -> int:
    parser = argparse.ArgumentParser(description="FSM runner (Sprint 4)")
    parser.add_argument("--config", default="configs/fsm.yaml", help="Config file")
    parser.add_argument("--run", default="latest", help="Run id/path to replay")
    parser.add_argument("--dry-run", action="store_true", help="Do not send MAVLink commands")
    parser.add_argument("--speed", type=float, default=1.0, help="Replay speed (0=fast)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()
    config = load_config(config_path)

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

    obs_path = run_dir / "observations" / "fused.jsonl"
    if not obs_path.exists():
        raise RuntimeError("Missing fused.jsonl. Run apps/fusion/fuse_replay.py first.")

    telemetry_path = run_dir / "telemetry" / "telemetry.jsonl"
    events_path = run_dir / "events.jsonl"
    commands_path = run_dir / "commands.jsonl"
    commands_path.touch(exist_ok=True)

    control = None
    if not args.dry_run:
        ctrl_cfg = config.get("control", {})
        mode = ctrl_cfg.get("mode", "mavlink_udp")
        mav_cfg = ctrl_cfg.get("mavlink", {})
        if mode == "mavlink_udp":
            conn_str = mav_cfg.get("udp", "udp:127.0.0.1:14551")
            control = MavlinkControl(conn_str)
        elif mode == "mavlink_serial":
            port = mav_cfg.get("serial_port", "COM5")
            baud = int(mav_cfg.get("baud", 115200))
            control = MavlinkControl(port, baud=baud)

    gate_cfg = GateConfig(
        max_rate_hz=float(config.get("fsm", {}).get("max_cmd_rate_hz", 5)),
        command_ttl_sec=float(config.get("fsm", {}).get("command_ttl_sec", 1)),
    )
    gate = CommandGate(gate_cfg)
    monitor = TelemetryMonitor(telemetry_path)
    fsm = FSM(config, gate, control, events_path, commands_path)

    events = load_jsonl(obs_path)
    if not events:
        return 0

    start_mono = get_mono_ms(events[0])
    start_time = time.perf_counter()
    for record in events:
        gate.update_link_status(monitor.update())
        t_mono = get_mono_ms(record) or start_mono
        if args.speed > 0:
            target_elapsed = (t_mono - start_mono) / 1000.0 / args.speed
            while time.perf_counter() - start_time < target_elapsed:
                time.sleep(0.001)
        fsm.step(record)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
