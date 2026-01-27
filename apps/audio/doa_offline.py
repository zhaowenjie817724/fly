from __future__ import annotations

import argparse
import json
import math
import sys
import time
import wave
from pathlib import Path

import numpy as np

def _add_repo_to_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


repo_root = _add_repo_to_path()

from apps.acquisition.config_utils import load_config  # noqa: E402
from src.common.timebase import TimeBase  # noqa: E402


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        frames = wav.getnframes()
        data = wav.readframes(frames)
        samples = np.frombuffer(data, dtype=np.int16)
        if channels > 1:
            samples = samples.reshape(-1, channels)
        else:
            samples = samples.reshape(-1, 1)
    return samples.astype(np.float32) / 32768.0, sample_rate


def write_wav(path: Path, data: np.ndarray, sample_rate: int) -> None:
    channels = data.shape[1]
    audio_i16 = np.clip(data * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio_i16.tobytes())


def gcc_phat(sig: np.ndarray, refsig: np.ndarray, fs: int, max_tau: float | None = None) -> tuple[float, float]:
    n = sig.shape[0] + refsig.shape[0]
    SIG = np.fft.rfft(sig, n=n)
    REFSIG = np.fft.rfft(refsig, n=n)
    R = SIG * np.conj(REFSIG)
    denom = np.abs(R)
    R = R / (denom + 1e-12)
    cc = np.fft.irfft(R, n=n)

    max_shift = n // 2
    if max_tau is not None:
        max_shift = min(int(fs * max_tau), max_shift)

    cc = np.concatenate((cc[-max_shift:], cc[: max_shift + 1]))
    shift = np.argmax(np.abs(cc)) - max_shift
    tau = shift / float(fs)
    peak = float(np.max(np.abs(cc)))
    mean = float(np.mean(np.abs(cc))) + 1e-12
    ratio = peak / mean
    return tau, ratio


def _pre_emphasis(sig: np.ndarray, coeff: float) -> np.ndarray:
    if coeff <= 0:
        return sig
    out = np.empty_like(sig)
    out[0] = sig[0]
    out[1:] = sig[1:] - coeff * sig[:-1]
    return out


def estimate_bearing(
    sig: np.ndarray,
    fs: int,
    mic_distance_m: float,
    speed_sound: float,
    pair_mode: str,
    window: str,
    pre_emphasis: float,
) -> tuple[float | None, float]:
    if sig.shape[1] < 2:
        return None, 0.0

    if window == "hann":
        win = np.hanning(sig.shape[0]).astype(np.float32)
    else:
        win = None

    def prep(channel: np.ndarray) -> np.ndarray:
        out = channel
        if win is not None:
            out = out * win
        return _pre_emphasis(out, pre_emphasis)

    channels = [prep(sig[:, idx]) for idx in range(sig.shape[1])]
    pairs: list[tuple[int, int]] = []
    if pair_mode == "adjacent":
        pairs = [(idx, idx + 1) for idx in range(sig.shape[1] - 1)]
    else:
        pairs = [(0, idx) for idx in range(1, sig.shape[1])]

    angles: list[float] = []
    weights: list[float] = []
    for i, j in pairs:
        distance = mic_distance_m * abs(i - j)
        if distance <= 0:
            continue
        tdoa, ratio = gcc_phat(channels[i], channels[j], fs, max_tau=distance / speed_sound)
        value = (tdoa * speed_sound) / distance
        value = float(np.clip(value, -1.0, 1.0))
        angle_rad = math.asin(value)
        angle = math.degrees(angle_rad)
        conf = float(ratio / (ratio + 1.0))
        angles.append(angle)
        weights.append(conf)

    if not angles:
        return None, 0.0

    total = sum(weights)
    if total <= 0:
        return None, 0.0

    bearing = sum(a * w for a, w in zip(angles, weights)) / total
    confidence = max(weights)
    return bearing, confidence


def synth_multichannel(
    duration_sec: float,
    sample_rate: int,
    mic_distance_m: float,
    speed_sound: float,
    angle_deg: float,
    noise_level: float,
) -> np.ndarray:
    t = np.arange(int(duration_sec * sample_rate)) / sample_rate
    base = 0.4 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 880 * t)
    base += noise_level * np.random.randn(t.shape[0])

    angle_rad = math.radians(angle_deg)
    delay = (mic_distance_m * math.sin(angle_rad)) / speed_sound
    delay_samples = delay * sample_rate

    def shift(sig: np.ndarray, samples: float) -> np.ndarray:
        idx = np.arange(sig.shape[0]) - samples
        idx0 = np.floor(idx).astype(int)
        frac = idx - idx0
        shifted = np.zeros_like(sig)
        valid = (idx0 >= 0) & (idx0 + 1 < sig.shape[0])
        shifted[valid] = sig[idx0[valid]] * (1 - frac[valid]) + sig[idx0[valid] + 1] * frac[valid]
        return shifted

    ch0 = base
    ch1 = shift(base, delay_samples)
    return np.stack([ch0, ch1], axis=1).astype(np.float32)


