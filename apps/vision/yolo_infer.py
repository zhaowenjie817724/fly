from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import cv2


def _add_repo_to_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


repo_root = _add_repo_to_path()

from apps.acquisition.config_utils import load_config  # noqa: E402
from apps.acquisition.stats import StatsCounter  # noqa: E402
from src.common.resource_monitor import ResourceMonitor  # noqa: E402
from src.common.timebase import TimeBase  # noqa: E402

def load_frame_times(index_path: Path) -> list[dict]:
    times: list[dict] = []
    if not index_path.exists():
        return times
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
                times.append(time_obj)
    return times


def bearing_from_roi(roi: dict, frame_w: int, fov_deg: float) -> float:
    if frame_w <= 0:
        return 0.0
    center_x = roi["x"] + roi["w"] / 2.0
    offset = (center_x - frame_w / 2.0) / frame_w
    return float(offset * fov_deg)


def filter_roi(roi: dict, filter_cfg: dict) -> tuple[bool, str]:
    """Sprint 2: ROI误报过滤策略

    Returns:
        (passed, reason): passed=True表示通过过滤，reason为拒绝原因
    """
    if not filter_cfg.get("enabled", False):
        return True, ""

    frame_w = roi.get("frame_w", 1)
    frame_h = roi.get("frame_h", 1)
    w = roi.get("w", 0)
    h = roi.get("h", 0)
    x = roi.get("x", 0)
    y = roi.get("y", 0)

    frame_area = frame_w * frame_h
    roi_area = w * h

    # 面积比例过滤
    if frame_area > 0:
        area_ratio = roi_area / frame_area
        min_ratio = filter_cfg.get("min_area_ratio", 0.005)
        max_ratio = filter_cfg.get("max_area_ratio", 0.6)
        if area_ratio < min_ratio:
            return False, f"area_too_small({area_ratio:.4f}<{min_ratio})"
        if area_ratio > max_ratio:
            return False, f"area_too_large({area_ratio:.4f}>{max_ratio})"

    # 宽高比过滤
    if h > 0:
        aspect = w / h
        min_aspect = filter_cfg.get("min_aspect_ratio", 0.2)
        max_aspect = filter_cfg.get("max_aspect_ratio", 5.0)
        if aspect < min_aspect or aspect > max_aspect:
            return False, f"aspect_invalid({aspect:.2f})"

    # 边缘排除
    margin = filter_cfg.get("edge_margin_px", 10)
    if x < margin or y < margin:
        return False, "near_edge_top_left"
    if x + w > frame_w - margin or y + h > frame_h - margin:
        return False, "near_edge_bottom_right"

    return True, ""


