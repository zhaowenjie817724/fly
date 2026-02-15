# 树莓派 Ubuntu 24.04 部署指南（2GB/32GB）

> 适用于 Ubuntu 24.04.x LTS (ARM64) / Raspberry Pi 5

## 1. 系统准备

1) 使用 Raspberry Pi Imager 刷入 **Ubuntu Server 24.04 LTS (64-bit)**
2) 首次启动完成网络与 SSH 配置
3) 更新系统：

```bash
sudo apt update && sudo apt -y upgrade
```

## 2. 一键部署（推荐）

```bash
git clone https://github.com/zhaowenjie817724/fly.git
cd fly
chmod +x scripts/pi_deploy_ubuntu.sh
./scripts/pi_deploy_ubuntu.sh
```

脚本将自动完成：
- 系统依赖安装（ffmpeg, v4l-utils, libcamera-tools, libraspberrypi-bin 等）
- Swap 空间配置（2GB swapfile）
- zram 压缩内存（50% RAM）
- Python 虚拟环境 + 依赖安装
- 摄像头/飞控检测
- systemd 服务安装

### 自定义用户/路径

```bash
# 指定用户和 fly 目录
./scripts/pi_deploy_ubuntu.sh myuser myuser /home/myuser/fly
```

## 3. 手动部署

### 3.1 基础依赖

```bash
sudo apt install -y git python3-venv python3-pip python3-dev ffmpeg \
    v4l-utils libportaudio2 libopencv-dev python3-opencv libatlas-base-dev

# 摄像头支持
sudo apt install -y libcamera-tools python3-libcamera python3-picamera2

# 树莓派工具（vcgencmd 等）
sudo apt install -y libraspberrypi-bin

# MAVLink 路由（如果可用）
sudo apt install -y mavlink-router
```

### 3.2 Python 环境

```bash
cd ~/fly
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-pi.txt
```

说明：
- `requirements-pi.txt` 是轻量依赖，不含 YOLO/torch，先保证采集+后端
- 若需 YOLO，可单独安装 `ultralytics`（可选）

### 3.3 安装 systemd 服务

```bash
sudo ./scripts/pi/install-fly-services.sh ubuntu ubuntu /home/ubuntu/fly configs/pi_ubuntu.yaml
```

此命令会：
- 创建 `/etc/wurenji/wurenji.env`（环境变量）
- 安装 `wurenji-acq/api/fsm/watchdog` 服务
- 禁用旧版 `fly-*` 服务

## 4. 运行配置

采集：`configs/pi_ubuntu.yaml`
视觉：`configs/vision_pi.yaml`
服务：`configs/service.yaml`

### 手动运行

```bash
source .venv/bin/activate
python apps/acquisition/run_acq.py --config configs/pi_ubuntu.yaml
python apps/service/server.py --config configs/service.yaml --run latest
python apps/control/fsm_runner.py --config configs/fsm.yaml --run latest --dry-run
```

### systemd 服务运行

```bash
# 启动所有服务
sudo systemctl start mavlink-router wurenji-acq wurenji-api wurenji-fsm wurenji-watchdog

# 查看状态
sudo systemctl status wurenji-acq

# 查看日志
journalctl -u wurenji-acq -f
```

## 5. 与地面站联通

- GCS（地面站）使用 `udp:127.0.0.1:14550`
- 本机程序使用 `udp:127.0.0.1:14551`

配置位置：`configs/pi_ubuntu.yaml` → `telemetry.mavlink.udp`

## 6. 系统优化

### 6.1 禁用不必要服务

```bash
bash scripts/pi/disable-services.sh
```

默认禁用：bluetooth, cups, avahi-daemon, ModemManager, snapd, whoopsie, apport

### 6.2 zram 压缩内存

```bash
bash scripts/pi/setup-zram.sh
```

自动检测并使用 `systemd-zram-generator` 或 `zram-tools`。

### 6.3 切换到无桌面模式（推荐生产环境）

```bash
bash scripts/pi/fly-mode-switch.sh headless
sudo reboot
```

### 6.4 低功耗建议

- 视频 640x360@10fps
- `vision_pi.yaml` 使用 `imgsz=416` + `frame_skip=2`
- 关闭音频（如无麦阵）
- 使用 Ubuntu Server（无桌面）

## 7. systemd 环境变量

服务通过 `/etc/wurenji/wurenji.env` 读取配置，模板位于 `scripts/systemd/wurenji.env`：

```ini
APP_USER=ubuntu
APP_GROUP=ubuntu
FLY_DIR=/home/ubuntu/fly
RUNS_DIR=/home/ubuntu/fly/runs
LOGS_DIR=/home/ubuntu/fly/logs
FLY_ACQ_CONFIG=configs/pi_ubuntu.yaml
FLY_API_CONFIG=configs/service.yaml
FLY_FSM_CONFIG=configs/fsm.yaml
```

修改后需重启服务：`sudo systemctl restart wurenji-acq wurenji-api wurenji-fsm`

## 8. 系统检查与故障排除

```bash
# 完整系统状态检查
bash scripts/pi/system-check.sh

# 查看看门狗日志
journalctl -u wurenji-watchdog -f
```

## 9. 目录与清理

```bash
# 手动清理旧 run 数据（保留最近 5 个）
python tools/cleanup_runs.py --keep-last 5
```

看门狗会自动监控磁盘空间，低于 500MB 时自动清理。

## 10. 与 Raspberry Pi OS 的差异

| 项目 | Ubuntu 24.04 | Raspberry Pi OS |
|------|-------------|-----------------|
| 默认用户 | `ubuntu` | `pi` |
| Swap 管理 | swapfile | dphys-swapfile |
| 桌面管理器 | gdm3 / 无 | lightdm |
| 摄像头命令 | `cam` / `libcamera-hello` | `libcamera-hello` |
| vcgencmd | 需装 `libraspberrypi-bin` | 默认可用 |
| 网络管理 | Netplan + NetworkManager | dhcpcd |
| 包名差异 | `libcamera-tools` | `libcamera-apps` |
| 配置文件 | `pi_ubuntu.yaml` | `pi_bookworm.yaml` |
