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


def extract_command(record: dict) -> dict | None:
    if "type" in record:
        return record
    if "cmd" in record and isinstance(record["cmd"], dict):
        return record["cmd"]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Command bridge (Miniapp -> MAVLink)")
    parser.add_argument("--config", default="configs/control_bridge.yaml", help="Config file")
    parser.add_argument("--run", default="latest", help="Run id/path to monitor")
    parser.add_argument("--dry-run", action="store_true", help="Do not send MAVLink commands")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()
    config = load_config(config_path)

    bridge_cfg = config.get("control_bridge", {})
    max_rate_hz = float(bridge_cfg.get("max_rate_hz", 5))
    allow_types = tuple(str(x).upper() for x in bridge_cfg.get("allow_types", ["SET_YAW", "SET_MODE", "STOP"]))
    default_yaw_rate = float(bridge_cfg.get("default_yaw_rate_deg_s", 30))
    start_from_beginning = bool(bridge_cfg.get("start_from_beginning", False))

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

    commands_path = run_dir / "commands.jsonl"
    commands_path.touch(exist_ok=True)

    gate = CommandGate(GateConfig(max_rate_hz=max_rate_hz, allow_types=allow_types))

    control = None
    if not args.dry_run:
        mode = str(bridge_cfg.get("mode", "mavlink_udp"))
        if mode == "mavlink_udp":
            conn_str = bridge_cfg.get("udp", "udp:127.0.0.1:14551")
            control = MavlinkControl(conn_str)
        else:
            port = bridge_cfg.get("serial_port", "COM5")
            baud = int(bridge_cfg.get("baud", 115200))
            control = MavlinkControl(port, baud=baud)

    with commands_path.open("r", encoding="utf-8") as handle:
        if not start_from_beginning:
            handle.seek(0, 2)
        while True:
            line = handle.readline()
            if not line:
                time.sleep(0.2)
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            cmd = extract_command(record)
            if not cmd:
                continue
            cmd_type = str(cmd.get("type", "")).upper()
            params = cmd.get("params", {})
            if not gate.can_send(cmd_type):
                continue
            if control is None:
                gate.mark_sent()
                continue
            if cmd_type == "SET_YAW":
                yaw_deg = float(params.get("yaw_deg", 0))
                yaw_rate = float(params.get("yaw_rate_deg_s", default_yaw_rate))
                control.send_yaw(yaw_deg, yaw_rate, relative=False)
            elif cmd_type == "SET_MODE":
                mode = str(params.get("mode", "LOITER"))
                control.set_mode(mode)
            elif cmd_type == "STOP":
                control.send_stop()
            gate.mark_sent()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