def write_event(handle, time_obj: dict, obs_id: str, note: str) -> None:
    record = {
        "version": "0.1",
        "time": time_obj,
        "type": "TARGET_DETECTED",
        "severity": "INFO",
        "ref": {"observation_id": obs_id},
        "note": note,
    }
    handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def run_inference(config: dict, run_dir: Path, source_video: Path | None, camera_index: int | None) -> None:
    vision_cfg = config.get("vision", {})
    model_name = str(vision_cfg.get("model", "yolov8n.pt"))
    conf_thres = float(vision_cfg.get("conf_threshold", 0.35))
    imgsz = int(vision_cfg.get("imgsz", 640))
    device = str(vision_cfg.get("device", "cpu"))
    frame_skip = max(1, int(vision_cfg.get("frame_skip", 1)))
    max_fps = float(vision_cfg.get("max_fps", 0))
    max_detections = int(vision_cfg.get("max_detections", 20))
    emit_no_signal = bool(vision_cfg.get("emit_no_signal", True))
    no_signal_interval = float(vision_cfg.get("no_signal_interval_sec", 2.0))
    event_min_interval = float(vision_cfg.get("event_min_interval_sec", 2.0))
    fov_deg = float(vision_cfg.get("camera_fov_deg", 90.0))
    save_annotated = bool(vision_cfg.get("save_annotated", False))
    annotate_every_n = int(vision_cfg.get("annotate_every_n", 0))
    class_filter_cfg = vision_cfg.get("class_filter", [])
    roi_filter_cfg = vision_cfg.get("roi_filter", {})

    obs_dir = run_dir / "observations"
    obs_dir.mkdir(parents=True, exist_ok=True)
    obs_path = obs_dir / "vision_yolo.jsonl"
    metrics_path = run_dir / "metrics.jsonl"
    events_path = run_dir / "events.jsonl"

    snapshots_dir = run_dir / "events" / "vision"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    try:
        from ultralytics import YOLO
    except Exception as exc:
        raise RuntimeError(f"ultralytics is required for YOLO inference: {exc}") from exc

    model = YOLO(model_name)
    class_ids = None
    if class_filter_cfg:
        if isinstance(class_filter_cfg, str):
            class_filter_cfg = [item.strip() for item in class_filter_cfg.split(",") if item.strip()]
        names = model.names
        if isinstance(names, dict):
            name_to_id = {v: int(k) for k, v in names.items()}
        else:
            name_to_id = {v: idx for idx, v in enumerate(names)}
        selected = set()
        for item in class_filter_cfg:
            if isinstance(item, (int, float)):
                selected.add(int(item))
                continue
            item_str = str(item)
            if item_str.isdigit():
                selected.add(int(item_str))
                continue
            if item_str in name_to_id:
                selected.add(name_to_id[item_str])
        if selected:
            class_ids = selected
    timebase = TimeBase()
    stats = StatsCounter()
    resource = ResourceMonitor()

    cap = None
    frame_times: list[dict] = []
    if source_video:
        cap = cv2.VideoCapture(str(source_video))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video: {source_video}")
        index_path = run_dir / "video" / "frame_index.jsonl"
        frame_times = load_frame_times(index_path)
    else:
        cap = cv2.VideoCapture(int(camera_index or 0), cv2.CAP_DSHOW)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open camera device {camera_index}")

    frame_id = 0
    frames_read = 0
    last_no_signal = 0.0
    last_event = 0.0
    start_time = time.perf_counter()
    next_metrics = start_time + float(vision_cfg.get("metrics_interval_sec", 5))
    next_infer = start_time
    infer_sum_ms = 0.0
    infer_count = 0

    with obs_path.open("w", encoding="utf-8") as obs_handle, metrics_path.open("a", encoding="utf-8") as metrics_handle, events_path.open(
        "a",
        encoding="utf-8",
    ) as events_handle:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frames_read += 1

            if frame_id < len(frame_times):
                time_obj = frame_times[frame_id]
            else:
                time_obj = timebase.now()

            if frame_id % frame_skip != 0:
                frame_id += 1
                continue

            if max_fps > 0:
                next_infer += 1.0 / max_fps
                time.sleep(max(0.0, next_infer - time.perf_counter()))

            t_start = time.perf_counter()
            results = model.predict(
                frame,
                conf=conf_thres,
                imgsz=imgsz,
                device=device,
                verbose=False,
            )
            infer_ms = (time.perf_counter() - t_start) * 1000
            infer_sum_ms += infer_ms
            infer_count += 1

            detections = []
            for result in results:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    conf = float(box.conf.item())
                    if conf < conf_thres:
                        continue
                    cls_id = int(box.cls.item())
                    if class_ids is not None and cls_id not in class_ids:
                        continue
                    xyxy = box.xyxy[0].tolist()
                    x1, y1, x2, y2 = [int(v) for v in xyxy]
                    roi = {
                        "x": x1,
                        "y": y1,
                        "w": max(0, x2 - x1),
                        "h": max(0, y2 - y1),
                        "frame_w": int(frame.shape[1]),
                        "frame_h": int(frame.shape[0]),
                    }
                    # Sprint 2: ROI误报过滤
                    passed, reject_reason = filter_roi(roi, roi_filter_cfg)
                    if not passed:
                        continue
                    bearing = bearing_from_roi(roi, frame.shape[1], fov_deg)
                    detections.append((conf, cls_id, roi, bearing))

            detections.sort(key=lambda item: item[0], reverse=True)
            if max_detections > 0:
                detections = detections[:max_detections]

            if detections:
                annotated = frame
                if save_annotated:
                    annotated = frame.copy()
                    for conf, cls_id, roi, _bearing in detections:
                        x1 = roi["x"]
                        y1 = roi["y"]
                        x2 = roi["x"] + roi["w"]
                        y2 = roi["y"] + roi["h"]
                        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(
                            annotated,
                            f"{cls_id}:{conf:.2f}",
                            (x1, max(15, y1 - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (0, 255, 0),
                            1,
                        )

                for idx, (conf, cls_id, roi, bearing) in enumerate(detections):
                    obs_id = f"{frame_id}-{idx}"
                    record = {
                        "version": "0.1",
                        "time": time_obj,
                        "source": "vision",
                        "bearing_deg": bearing,
                        "roi": roi,
                        "confidence": conf,
                        "status": "OK",
                        "extras": {"class_id": cls_id, "obs_id": obs_id},
                    }
                    obs_handle.write(json.dumps(record, ensure_ascii=True) + "\n")

                now = time.time()
                if now - last_event >= event_min_interval:
                    conf, cls_id, roi, bearing = detections[0]
                    snapshot_path = snapshots_dir / f"det_{frame_id:06d}.jpg"
                    cv2.imwrite(str(snapshot_path), annotated if save_annotated else frame)
                    write_event(
                        events_handle,
                        time_obj,
                        f"{frame_id}-0",
                        f"cls={cls_id} conf={conf:.2f} bearing={bearing:.1f}",
                    )
                    last_event = now

                if save_annotated and annotate_every_n > 0 and frame_id % annotate_every_n == 0:
                    snap_path = snapshots_dir / f"annot_{frame_id:06d}.jpg"
                    cv2.imwrite(str(snap_path), annotated)
            elif emit_no_signal:
                now = time.time()
                if now - last_no_signal >= no_signal_interval:
                    record = {
                        "version": "0.1",
                        "time": time_obj,
                        "source": "vision",
                        "bearing_deg": None,
                        "roi": None,
                        "confidence": None,
                        "status": "NO_SIGNAL",
                        "extras": {"obs_id": f"{frame_id}-none"},
                    }
                    obs_handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                    last_no_signal = now

            stats.increment()
            frame_id += 1

            now_perf = time.perf_counter()
            if now_perf >= next_metrics:
                snap = stats.snapshot()
                res = resource.snapshot()
                metrics = {
                    "version": "0.1",
                    "time": timebase.now(),
                    "type": "vision_perf",
                    "payload": {
                        "fps": snap["rate_hz"],
                        "frames_read": frames_read,
                        "frames_inferred": snap["interval_count"],
                        "avg_infer_ms": infer_sum_ms / infer_count if infer_count else 0.0,
                        "cpu_total_pct": res.cpu_total_pct,
                        "cpu_process_pct": res.cpu_process_pct,
                        "mem_rss_mb": res.mem_rss_mb,
                        "mem_percent": res.mem_percent,
                    },
                }
                metrics_handle.write(json.dumps(metrics, ensure_ascii=True) + "\n")
                next_metrics = now_perf + float(vision_cfg.get("metrics_interval_sec", 5))
                infer_sum_ms = 0.0
                infer_count = 0

    cap.release()


def main() -> int:
    parser = argparse.ArgumentParser(description="YOLO inference runner (Sprint 2)")
    parser.add_argument("--config", default="configs/vision.yaml", help="Config file")
    parser.add_argument("--run", default="latest", help="Run id/path to use for output")
    parser.add_argument("--video", help="Optional video path (default uses run video)")
    parser.add_argument("--camera", type=int, help="Optional camera index for live capture")
    args = parser.parse_args()

    repo_root = _add_repo_to_path()
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

    source_video = None
    if args.video:
        source_video = Path(args.video)
    elif args.camera is None:
        candidate = run_dir / "video" / "video.mp4"
        if candidate.exists():
            source_video = candidate

    run_inference(config, run_dir, source_video, args.camera)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
