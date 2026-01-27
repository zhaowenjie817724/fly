# 树莓派 Ubuntu 24.04 部署指南（2GB/32GB）

## 1. 系统准备

1) 刷入 Ubuntu 24.04（64-bit）  
2) 首次启动完成网络与 SSH 配置  
3) 更新系统：

```
sudo apt update && sudo apt -y upgrade
```

## 2. 基础依赖

```
sudo apt install -y git python3-venv python3-pip ffmpeg libportaudio2
```

如果摄像头用 V4L2，可选安装：

```
sudo apt install -y v4l-utils
```

## 3. 获取代码

```
git clone https://github.com/zhaowenjie817724/fly.git
cd fly
```

## 4. Python 环境

```
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-pi.txt
```

说明：
- `requirements-pi.txt` 是轻量依赖，不含 YOLO/torch，先保证采集+后端。
- 若需 YOLO，可在树莓派上单独安装支持的 torch/ultralytics（可选）。

## 5. 运行配置（建议）

采集：`configs/pi_2gb.yaml`  
视觉：`configs/vision_pi.yaml`

示例：

```
python apps/acquisition/run_acq.py --config configs/pi_2gb.yaml
python apps/service/server.py --config configs/service.yaml --run latest
```

## 6. 与地面站联通

- GCS（地面站）使用 `udp:127.0.0.1:14550`  
- 本机程序使用 `udp:127.0.0.1:14551`  

配置位置：`configs/pi_2gb.yaml` -> `telemetry.mavlink.udp`

## 7. 低功耗建议

- 视频 640x360@10fps
- `vision_pi.yaml` 使用 `imgsz=416` + `frame_skip=2`
- 关闭音频（如无麦阵）

## 8. 目录与清理

```
scripts/cleanup_runs.ps1   # Windows
python tools/cleanup_runs.py --keep-last 5
```

树莓派上建议定期清理 runs 目录。
