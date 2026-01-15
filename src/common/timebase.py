from __future__ import annotations

import time


class TimeBase:
    def now(self) -> dict:
        return {
            "t_mono_ms": int(time.monotonic() * 1000),
            "t_wall_ms": int(time.time() * 1000),
        }
