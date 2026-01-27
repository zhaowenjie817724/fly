"""
Online DOA (Direction of Arrival) processing module.
Sprint 6: Real-time audio stream processing for sound source localization.

This module provides streaming DOA estimation using GCC-PHAT algorithm,
supporting real-time audio input from microphone arrays.
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

def _add_repo_to_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


repo_root = _add_repo_to_path()

from src.common.timebase import TimeBase  # noqa: E402


@dataclass
class DOAConfig:
    """Configuration for online DOA processing."""
    mic_distance_m: float = 0.05
    speed_sound_m_s: float = 343.0
    sample_rate: int = 16000
    block_ms: int = 100
    overlap_ratio: float = 0.5
    smoothing: float = 0.4
    conf_threshold: float = 0.1
    window: str = "hann"
    pair_mode: str = "reference"
    pre_emphasis: float = 0.0
    max_history: int = 50

    @classmethod
    def from_dict(cls, cfg: dict) -> "DOAConfig":
        """Create config from dictionary."""
        return cls(
            mic_distance_m=float(cfg.get("mic_distance_m", 0.05)),
            speed_sound_m_s=float(cfg.get("speed_sound_m_s", 343.0)),
            sample_rate=int(cfg.get("sample_rate", 16000)),
            block_ms=int(cfg.get("block_ms", 100)),
            overlap_ratio=float(cfg.get("overlap_ratio", 0.5)),
            smoothing=float(cfg.get("smoothing", 0.4)),
            conf_threshold=float(cfg.get("conf_threshold", 0.1)),
            window=str(cfg.get("window", "hann")),
            pair_mode=str(cfg.get("pair_mode", "reference")),
            pre_emphasis=float(cfg.get("pre_emphasis", 0.0)),
            max_history=int(cfg.get("max_history", 50)),
        )


@dataclass
class DOAResult:
    """Result of a DOA estimation."""
    bearing_deg: float | None
    confidence: float
    status: str
    timestamp_ms: int
    block_id: int


class RingBuffer:
    """Thread-safe ring buffer for audio samples."""

    def __init__(self, capacity: int, channels: int = 2):
        self._capacity = capacity
        self._channels = channels
        self._buffer = np.zeros((capacity, channels), dtype=np.float32)
        self._write_pos = 0
        self._samples_written = 0

    def write(self, data: np.ndarray) -> int:
        """Write samples to buffer. Returns number of samples written."""
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        if data.shape[1] != self._channels:
            raise ValueError(f"Expected {self._channels} channels, got {data.shape[1]}")

        samples = data.shape[0]
        if samples > self._capacity:
            # Only keep last capacity samples
            data = data[-self._capacity:]
            samples = self._capacity

        end_pos = self._write_pos + samples
        if end_pos <= self._capacity:
            self._buffer[self._write_pos:end_pos] = data
        else:
            first_part = self._capacity - self._write_pos
            self._buffer[self._write_pos:] = data[:first_part]
            self._buffer[:samples - first_part] = data[first_part:]

        self._write_pos = end_pos % self._capacity
        self._samples_written += samples
        return samples

    def read(self, samples: int) -> np.ndarray | None:
        """Read last N samples from buffer. Returns None if not enough data."""
        if self._samples_written < samples:
            return None

        end_pos = self._write_pos
        start_pos = end_pos - samples
        if start_pos >= 0:
            return self._buffer[start_pos:end_pos].copy()
        else:
            return np.vstack([
                self._buffer[start_pos:],
                self._buffer[:end_pos]
            ])

    @property
    def available(self) -> int:
        """Number of samples available in buffer."""
        return min(self._samples_written, self._capacity)

    def clear(self) -> None:
        """Clear the buffer."""
        self._buffer.fill(0)
        self._write_pos = 0
        self._samples_written = 0


def _gcc_phat(sig: np.ndarray, refsig: np.ndarray, fs: int, max_tau: float | None = None) -> tuple[float, float]:
    """GCC-PHAT time delay estimation."""
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

    cc = np.concatenate((cc[-max_shift:], cc[:max_shift + 1]))
    shift = np.argmax(np.abs(cc)) - max_shift
    tau = shift / float(fs)
    peak = float(np.max(np.abs(cc)))
    mean = float(np.mean(np.abs(cc))) + 1e-12
    ratio = peak / mean
    return tau, ratio


def _pre_emphasis(sig: np.ndarray, coeff: float) -> np.ndarray:
    """Apply pre-emphasis filter."""
    if coeff <= 0:
        return sig
    out = np.empty_like(sig)
    out[0] = sig[0]
    out[1:] = sig[1:] - coeff * sig[:-1]
    return out


class OnlineDOA:
    """
    Online DOA processor for real-time audio streams.

    Usage:
        doa = OnlineDOA(config)
        doa.start()

        # Feed audio chunks as they arrive
        for chunk in audio_stream:
            doa.process_chunk(chunk)
            result = doa.get_latest()
            if result:
                print(f"Bearing: {result.bearing_deg}°")

        doa.stop()
    """

    def __init__(
        self,
        config: DOAConfig,
        on_result: Callable[[DOAResult], None] | None = None,
    ):
        self._config = config
        self._on_result = on_result
        self._timebase = TimeBase()

        # Calculate block size
        self._block_samples = int(config.sample_rate * config.block_ms / 1000)
        self._hop_samples = int(self._block_samples * (1 - config.overlap_ratio))

        # Initialize buffer
        buffer_size = self._block_samples * 4  # 4x block size for safety
        self._buffer = RingBuffer(buffer_size, channels=2)

        # State
        self._smoothed_bearing: float | None = None
        self._block_id = 0
        self._running = False
        self._history: deque[DOAResult] = deque(maxlen=config.max_history)

        # Pre-compute window
        if config.window == "hann":
            self._window = np.hanning(self._block_samples).astype(np.float32)
        else:
            self._window = None

    def start(self) -> None:
        """Start the processor."""
        self._running = True
        self._buffer.clear()
        self._smoothed_bearing = None
        self._block_id = 0
        self._history.clear()

    def stop(self) -> None:
        """Stop the processor."""
        self._running = False

    def process_chunk(self, chunk: np.ndarray) -> DOAResult | None:
        """
        Process an audio chunk.

        Args:
            chunk: Audio data of shape (samples,) for mono or (samples, channels) for multi-channel

        Returns:
            DOAResult if a new estimate was computed, None otherwise
        """
        if not self._running:
            return None

        # Normalize input
        if chunk.ndim == 1:
            chunk = np.column_stack([chunk, chunk])  # Duplicate for stereo
        if chunk.dtype != np.float32:
            if chunk.dtype == np.int16:
                chunk = chunk.astype(np.float32) / 32768.0
            else:
                chunk = chunk.astype(np.float32)

        # Write to buffer
        self._buffer.write(chunk)

        # Check if we have enough data
        if self._buffer.available < self._block_samples:
            return None

        # Read block
        block = self._buffer.read(self._block_samples)
        if block is None:
            return None

        # Estimate bearing
        result = self._estimate_bearing(block)

        # Store and notify
        self._history.append(result)
        if self._on_result:
            self._on_result(result)

        self._block_id += 1
        return result

    def _estimate_bearing(self, block: np.ndarray) -> DOAResult:
        """Estimate bearing from audio block."""
        cfg = self._config

        # Apply window and pre-emphasis
        def prep(channel: np.ndarray) -> np.ndarray:
            out = channel
            if self._window is not None:
                out = out * self._window
            return _pre_emphasis(out, cfg.pre_emphasis)

        channels = [prep(block[:, i]) for i in range(block.shape[1])]

        # Determine microphone pairs
        pairs: list[tuple[int, int]] = []
        if cfg.pair_mode == "adjacent":
            pairs = [(i, i + 1) for i in range(block.shape[1] - 1)]
        else:
            pairs = [(0, i) for i in range(1, block.shape[1])]

        # Estimate angle from each pair
        angles: list[float] = []
        weights: list[float] = []
        for i, j in pairs:
            distance = cfg.mic_distance_m * abs(i - j)
            if distance <= 0:
                continue

            tdoa, ratio = _gcc_phat(
                channels[i], channels[j], cfg.sample_rate,
                max_tau=distance / cfg.speed_sound_m_s
            )
            value = (tdoa * cfg.speed_sound_m_s) / distance
            value = float(np.clip(value, -1.0, 1.0))
            angle_rad = math.asin(value)
            angle = math.degrees(angle_rad)
            conf = float(ratio / (ratio + 1.0))
            angles.append(angle)
            weights.append(conf)

        # Combine estimates
        timestamp_ms = int(time.time() * 1000)

        if not angles:
            return DOAResult(
                bearing_deg=None,
                confidence=0.0,
                status="NO_SIGNAL",
                timestamp_ms=timestamp_ms,
                block_id=self._block_id,
            )

        total_weight = sum(weights)
        if total_weight <= 0:
            return DOAResult(
                bearing_deg=None,
                confidence=0.0,
                status="LOW_CONFIDENCE",
                timestamp_ms=timestamp_ms,
                block_id=self._block_id,
            )

        raw_bearing = sum(a * w for a, w in zip(angles, weights)) / total_weight
        confidence = max(weights)

        if confidence < cfg.conf_threshold:
            return DOAResult(
                bearing_deg=None,
                confidence=confidence,
                status="LOW_CONFIDENCE",
                timestamp_ms=timestamp_ms,
                block_id=self._block_id,
            )

        # Apply smoothing
        if self._smoothed_bearing is None:
            self._smoothed_bearing = raw_bearing
        else:
            self._smoothed_bearing = (
                self._smoothed_bearing * (1 - cfg.smoothing) +
                raw_bearing * cfg.smoothing
            )

        return DOAResult(
            bearing_deg=self._smoothed_bearing,
            confidence=confidence,
            status="OK",
            timestamp_ms=timestamp_ms,
            block_id=self._block_id,
        )

    def get_latest(self) -> DOAResult | None:
        """Get the most recent DOA result."""
        if self._history:
            return self._history[-1]
        return None

    def get_history(self, count: int | None = None) -> list[DOAResult]:
        """Get recent DOA results."""
        if count is None:
            return list(self._history)
        return list(self._history)[-count:]

    def to_observation(self, result: DOAResult) -> dict:
        """Convert DOAResult to observation record format."""
        return {
            "version": "0.1",
            "time": self._timebase.now(),
            "source": "audio",
            "bearing_deg": result.bearing_deg,
            "roi": None,
            "confidence": result.confidence if result.bearing_deg is not None else None,
            "status": result.status,
            "extras": {"block_id": result.block_id, "online": True},
        }


class AudioStreamDOA:
    """
    Async wrapper for OnlineDOA with sounddevice integration.

    Usage:
        async with AudioStreamDOA(config) as doa:
            async for result in doa.stream():
                print(f"Bearing: {result.bearing_deg}°")
    """

    def __init__(self, config: DOAConfig, device: int | str | None = None):
        self._config = config
        self._device = device
        self._doa = OnlineDOA(config)
        self._stream = None
        self._queue: asyncio.Queue[DOAResult] = asyncio.Queue()

    async def __aenter__(self) -> "AudioStreamDOA":
        await self.start()
        return self

    async def __aexit__(self, *args) -> None:
        await self.stop()

    async def start(self) -> None:
        """Start audio capture and DOA processing."""
        try:
            import sounddevice as sd
        except ImportError:
            raise RuntimeError("sounddevice is required for AudioStreamDOA")

        def callback(indata, frames, time_info, status):
            if status:
                pass  # Log status if needed
            result = self._doa.process_chunk(indata.copy())
            if result and result.bearing_deg is not None:
                try:
                    self._queue.put_nowait(result)
                except asyncio.QueueFull:
                    pass

        self._doa.start()
        self._stream = sd.InputStream(
            samplerate=self._config.sample_rate,
            channels=2,
            dtype=np.float32,
            blocksize=self._doa._hop_samples,
            device=self._device,
            callback=callback,
        )
        self._stream.start()

    async def stop(self) -> None:
        """Stop audio capture."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._doa.stop()

    async def stream(self):
        """Async generator yielding DOA results."""
        while True:
            try:
                result = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield result
            except asyncio.TimeoutError:
                continue

    def get_latest(self) -> DOAResult | None:
        """Get the most recent result."""
        return self._doa.get_latest()


async def main() -> int:
    """Demo: run online DOA processing."""
    import argparse

    parser = argparse.ArgumentParser(description="Online DOA (Sprint 6)")
    parser.add_argument("--device", type=int, help="Audio device index")
    parser.add_argument("--duration", type=float, default=30.0, help="Duration in seconds")
    args = parser.parse_args()

    config = DOAConfig(
        mic_distance_m=0.05,
        sample_rate=16000,
        block_ms=100,
        smoothing=0.4,
    )

    print(f"Starting online DOA for {args.duration}s...")
    print("Press Ctrl+C to stop")

    try:
        async with AudioStreamDOA(config, device=args.device) as doa:
            start_time = time.monotonic()
            async for result in doa.stream():
                elapsed = time.monotonic() - start_time
                if elapsed > args.duration:
                    break
                print(f"[{elapsed:6.1f}s] Bearing: {result.bearing_deg:6.1f}° | Conf: {result.confidence:.2f}")
    except KeyboardInterrupt:
        print("\nStopped by user")

    return 0


if __name__ == "__main__":
    import asyncio
    raise SystemExit(asyncio.run(main()))
