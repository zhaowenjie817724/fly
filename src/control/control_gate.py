from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class GateConfig:
    max_rate_hz: float = 5.0
    command_ttl_sec: float = 1.0
    allow_types: tuple[str, ...] = ("SET_YAW", "SET_MODE", "STOP")


class CommandGate:
    def __init__(self, config: GateConfig) -> None:
        self._config = config
        self._last_send = 0.0
        self._last_cmd = 0.0
        self._link_status = "OK"

    def update_link_status(self, status: str) -> None:
        self._link_status = status

    def can_send(self, cmd_type: str) -> bool:
        if cmd_type not in self._config.allow_types:
            return False
        if self._link_status != "OK":
            return False
        now = time.monotonic()
        min_interval = 1.0 / self._config.max_rate_hz if self._config.max_rate_hz > 0 else 0
        if now - self._last_send < min_interval:
            return False
        return True

    def mark_sent(self) -> None:
        now = time.monotonic()
        self._last_send = now
        self._last_cmd = now

    def expired(self) -> bool:
        if self._config.command_ttl_sec <= 0:
            return False
        return (time.monotonic() - self._last_cmd) > self._config.command_ttl_sec
