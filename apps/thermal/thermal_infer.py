"""
Thermal camera inference runner.

支持硬件：
  - FLIR Lepton (PureThermal USB)：/dev/video1，Y16 16-bit 灰度，160x120 或 160x122
  - SEEK Thermal Compact：/dev/video1，灰度
  - 通用 V4L2 USB 热成像（任何输出灰度或 YUV 的 USB 热像仪）
  - mock 模式：无硬件时生成合成热图用于测试

输出：runs/*/observations/thermal_obs.jsonl
格式：{"version":"0.1","time":{...},"source":"thermal","bearing_deg":float,
       "roi":{...},"confidence":float,"status":"OK"|"NO_SIGNAL","extras":{...}}
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import time
from pathlib import Path

import cv2
import numpy as np


def _add_repo_to_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


repo_root = _add_repo_to_path()

from apps.acquisition.config_utils import load_config  # noqa: E402
from src.common.timebase import TimeBase  # noqa: E402


def bearing_from_cx(cx: int, frame_w: int, fov_deg: float) -> float:
    """将热点水平像素坐标转换为方位角（度）。中心=0°，右正左负。"""
    if frame_w <= 0:
        return 0.0
    offset = (cx - frame_w / 2.0) / frame_w
    return float(offset * fov_deg)


def find_hotspot(
    frame_gray: np.ndarray,
    percentile: float,
    min_area_px: int,
) -> tuple[int, int, float] | None:
    """在热图中找到最热区域（热点）。

    Args:
        frame_gray: 单通道灰度图（uint8 或 uint16）
        percentile:  亮度阈值百分位（95 表示取亮度前 5%）
        min_area_px: 热点最小面积（像素数），过滤噪声

    Returns:
        (cx, cy, confidence) 或 None（未检测到有效热点）
    """
    if frame_gray.dtype == np.uint16:
        # 16-bit 归一化到 8-bit
        frame_8 = cv2.normalize(frame_gray, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
    else:
        frame_8 = frame_gray

    thresh_val = float(np.percentile(frame_8, percentile))
    # 极端情况：全图均匀时跳过
    if thresh_val >= 254:
        return None

    _, binary = cv2.threshold(frame_8, thresh_val, 255, cv2.THRESH_BINARY)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    if num_labels <= 1:
        return None

    # 跳过背景 label=0，找最大连通区域
    areas = stats[1:, cv2.CC_STAT_AREA]
    best_idx = int(np.argmax(areas)) + 1
    area = int(areas[best_idx - 1])

    if area < min_area_px:
        return None

    cx = int(centroids[best_idx][0])
    cy = int(centroids[best_idx][1])

    # 置信度：该热点面积占所有亮区面积的比例（独立热点置信高）
    total_bright = max(int(np.sum(binary > 0)), 1)
    confidence = float(min(1.0, area / total_bright))

    return cx, cy, confidence


def run_thermal_inference(config: dict, run_dir: Path, camera_index: int) -> None:
    thermal_cfg = config.get("thermal", {})
    fov_deg = float(thermal_cfg.get("fov_deg", 50.0))
    hotspot_percentile = float(thermal_cfg.get("hotspot_percentile", 95.0))
    min_area_px = int(thermal_cfg.get("min_area_px", 30))
    max_fps = float(thermal_cfg.get("max_fps", 9.0))   # FLIR Lepton 9 Hz
    emit_no_signal = bool(thermal_cfg.get("emit_no_signal", True))
    no_signal_interval = float(thermal_cfg.get("no_signal_interval_sec", 2.0))
    save_snapshots = bool(thermal_cfg.get("save_snapshots", False))
    snapshot_interval_sec = float(thermal_cfg.get("snapshot_interval_sec", 10.0))
    mock_mode = str(thermal_cfg.get("mode", "device")).lower() == "mock"

    obs_dir = run_dir / "observations"
    obs_dir.mkdir(parents=True, exist_ok=True)
    obs_path = obs_dir / "thermal_obs.jsonl"

    snapshots_dir = run_dir / "events" / "thermal"
    if save_snapshots:
        snapshots_dir.mkdir(parents=True, exist_ok=True)

    timebase = TimeBase()

    # --- 打开摄像头 ---
    if mock_mode:
        cap = None
        print("Thermal inference: mock mode (no camera required)", flush=True)
    else:
        _backend = cv2.CAP_V4L2 if platform.system() == "Linux" else cv2.CAP_DSHOW
        cap = cv2.VideoCapture(camera_index, _backend)

        # 尝试 Y16（16-bit 灰度，PureThermal USB Lepton）
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"Y16 "))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            raise RuntimeError(
                f"Failed to open thermal camera at device {camera_index}. "
                "Check that the camera is connected and not busy."
            )
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(
            f"Thermal camera opened: device={camera_index}, "
            f"res={actual_w}x{actual_h}, fov={fov_deg}°",
            flush=True,
        )

    frame_id = 0
    last_no_signal = 0.0
    last_snapshot = 0.0
    start_time = time.perf_counter()
    next_frame = start_time

    with obs_path.open("w", encoding="utf-8") as obs_handle:
        while True:
            time_obj = timebase.now()

            if mock_mode:
                # 生成合成热图：随机游走热点，模拟人体热特征
                frame_h, frame_w = 120, 160
                frame_gray = np.random.randint(60, 80, (frame_h, frame_w), dtype=np.uint8)
                # 在随机位置放一个高斯热点
                t = time.time()
                hx = int(frame_w / 2 + math.sin(t * 0.3) * frame_w * 0.3)
                hy = int(frame_h / 2 + math.cos(t * 0.2) * frame_h * 0.2)
                hx = max(10, min(frame_w - 10, hx))
                hy = max(10, min(frame_h - 10, hy))
                cv2.circle(frame_gray, (hx, hy), 12, 210, -1)
                # 加高斯模糊使其自然
                frame_gray = cv2.GaussianBlur(frame_gray, (7, 7), 0)
                ret = True
            else:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue
                if len(frame.shape) == 3:
                    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                else:
                    frame_gray = frame
                frame_h, frame_w = frame_gray.shape[:2]

            frame_id += 1

            # 限速
            if max_fps > 0:
                next_frame += 1.0 / max_fps
                time.sleep(max(0.0, next_frame - time.perf_counter()))

            result = find_hotspot(frame_gray, hotspot_percentile, min_area_px)

            if result is not None:
                cx, cy, confidence = result
                bearing = bearing_from_cx(cx, frame_w, fov_deg)

                record = {
                    "version": "0.1",
                    "time": time_obj,
                    "source": "thermal",
                    "bearing_deg": round(bearing, 2),
                    "roi": {
                        "x": max(0, cx - 8),
                        "y": max(0, cy - 8),
                        "w": 16,
                        "h": 16,
                        "frame_w": frame_w,
                        "frame_h": frame_h,
                    },
                    "confidence": round(confidence, 3),
                    "status": "OK",
                    "extras": {
                        "hotspot_cx": cx,
                        "hotspot_cy": cy,
                        "frame_id": frame_id,
                        "mock": mock_mode,
                    },
                }
                obs_handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                obs_handle.flush()

                if save_snapshots:
                    now = time.time()
                    if now - last_snapshot >= snapshot_interval_sec:
                        snap = cv2.normalize(
                            frame_gray, None, 0, 255, cv2.NORM_MINMAX
                        ).astype(np.uint8)
                        snap = cv2.applyColorMap(snap, cv2.COLORMAP_INFERNO)
                        cv2.circle(snap, (cx, cy), 5, (0, 255, 0), 2)
                        cv2.putText(
                            snap,
                            f"{bearing:.1f}deg {confidence:.2f}",
                            (cx + 8, cy),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.4,
                            (0, 255, 0),
                            1,
                        )
                        cv2.imwrite(str(snapshots_dir / f"thermal_{frame_id:06d}.jpg"), snap)
                        last_snapshot = now

            elif emit_no_signal:
                now = time.time()
                if now - last_no_signal >= no_signal_interval:
                    record = {
                        "version": "0.1",
                        "time": time_obj,
                        "source": "thermal",
                        "bearing_deg": None,
                        "roi": None,
                        "confidence": None,
                        "status": "NO_SIGNAL",
                        "extras": {"frame_id": frame_id, "mock": mock_mode},
                    }
                    obs_handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                    obs_handle.flush()
                    last_no_signal = now

    if cap is not None:
        cap.release()


def main() -> int:
    parser = argparse.ArgumentParser(description="Thermal camera inference runner")
    parser.add_argument("--config", default="configs/pi_stereo.yaml", help="Config file")
    parser.add_argument("--run", default="latest", help="Run id/path")
    parser.add_argument(
        "--camera", type=int, default=None, help="Thermal camera device index (overrides config)"
    )
    args = parser.parse_args()

    repo_root = _add_repo_to_path()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()
    config = load_config(config_path)

    thermal_cfg = config.get("thermal", {})
    camera_index = (
        args.camera if args.camera is not None
        else int(thermal_cfg.get("device_index", 1))
    )

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

    run_thermal_inference(config, run_dir, camera_index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
