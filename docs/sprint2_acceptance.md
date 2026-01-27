# Sprint 2 Acceptance (PC)

## Quick Start

1) Install deps (once):

```
pip install -r requirements.txt
```

2) Run YOLO on latest run video:

```
python apps/vision/yolo_infer.py --config configs/vision.yaml --run latest
```

3) Optional live camera:

```
python apps/vision/yolo_infer.py --config configs/vision.yaml --camera 0
```

## Expected Outputs

- runs/<run_id>/observations/vision_yolo.jsonl
- runs/<run_id>/events.jsonl (TARGET_DETECTED entries)
- runs/<run_id>/events/vision/*.jpg (event snapshots)
- runs/<run_id>/metrics.jsonl (vision_perf entries)

## Notes

- For replay tuning, reuse the same run and change `configs/vision.yaml`.
- If model download is blocked, put a local `yolov8n.pt` and set `vision.model` to its path.
- Use `frame_skip` or `max_fps` to control CPU on the 2GB device.
- Use `class_filter` to restrict detections (e.g. ["person"]).
