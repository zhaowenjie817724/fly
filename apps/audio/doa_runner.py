"""
DOA (Direction of Arrival) 实时运行器。

包装 doa_online.OnlineDOA，从麦克风阵列实时采集双通道音频，
计算声源方位角，写入 runs/*/observations/doa_obs.jsonl。

用法：
  python apps/audio/doa_runner.py --config configs/pi_stereo.yaml --run latest
  python apps/audio/doa_runner.py --config configs/pi_stereo.yaml --device 1
"""
from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
from pathlib import Path


def _add_repo_to_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


repo_root = _add_repo_to_path()

from apps.acquisition.config_utils import load_config  # noqa: E402
from apps.audio.doa_online import DOAConfig, OnlineDOA  # noqa: E402


def run_doa_live(config: dict, run_dir: Path, device_override: int | None) -> None:
    """从麦克风实时采集并写 doa_obs.jsonl。"""
    doa_cfg_dict = config.get("doa", {})
    audio_cfg = config.get("audio", {})

    doa_config = DOAConfig.from_dict(doa_cfg_dict)

    # 设备优先级：命令行参数 > config audio.device_index > 系统默认
    if device_override is not None:
        device = device_override
    else:
        raw = audio_cfg.get("device_index", None)
        device = int(raw) if raw is not None else None

    channels = int(audio_cfg.get("channels", 2))

    obs_dir = run_dir / "observations"
    obs_dir.mkdir(parents=True, exist_ok=True)
    obs_path = obs_dir / "doa_obs.jsonl"

    result_queue: queue.Queue = queue.Queue(maxsize=200)

    def on_result(result):
        try:
            result_queue.put_nowait(result)
        except queue.Full:
            pass  # 丢弃旧结果，避免积压

    doa = OnlineDOA(doa_config, on_result=on_result)

    try:
        import sounddevice as sd
    except ImportError:
        raise RuntimeError(
            "sounddevice is required for DOA runner.\n"
            "Install: pip install sounddevice"
        )

    stop_event = threading.Event()

    def audio_callback(indata, frames, time_info, status):
        if not stop_event.is_set():
            doa.process_chunk(indata.copy())

    doa.start()

    # 实际采集声道数：DOA 需要至少 2 通道
    actual_channels = max(2, channels)

    stream = sd.InputStream(
        samplerate=doa_config.sample_rate,
        channels=actual_channels,
        dtype="float32",
        blocksize=doa._hop_samples,
        device=device,
        callback=audio_callback,
    )

    print(
        f"DOA runner started: device={device}, "
        f"sr={doa_config.sample_rate}Hz, channels={actual_channels}, "
        f"mic_dist={doa_config.mic_distance_m}m",
        flush=True,
    )

    stream.start()

    try:
        with obs_path.open("w", encoding="utf-8") as handle:
            while not stop_event.is_set():
                try:
                    result = result_queue.get(timeout=1.0)
                    record = doa.to_observation(result)
                    handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                    handle.flush()
                except queue.Empty:
                    continue
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        stream.stop()
        stream.close()
        doa.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="DOA live runner")
    parser.add_argument("--config", default="configs/pi_stereo.yaml", help="Config file")
    parser.add_argument("--run", default="latest", help="Run id/path")
    parser.add_argument("--device", type=int, default=None, help="Audio device index (overrides config)")
    args = parser.parse_args()

    repo_root = _add_repo_to_path()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()
    config = load_config(config_path)

    runs_root = repo_root / "runs"
    if args.run == "latest":
        run_dir = None
        while run_dir is None:
            run_dirs = (
                [p for p in runs_root.iterdir() if p.is_dir()]
                if runs_root.exists()
                else []
            )
            if run_dirs:
                run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                run_dir = run_dirs[0]
            else:
                print("Waiting for a run to appear in runs/ ...", flush=True)
                time.sleep(2)
    else:
        run_dir = Path(args.run)
        if not run_dir.is_absolute():
            run_dir = runs_root / args.run
        if not run_dir.exists():
            raise RuntimeError(f"Run not found: {run_dir}")

    run_doa_live(config, run_dir, args.device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