def load_audio_index(index_path: Path) -> list[dict]:
    if not index_path.exists():
        return []
    records: list[dict] = []
    with index_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            time_obj = record.get("time")
            if isinstance(time_obj, dict):
                records.append(time_obj)
    return records


def run_doa(config: dict, run_dir: Path, input_wav: Path | None) -> None:
    doa_cfg = config.get("doa", {})
    mic_distance = float(doa_cfg.get("mic_distance_m", 0.05))
    speed_sound = float(doa_cfg.get("speed_sound_m_s", 343.0))
    block_ms = float(doa_cfg.get("block_ms", 100))
    smoothing = float(doa_cfg.get("smoothing", 0.4))
    conf_threshold = float(doa_cfg.get("conf_threshold", 0.1))
    window = str(doa_cfg.get("window", "hann"))
    pair_mode = str(doa_cfg.get("pair_mode", "reference"))
    pre_emphasis = float(doa_cfg.get("pre_emphasis", 0.0))
    use_synth = bool(doa_cfg.get("synth_enabled", False))
    synth_angle = float(doa_cfg.get("synth_angle_deg", 30))
    synth_duration = float(doa_cfg.get("synth_duration_sec", 10))
    noise_level = float(doa_cfg.get("synth_noise_level", 0.05))

    if use_synth:
        sample_rate = int(doa_cfg.get("synth_sample_rate", 16000))
        audio = synth_multichannel(
            synth_duration,
            sample_rate,
            mic_distance,
            speed_sound,
            synth_angle,
            noise_level,
        )
        input_wav = run_dir / "audio" / "audio_synth.wav"
        input_wav.parent.mkdir(parents=True, exist_ok=True)
        write_wav(input_wav, audio, sample_rate)
    elif not input_wav:
        raise RuntimeError("input_wav is required when synth is disabled")

    audio, sample_rate = read_wav(input_wav)
    block_samples = max(1, int(sample_rate * block_ms / 1000.0))
    timebase = TimeBase()

    obs_dir = run_dir / "observations"
    obs_dir.mkdir(parents=True, exist_ok=True)
    obs_path = obs_dir / "audio_doa.jsonl"
    metrics_path = run_dir / "metrics.jsonl"

    index_path = run_dir / "audio" / "audio_index.jsonl"
    time_index = load_audio_index(index_path)

    smoothed_angle: float | None = None
    errors: list[float] = []
    block_id = 0
    with obs_path.open("w", encoding="utf-8") as obs_handle, metrics_path.open("a", encoding="utf-8") as metrics_handle:
        for start in range(0, audio.shape[0] - block_samples + 1, block_samples):
            chunk = audio[start : start + block_samples]
            time_obj = time_index[block_id] if block_id < len(time_index) else timebase.now()
            angle, conf_score = estimate_bearing(
                chunk,
                sample_rate,
                mic_distance,
                speed_sound,
                pair_mode,
                window,
                pre_emphasis,
            )
            status = "INVALID"
            bearing = None
            confidence = None
            if angle is not None and conf_score >= conf_threshold:
                status = "OK"
                bearing = angle
                confidence = min(1.0, conf_score)
                if smoothed_angle is None:
                    smoothed_angle = bearing
                else:
                    smoothed_angle = smoothed_angle * (1 - smoothing) + bearing * smoothing
                bearing = smoothed_angle
                if use_synth:
                    errors.append(abs(bearing - synth_angle))

            record = {
                "version": "0.1",
                "time": time_obj,
                "source": "audio",
                "bearing_deg": bearing,
                "roi": None,
                "confidence": confidence,
                "status": status,
                "extras": {"block_id": block_id},
            }
            obs_handle.write(json.dumps(record, ensure_ascii=True) + "\n")
            block_id += 1

        if use_synth and errors:
            metrics = {
                "version": "0.1",
                "time": timebase.now(),
                "type": "doa_eval",
                "payload": {
                    "mean_abs_error_deg": float(np.mean(errors)),
                    "max_abs_error_deg": float(np.max(errors)),
                    "blocks": len(errors),
                },
            }
            metrics_handle.write(json.dumps(metrics, ensure_ascii=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline DOA (Sprint 3)")
    parser.add_argument("--config", default="configs/doa.yaml", help="Config file")
    parser.add_argument("--run", default="latest", help="Run id/path for output")
    parser.add_argument("--input", help="Input wav file (optional if synth enabled)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()
    config = load_config(config_path)

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

    input_wav = Path(args.input) if args.input else None
    if input_wav and not input_wav.is_absolute():
        input_wav = (repo_root / input_wav).resolve()

    run_doa(config, run_dir, input_wav)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
