from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def _add_repo_to_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


repo_root = _add_repo_to_path()

from apps.acquisition.audio_capture import AudioCapture  # noqa: E402
from apps.acquisition.camera_capture import CameraCapture  # noqa: E402
from apps.acquisition.config_utils import load_config  # noqa: E402
from apps.acquisition.logging_utils import setup_logging  # noqa: E402
from apps.acquisition.observation_capture import ObservationCapture  # noqa: E402
from apps.acquisition.telemetry_capture import TelemetryCapture  # noqa: E402
from src.common.run_manager import RunManager  # noqa: E402
from src.common.timebase import TimeBase  # noqa: E402


def log_stats(logger, label: str, stats, warn_below: float | None = None, overrun_warn: int | None = None) -> None:
    snap = stats.snapshot()
    logger.info(
        "%s rate=%.2fHz total=%d dropped=%d overrun=%d",
        label,
        snap["rate_hz"],
        snap["total"],
        snap["dropped"],
        snap["overrun"],
    )
    if warn_below is not None and snap["rate_hz"] > 0 and snap["rate_hz"] < warn_below:
        logger.warning("%s rate below target: %.2fHz < %.2fHz", label, snap["rate_hz"], warn_below)
    if overrun_warn is not None and snap["interval_overrun"] >= overrun_warn:
        logger.warning("%s overrun in interval: %d", label, snap["interval_overrun"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Sprint 1 acquisition runner")
    parser.add_argument("--config", default="configs/dev.yaml", help="Config file")
    parser.add_argument("--duration", type=float, help="Override duration (sec)")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()

    config = load_config(config_path)
    run_cfg = config.get("run", {})
    duration_sec = float(args.duration) if args.duration is not None else float(run_cfg.get("duration_sec", 1800))
    stats_interval = float(run_cfg.get("stats_interval_sec", 5))

    output_root = Path(run_cfg.get("output_root", "runs"))
    output_root_path = (repo_root / output_root).resolve()

    run_manager = RunManager(repo_root, output_root_path, config)
    timebase = TimeBase()

    log_cfg = config.get("logging", {})
    logger = setup_logging(str(log_cfg.get("level", "INFO")), Path(log_cfg.get("dir", "logs")), run_manager.run_id)

    logger.info("Run starting: %s", run_manager.paths.root)
    logger.info("Config: %s", config_path)
    run_manager.write_meta(extra={"run_dir": str(run_manager.paths.root)})

    camera_cfg = config.get("camera", {})
    audio_cfg = config.get("audio", {})
    telemetry_cfg = config.get("telemetry", {})
    observation_cfg = config.get("observation", {})

    camera = CameraCapture(camera_cfg, run_manager.paths.video, timebase, logger)
    audio = AudioCapture(audio_cfg, run_manager.paths.audio, timebase, logger)
    telemetry = TelemetryCapture(telemetry_cfg, run_manager.paths.telemetry, timebase, logger)
    observation = ObservationCapture(observation_cfg, run_manager.paths.observations, timebase, logger)

    camera.start()
    audio.start()
    telemetry.start()
    observation.start()

    start = time.monotonic()
    next_stats = start + stats_interval

    try:
        if duration_sec <= 0:
            logger.info("Running until interrupted...")
            while True:
                time.sleep(1)
                if time.monotonic() >= next_stats:
                    log_stats(logger, "video", camera.stats, warn_below=float(camera_cfg.get("fps_warn_below", 0)) or None)
                    log_stats(
                        logger,
                        "audio",
                        audio.stats,
                        overrun_warn=int(audio_cfg.get("overrun_warn", 0)) or None,
                    )
                    log_stats(logger, "telemetry", telemetry.stats)
                    log_stats(logger, "observation", observation.stats)
                    next_stats = time.monotonic() + stats_interval
        else:
            while time.monotonic() - start < duration_sec:
                time.sleep(0.2)
                if time.monotonic() >= next_stats:
                    log_stats(logger, "video", camera.stats, warn_below=float(camera_cfg.get("fps_warn_below", 0)) or None)
                    log_stats(
                        logger,
                        "audio",
                        audio.stats,
                        overrun_warn=int(audio_cfg.get("overrun_warn", 0)) or None,
                    )
                    log_stats(logger, "telemetry", telemetry.stats)
                    log_stats(logger, "observation", observation.stats)
                    next_stats += stats_interval
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        camera.stop()
        audio.stop()
        telemetry.stop()
        observation.stop()
        camera.join(timeout=5)
        audio.join(timeout=5)
        telemetry.join(timeout=5)
        observation.join(timeout=5)
        logger.info("Run complete: %s", run_manager.paths.root)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
