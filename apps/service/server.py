from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

def _add_repo_to_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


repo_root = _add_repo_to_path()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query  # noqa: E402
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse, FileResponse  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from apps.acquisition.config_utils import load_config  # noqa: E402

logger = logging.getLogger("service")


async def _handle_command(payload: dict, state: dict, cfg: dict, commands_path: Path):
    """统一的命令处理逻辑（带速率限制和白名单）"""
    if not isinstance(payload, dict):
        return JSONResponse({"accepted": False, "error": "invalid_payload"}, status_code=400)

    try:
        now = time.monotonic()
        rate_hz = float(cfg.get("command_rate_limit_hz", 5))
        min_interval = 1.0 / rate_hz if rate_hz > 0 else 0.0
        if min_interval and (now - state["last_command_time"]) < min_interval:
            return JSONResponse({"accepted": False, "error": "rate_limited"}, status_code=429)

        cmd_type = str(payload.get("type", "")).upper()
        whitelist = {item.upper() for item in cfg.get("command_whitelist", [])}
        if whitelist and cmd_type not in whitelist:
            return JSONResponse({"accepted": False, "error": "command_not_allowed"}, status_code=400)

        if cmd_type == "SET_YAW":
            params = payload.get("params", {})
            if "yaw_rate_deg_s" not in params:
                params["yaw_rate_deg_s"] = float(cfg.get("default_yaw_rate_deg_s", 30))
            payload["params"] = params

        # 添加时间戳和审计信息
        payload["_timestamp"] = int(time.time() * 1000)
        payload["_source"] = "api"

        commands_path.parent.mkdir(parents=True, exist_ok=True)
        with commands_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
        state["last_command_time"] = now
        return JSONResponse({"accepted": True, "command": cmd_type})
    except Exception as exc:
        logger.exception("Failed to handle command: %s", exc)
        return JSONResponse({"accepted": False, "error": "internal_error"}, status_code=500)


def read_last_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        if size == 0:
            return None
        offset = min(size, 4096)
        handle.seek(-offset, 2)
        chunk = handle.read(offset).decode("utf-8", errors="ignore")
        lines = [line for line in chunk.splitlines() if line.strip()]
        if not lines:
            return None
        try:
            return json.loads(lines[-1])
        except json.JSONDecodeError:
            return None


def update_state(state: dict, event_type: str, payload: dict) -> None:
    now_ms = int(time.time() * 1000)
    if event_type == "telemetry":
        time_obj = payload.get("time") or {}
        state["last_telemetry_epoch_ms"] = int(time_obj.get("epoch_ms", now_ms))
        state["link_status"] = payload.get("link_status", state.get("link_status", "UNKNOWN"))
    elif event_type == "event":
        state["last_event_epoch_ms"] = now_ms
    elif event_type.startswith("observation:"):
        state["last_observation_epoch_ms"] = now_ms


async def tail_paths(websocket: WebSocket, get_paths, state: dict, interval: float = 0.3) -> None:
    positions: dict[Path, int] = {}
    while True:
        paths = get_paths()
        for event_type, path in list(paths.items()):
            if not path.exists():
                continue
            pos = positions.get(path, 0)
            with path.open("r", encoding="utf-8") as handle:
                handle.seek(pos)
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    update_state(state, event_type, payload)
                    await websocket.send_json({"type": event_type, "payload": payload})
                positions[path] = handle.tell()
        await asyncio.sleep(interval)


async def status_loop(websocket: WebSocket, state: dict, interval: float, timeout_sec: float) -> None:
    while True:
        now_ms = int(time.time() * 1000)
        last = state.get("last_telemetry_epoch_ms")
        age_sec = None
        if last:
            age_sec = max(0.0, (now_ms - last) / 1000.0)
        link_status = state.get("link_status", "UNKNOWN")
        if age_sec is not None and timeout_sec > 0 and age_sec >= timeout_sec:
            link_status = "LOST"
        payload = {
            "link_status": link_status,
            "last_telemetry_epoch_ms": last,
            "telemetry_age_sec": age_sec,
            "gcs_label": state.get("gcs_label", "地面站"),
        }
        await websocket.send_json({"type": "status", "payload": payload})
        await asyncio.sleep(interval)


