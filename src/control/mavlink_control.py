from __future__ import annotations

import time


class MavlinkControl:
    def __init__(self, conn_str: str, baud: int | None = None) -> None:
        try:
            from pymavlink import mavutil
        except Exception as exc:
            raise RuntimeError(f"pymavlink is required for control: {exc}") from exc

        if baud is None:
            self._master = mavutil.mavlink_connection(conn_str)
        else:
            self._master = mavutil.mavlink_connection(conn_str, baud=baud)

        heartbeat = self._master.wait_heartbeat(timeout=10)
        if not heartbeat:
            raise RuntimeError("No MAVLink heartbeat")

    def send_yaw(self, yaw_deg: float, yaw_rate_deg_s: float, relative: bool = False) -> None:
        # MAV_CMD_CONDITION_YAW: param1=yaw, param2=rate, param3=direction, param4=relative
        direction = 1 if yaw_rate_deg_s >= 0 else -1
        self._master.mav.command_long_send(
            self._master.target_system,
            self._master.target_component,
            115,  # MAV_CMD_CONDITION_YAW
            0,
            float(yaw_deg),
            float(abs(yaw_rate_deg_s)),
            float(direction),
            1.0 if relative else 0.0,
            0,
            0,
            0,
        )

    def set_mode(self, mode: str) -> None:
        mapping = self._master.mode_mapping()
        if mode not in mapping:
            raise ValueError(f"Mode not supported: {mode}")
        mode_id = mapping[mode]
        self._master.set_mode(mode_id)

    def send_stop(self) -> None:
        # Default to LOITER for safety if available.
        try:
            self.set_mode("LOITER")
        except Exception:
            self.set_mode("HOLD")
        time.sleep(0.1)
