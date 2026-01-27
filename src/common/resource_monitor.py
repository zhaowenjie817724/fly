from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ResourceSnapshot:
    cpu_total_pct: float
    cpu_process_pct: float
    mem_rss_mb: float
    mem_percent: float


class ResourceMonitor:
    def __init__(self) -> None:
        try:
            import psutil
        except Exception as exc:  # pragma: no cover - import error path
            raise RuntimeError(f"psutil is required for ResourceMonitor: {exc}") from exc

        self._psutil = psutil
        self._process = psutil.Process()
        # Prime CPU counters so first snapshot is meaningful.
        psutil.cpu_percent(interval=None)
        self._process.cpu_percent(interval=None)

    def snapshot(self) -> ResourceSnapshot:
        cpu_total = float(self._psutil.cpu_percent(interval=None))
        cpu_proc = float(self._process.cpu_percent(interval=None))
        mem_info = self._process.memory_info()
        mem_rss_mb = float(mem_info.rss) / (1024 * 1024)
        mem_percent = float(self._process.memory_percent())
        return ResourceSnapshot(
            cpu_total_pct=cpu_total,
            cpu_process_pct=cpu_proc,
            mem_rss_mb=mem_rss_mb,
            mem_percent=mem_percent,
        )
