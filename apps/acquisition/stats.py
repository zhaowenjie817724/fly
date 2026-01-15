from __future__ import annotations

import threading
import time


class StatsCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start = time.monotonic()
        self._interval_start = self._start
        self.total = 0
        self.dropped = 0
        self.overrun = 0
        self._interval_total = 0
        self._interval_dropped = 0
        self._interval_overrun = 0

    def increment(self, count: int = 1) -> None:
        with self._lock:
            self.total += count
            self._interval_total += count

    def drop(self, count: int = 1) -> None:
        with self._lock:
            self.dropped += count
            self._interval_dropped += count

    def add_overrun(self, count: int = 1) -> None:
        with self._lock:
            self.overrun += count
            self._interval_overrun += count

    def snapshot(self, reset_interval: bool = True) -> dict:
        now = time.monotonic()
        with self._lock:
            interval = now - self._interval_start
            fps = self._interval_total / interval if interval > 0 else 0.0
            snapshot = {
                "total": self.total,
                "dropped": self.dropped,
                "overrun": self.overrun,
                "interval_sec": interval,
                "interval_count": self._interval_total,
                "interval_dropped": self._interval_dropped,
                "interval_overrun": self._interval_overrun,
                "rate_hz": fps,
            }
            if reset_interval:
                self._interval_start = now
                self._interval_total = 0
                self._interval_dropped = 0
                self._interval_overrun = 0
        return snapshot
