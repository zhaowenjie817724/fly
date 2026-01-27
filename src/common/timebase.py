from __future__ import annotations

import time


class TimeBase:
    def now(self) -> dict:
        return {
            "mono_ms": int(time.monotonic() * 1000),
            "epoch_ms": int(time.time() * 1000),
        }