def create_app(run_dir: Path, service_cfg: dict) -> FastAPI:
    app = FastAPI(title="通感之眼2.0 API", version="0.2.0")
    cfg = service_cfg if isinstance(service_cfg, dict) else {}

    # CORS支持（小程序调试用）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    telemetry_path = run_dir / "telemetry" / "telemetry.jsonl"
    events_path = run_dir / "events.jsonl"
    obs_dir = run_dir / "observations"
    commands_path = run_dir / "commands.jsonl"
    dashboard_path = repo_root / "web" / "dashboard.html"
    snapshots_dir = run_dir / "events" / "vision"

    state = {
        "last_telemetry_epoch_ms": None,
        "link_status": "UNKNOWN",
        "gcs_label": "地面站",
        "last_event_epoch_ms": None,
        "last_observation_epoch_ms": None,
        "last_command_time": 0.0,
    }

    # ========== 辅助函数 ==========
    def load_jsonl(path: Path, limit: int = 100, offset: int = 0) -> list[dict]:
        """加载JSONL文件，支持分页"""
        if not path.exists():
            return []
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        # 倒序（最新在前）
        records.reverse()
        return records[offset:offset + limit]

    def get_event_by_id(event_id: str) -> dict | None:
        """根据ID获取事件详情"""
        if not events_path.exists():
            return None
        with events_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    # 用时间戳作为ID
                    time_obj = record.get("time", {})
                    record_id = str(time_obj.get("epoch_ms", ""))
                    if record_id == event_id:
                        return record
                except json.JSONDecodeError:
                    continue
        return None

    # ========== 基础路由 ==========
    @app.get("/")
    @app.get("/dashboard")
    async def root():
        if dashboard_path.exists():
            return HTMLResponse(dashboard_path.read_text(encoding="utf-8"))
        return {"status": "ok", "service": "通感之眼2.0"}

    @app.get("/health")
    async def health():
        """增强型健康检查端点"""
        import shutil
        import psutil

        now_ms = int(time.time() * 1000)
        last_tel = state.get("last_telemetry_epoch_ms")
        tel_age = None
        if last_tel:
            tel_age = (now_ms - last_tel) / 1000.0

        # 检查MAVLink连接状态
        link_status = state.get("link_status", "UNKNOWN")
        timeout = float(cfg.get("telemetry_timeout_sec", 3))
        if tel_age is not None and timeout > 0 and tel_age >= timeout:
            link_status = "LOST"

        # 磁盘空间检查
        try:
            disk = shutil.disk_usage(str(run_dir))
            disk_free_gb = disk.free / (1024**3)
            disk_total_gb = disk.total / (1024**3)
        except Exception:
            disk_free_gb = None
            disk_total_gb = None

        # 内存使用
        try:
            mem = psutil.virtual_memory()
            mem_used_pct = mem.percent
            mem_available_mb = mem.available / (1024**2)
        except Exception:
            mem_used_pct = None
            mem_available_mb = None

        # 整体状态判断
        overall_status = "ok"
        warnings = []
        if link_status == "LOST":
            warnings.append("telemetry_lost")
        if disk_free_gb is not None and disk_free_gb < 1.0:
            warnings.append("low_disk_space")
        if mem_used_pct is not None and mem_used_pct > 90:
            warnings.append("high_memory_usage")

        if warnings:
            overall_status = "degraded"

        return {
            "status": overall_status,
            "warnings": warnings,
            "telemetry": {
                "link_status": link_status,
                "age_sec": tel_age,
            },
            "system": {
                "disk_free_gb": round(disk_free_gb, 2) if disk_free_gb else None,
                "disk_total_gb": round(disk_total_gb, 2) if disk_total_gb else None,
                "mem_used_pct": round(mem_used_pct, 1) if mem_used_pct else None,
                "mem_available_mb": round(mem_available_mb, 0) if mem_available_mb else None,
            },
            "run_dir": str(run_dir),
        }

    @app.get("/status")
    async def status():
        now_ms = int(time.time() * 1000)
        last = state.get("last_telemetry_epoch_ms")
        age_sec = None
        if last:
            age_sec = max(0.0, (now_ms - last) / 1000.0)
        link_status = state.get("link_status", "UNKNOWN")
        timeout = float(cfg.get("telemetry_timeout_sec", 3))
        if age_sec is not None and timeout > 0 and age_sec >= timeout:
            link_status = "LOST"
        return {
            "run_dir": str(run_dir),
            "telemetry_path": str(telemetry_path),
            "events_path": str(events_path),
            "link_status": link_status,
            "telemetry_age_sec": age_sec,
            "gcs_label": state.get("gcs_label", "地面站"),
        }

    # ========== Sprint 5: REST API ==========

    @app.get("/api/events")
    async def api_events(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
        """获取事件列表"""
        events = load_jsonl(events_path, limit=limit, offset=offset)
        # 添加ID和快照路径
        for evt in events:
            time_obj = evt.get("time", {})
            evt["id"] = str(time_obj.get("epoch_ms", ""))
            # 检查是否有快照
            ref = evt.get("ref", {})
            obs_id = ref.get("observation_id", "")
            if obs_id:
                frame_id = obs_id.split("-")[0] if "-" in obs_id else obs_id
                snapshot_path = snapshots_dir / f"det_{int(frame_id):06d}.jpg"
                if snapshot_path.exists():
                    evt["snapshot"] = f"/api/snapshot/{frame_id}"
        return {"total": len(events), "events": events}

    @app.get("/api/events/{event_id}")
    async def api_event_detail(event_id: str):
        """获取事件详情"""
        event = get_event_by_id(event_id)
        if not event:
            return JSONResponse({"error": "event_not_found"}, status_code=404)
        # 添加快照
        ref = event.get("ref", {})
        obs_id = ref.get("observation_id", "")
        if obs_id:
            frame_id = obs_id.split("-")[0] if "-" in obs_id else obs_id
            snapshot_path = snapshots_dir / f"det_{int(frame_id):06d}.jpg"
            if snapshot_path.exists():
                event["snapshot"] = f"/api/snapshot/{frame_id}"
        return event

    @app.get("/api/snapshot/{frame_id}")
    async def api_snapshot(frame_id: str):
        """获取事件快照图片"""
        try:
            fid = int(frame_id)
            snapshot_path = snapshots_dir / f"det_{fid:06d}.jpg"
            if snapshot_path.exists():
                return FileResponse(snapshot_path, media_type="image/jpeg")
        except ValueError:
            pass
        return JSONResponse({"error": "snapshot_not_found"}, status_code=404)

    @app.get("/api/observations")
    async def api_observations(source: str = Query(None), limit: int = Query(20, ge=1, le=100)):
        """获取观测数据"""
        result = []
        if obs_dir.exists():
            for path in obs_dir.glob("*.jsonl"):
                if source and source not in path.stem:
                    continue
                records = load_jsonl(path, limit=limit)
                for r in records:
                    r["_source_file"] = path.stem
                result.extend(records)
        # 按时间排序
        result.sort(key=lambda x: x.get("time", {}).get("epoch_ms", 0), reverse=True)
        return {"observations": result[:limit]}

    @app.get("/api/telemetry")
    async def api_telemetry():
        """获取最新遥测数据"""
        record = read_last_json(telemetry_path)
        if not record:
            return {"telemetry": None}
        return {"telemetry": record}

    @app.get("/api/fsm")
    async def api_fsm():
        """获取FSM状态"""
        # 从events中读取最新MODE_CHANGED事件
        events = load_jsonl(events_path, limit=50)
        for evt in events:
            if evt.get("type") == "MODE_CHANGED":
                return {"fsm_state": evt.get("note", "UNKNOWN"), "time": evt.get("time")}
        return {"fsm_state": "UNKNOWN", "time": None}

    # ========== 控制API ==========

    @app.post("/api/control/yaw")
    async def api_control_yaw(payload: dict):
        """偏航控制"""
        yaw_deg = payload.get("yaw_deg", 0)
        yaw_rate = payload.get("yaw_rate_deg_s", cfg.get("default_yaw_rate_deg_s", 30))
        cmd = {"type": "SET_YAW", "params": {"yaw_deg": yaw_deg, "yaw_rate_deg_s": yaw_rate}}
        return await _handle_command(cmd, state, cfg, commands_path)

    @app.post("/api/control/mode")
    async def api_control_mode(payload: dict):
        """模式切换"""
        mode = payload.get("mode", "LOITER")
        cmd = {"type": "SET_MODE", "params": {"mode": mode}}
        return await _handle_command(cmd, state, cfg, commands_path)

    @app.post("/api/control/estop")
    async def api_control_estop():
        """急停"""
        cmd = {"type": "STOP", "params": {}}
        return await _handle_command(cmd, state, cfg, commands_path)

    @app.post("/api/state")
    async def api_state():
        return await status()

    @app.post("/command")
    async def command(payload: dict):
        return await _handle_command(payload, state, cfg, commands_path)

    # ========== 视频流 API ==========

    video_dir = run_dir / "video"
    latest_frame_path = video_dir / "latest.jpg"

    @app.get("/api/video/snapshot")
    async def video_snapshot():
        """获取最新摄像头帧 (JPEG)"""
        if latest_frame_path.exists():
            return FileResponse(str(latest_frame_path), media_type="image/jpeg")
        return JSONResponse({"error": "no_frame"}, status_code=404)

    @app.get("/api/video/mjpeg")
    async def video_mjpeg():
        """MJPEG 视频流 (multipart/x-mixed-replace)"""
        async def generate():
            boundary = b"--frame\r\n"
            last_mtime = 0.0
            while True:
                try:
                    if latest_frame_path.exists():
                        mtime = latest_frame_path.stat().st_mtime
                        if mtime != last_mtime:
                            data = latest_frame_path.read_bytes()
                            last_mtime = mtime
                            yield (
                                boundary
                                + b"Content-Type: image/jpeg\r\n"
                                + f"Content-Length: {len(data)}\r\n\r\n".encode()
                                + data
                                + b"\r\n"
                            )
                except Exception:
                    pass
                await asyncio.sleep(0.05)  # ~20 FPS max poll rate

        return StreamingResponse(
            generate(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        tasks: list[asyncio.Task] = []
        last_pong = {"time": time.monotonic()}
        heartbeat_interval = float(cfg.get("ws_heartbeat_interval_sec", 30))
        heartbeat_timeout = float(cfg.get("ws_heartbeat_timeout_sec", 60))

        async def heartbeat_loop():
            """发送心跳ping并检测超时"""
            while True:
                try:
                    await websocket.send_json({"type": "ping", "payload": {"ts": int(time.time() * 1000)}})
                    # 检查pong超时
                    if (time.monotonic() - last_pong["time"]) > heartbeat_timeout:
                        logger.warning("WebSocket heartbeat timeout, closing connection")
                        await websocket.close(code=1000, reason="heartbeat_timeout")
                        return
                    await asyncio.sleep(heartbeat_interval)
                except Exception:
                    return

        async def receive_loop():
            """接收客户端消息（处理pong和命令）"""
            while True:
                try:
                    data = await websocket.receive_json()
                    msg_type = data.get("type", "")
                    if msg_type == "pong":
                        last_pong["time"] = time.monotonic()
                    elif msg_type == "command":
                        # 支持WebSocket发送命令
                        result = await _handle_command(data.get("payload", {}), state, cfg, commands_path)
                        await websocket.send_json({"type": "command_result", "payload": result.body.decode()})
                except WebSocketDisconnect:
                    return
                except Exception:
                    return

        try:
            def get_paths():
                mapping = {
                    "telemetry": telemetry_path,
                    "event": events_path,
                }
                if obs_dir.exists():
                    for path in obs_dir.glob("*.jsonl"):
                        mapping[f"observation:{path.stem}"] = path
                return mapping

            # Send last known records on connect.
            for event_type, path in get_paths().items():
                payload = read_last_json(path)
                if payload:
                    await websocket.send_json({"type": event_type, "payload": payload})

            state["gcs_label"] = str(cfg.get("gcs_label", "地面站"))
            status_interval = float(cfg.get("status_interval_sec", 1))
            telemetry_timeout = float(cfg.get("telemetry_timeout_sec", 3))
            tasks = [
                asyncio.create_task(tail_paths(websocket, get_paths, state)),
                asyncio.create_task(status_loop(websocket, state, status_interval, telemetry_timeout)),
                asyncio.create_task(heartbeat_loop()),
                asyncio.create_task(receive_loop()),
            ]
            await asyncio.gather(*tasks)
        except WebSocketDisconnect:
            for task in tasks:
                task.cancel()
        except Exception:
            for task in tasks:
                task.cancel()
            raise

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="FastAPI service (Sprint 5)")
    parser.add_argument("--config", default="configs/service.yaml", help="Config file")
    parser.add_argument("--run", default="latest", help="Run id/path to serve")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()
    config = load_config(config_path)
    service_cfg = config.get("service", {})

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

    host = args.host or service_cfg.get("host", "0.0.0.0")
    port = int(args.port or service_cfg.get("port", 8000))

    app = create_app(run_dir, service_cfg)
    import uvicorn

    uvicorn.run(app, host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
