from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import yaml
from pymavlink import mavutil


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("Config must be a mapping")
    return data


def connect_mavlink(config: dict) -> mavutil.mavfile:
    telemetry = config.get("telemetry", {})
    mode = telemetry.get("mode")
    mav_cfg = telemetry.get("mavlink", {})

    if mode == "mavlink_udp":
        conn_str = mav_cfg.get("udp")
        if not conn_str:
            raise ValueError("telemetry.mavlink.udp is required")
        return mavutil.mavlink_connection(conn_str)

    if mode == "mavlink_serial":
        port = mav_cfg.get("serial_port")
        if not port:
            raise ValueError("telemetry.mavlink.serial_port is required")
        baud = int(mav_cfg.get("baud", 115200))
        return mavutil.mavlink_connection(port, baud=baud)

    raise ValueError("telemetry.mode must be mavlink_udp or mavlink_serial for this demo")


def main() -> int:
    parser = argparse.ArgumentParser(description="MAVLink heartbeat demo")
    parser.add_argument("--config", default="configs/dev.yaml", help="Config file")
    parser.add_argument("--output", help="Optional JSONL output path")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()

    config = load_config(config_path)

    try:
        master = connect_mavlink(config)
    except Exception as exc:
        print(f"Failed to connect MAVLink: {exc}")
        return 1

    print("Waiting for heartbeat (10s timeout)...")
    heartbeat = master.wait_heartbeat(timeout=10)
    if not heartbeat:
        print("No heartbeat received. Start SITL or check your port.")
        return 1

    print("Heartbeat received. Streaming for 10s...")

    output_handle = None
    if args.output:
        output_path = Path(args.output)
        output_handle = output_path.open("w", encoding="utf-8")

    end_time = time.time() + 10
    try:
        while time.time() < end_time:
            msg = master.recv_match(blocking=True, timeout=1)
            if not msg:
                continue
            msg_type = msg.get_type()
            if msg_type == "BAD_DATA":
                continue
            record = {
                "version": "0.1",
                "type": "telemetry",
                "epoch_ms": int(time.time() * 1000),
                "source": "mavlink",
                "payload": msg.to_dict(),
            }
            line = json.dumps(record, ensure_ascii=True)
            if output_handle:
                output_handle.write(line + "\n")
            else:
                print(line)
    finally:
        if output_handle:
            output_handle.close()

    print("Demo complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
