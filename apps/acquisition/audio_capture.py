from __future__ import annotations

import json
import queue
import threading
import time
import wave
from pathlib import Path

import numpy as np

from .stats import StatsCounter


class AudioCapture:
    def __init__(self, config: dict, output_dir: Path, timebase, logger) -> None:
        self.config = config
        self.output_dir = output_dir
        self.timebase = timebase
        self.logger = logger
        self.stats = StatsCounter()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="audio-capture", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def _run(self) -> None:
        if not self.config.get("enabled", False):
            self.logger.info("Audio disabled")
            return

        mode = self.config.get("mode", "disabled")
        if mode == "disabled":
            self.logger.info("Audio mode disabled")
            return

        sample_rate = int(self.config.get("sample_rate", 16000))
        channels = int(self.config.get("channels", 1))
        block_ms = float(self.config.get("block_ms", 20))
        block_samples = max(1, int(sample_rate * block_ms / 1000.0))

        audio_path = self.output_dir / "audio.wav"
        index_path = self.output_dir / "audio_index.jsonl"

        if mode == "mic":
            self._run_mic(audio_path, index_path, sample_rate, channels, block_samples)
        elif mode == "wav_file":
            input_wav = self.config.get("input_wav", "")
            if not input_wav:
                self.logger.error("audio.input_wav is required for wav_file mode")
                return
            self._run_wav_file(Path(input_wav), audio_path, index_path, sample_rate, channels, block_samples)
        elif mode == "mock":
            self._run_mock(audio_path, index_path, sample_rate, channels, block_samples)
        else:
            self.logger.error("Unsupported audio mode: %s", mode)

    def _write_wave_header(self, handle: wave.Wave_write, sample_rate: int, channels: int) -> None:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)

    def _run_mock(
        self,
        audio_path: Path,
        index_path: Path,
        sample_rate: int,
        channels: int,
        block_samples: int,
    ) -> None:
        freq = 440.0
        phase = 0.0
        step = 2 * np.pi * freq / sample_rate
        block_duration = block_samples / sample_rate
        next_tick = time.perf_counter()

        with wave.open(str(audio_path), "wb") as wav_handle, index_path.open("w", encoding="utf-8") as idx:
            self._write_wave_header(wav_handle, sample_rate, channels)
            block_id = 0
            while not self._stop_event.is_set():
                times = self.timebase.now()
                t = phase + step * np.arange(block_samples)
                signal = (0.2 * np.sin(t)).astype(np.float32)
                phase = t[-1] + step
                audio = np.tile(signal[:, None], (1, channels))
                audio_i16 = (audio * 32767).astype(np.int16)
                wav_handle.writeframes(audio_i16.tobytes())

                record = {
                    "block_id": block_id,
                    "t_mono_ms": times["t_mono_ms"],
                    "t_wall_ms": times["t_wall_ms"],
                    "samples": block_samples,
                    "channels": channels,
                    "overrun": False,
                }
                idx.write(json.dumps(record, ensure_ascii=True) + "\n")
                self.stats.increment()
                block_id += 1

                next_tick += block_duration
                time.sleep(max(0.0, next_tick - time.perf_counter()))

    def _run_wav_file(
        self,
        input_path: Path,
        audio_path: Path,
        index_path: Path,
        sample_rate: int,
        channels: int,
        block_samples: int,
    ) -> None:
        if not input_path.exists():
            self.logger.error("Input wav not found: %s", input_path)
            return

        block_duration = block_samples / sample_rate
        next_tick = time.perf_counter()
        block_id = 0

        with wave.open(str(input_path), "rb") as src, wave.open(str(audio_path), "wb") as dst:
            self._write_wave_header(dst, sample_rate, channels)
            with index_path.open("w", encoding="utf-8") as idx:
                while not self._stop_event.is_set():
                    data = src.readframes(block_samples)
                    if not data:
                        src.rewind()
                        continue

                    times = self.timebase.now()
                    dst.writeframes(data)
                    record = {
                        "block_id": block_id,
                        "t_mono_ms": times["t_mono_ms"],
                        "t_wall_ms": times["t_wall_ms"],
                        "samples": block_samples,
                        "channels": channels,
                        "overrun": False,
                    }
                    idx.write(json.dumps(record, ensure_ascii=True) + "\n")
                    self.stats.increment()
                    block_id += 1

                    next_tick += block_duration
                    time.sleep(max(0.0, next_tick - time.perf_counter()))

    def _run_mic(
        self,
        audio_path: Path,
        index_path: Path,
        sample_rate: int,
        channels: int,
        block_samples: int,
    ) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:
            self.logger.error("sounddevice not available: %s", exc)
            return

        q: queue.Queue = queue.Queue(maxsize=100)

        def callback(indata, frames, _time, status):
            overrun = bool(status)
            times = self.timebase.now()
            try:
                q.put_nowait((indata.copy(), times, overrun))
            except queue.Full:
                self.stats.add_overrun()

        writer_stop = threading.Event()

        def writer():
            block_id = 0
            with wave.open(str(audio_path), "wb") as wav_handle, index_path.open("w", encoding="utf-8") as idx:
                self._write_wave_header(wav_handle, sample_rate, channels)
                while not writer_stop.is_set() or not q.empty():
                    try:
                        data, times, overrun = q.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    audio_i16 = data
                    if audio_i16.dtype != np.int16:
                        audio_i16 = (audio_i16 * 32767).astype(np.int16)
                    wav_handle.writeframes(audio_i16.tobytes())
                    record = {
                        "block_id": block_id,
                        "t_mono_ms": times["t_mono_ms"],
                        "t_wall_ms": times["t_wall_ms"],
                        "samples": int(data.shape[0]),
                        "channels": int(data.shape[1]) if data.ndim > 1 else 1,
                        "overrun": bool(overrun),
                    }
                    idx.write(json.dumps(record, ensure_ascii=True) + "\n")
                    self.stats.increment()
                    if overrun:
                        self.stats.add_overrun()
                    block_id += 1

        writer_thread = threading.Thread(target=writer, name="audio-writer", daemon=True)
        writer_thread.start()

        with sd.InputStream(
            channels=channels,
            samplerate=sample_rate,
            blocksize=block_samples,
            dtype="int16",
            callback=callback,
        ):
            while not self._stop_event.is_set():
                time.sleep(0.1)

        writer_stop.set()
        writer_thread.join(timeout=5)
