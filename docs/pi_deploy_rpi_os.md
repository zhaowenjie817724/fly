# 树莓派 Raspberry Pi OS (Bookworm) 部署指南

> 适用于 Raspberry Pi OS (Legacy) Full - Debian 12 Bookworm / 64-bit / 带桌面
> 硬件：Raspberry Pi 4/5，2GB+ 内存，32GB+ SD卡

---

## 1. 系统准备

### 1.1 刷入系统

使用 Raspberry Pi Imager 刷入 **Raspberry Pi OS (64-bit) Full**。

刷入前建议在 Imager 中预配置：
- 主机名、用户名/密码
- WiFi（如需）
- SSH 启用
- 时区/键盘布局

### 1.2 首次启动

```bash
# 更新系统
sudo apt update && sudo apt -y upgrade

# 安装基础依赖
sudo apt install -y git python3-venv python3-pip ffmpeg libportaudio2 v4l-utils
```

### 1.3 用户权限

```bash
# 串口权限（MAVLink）
sudo usermod -aG dialout $USER

# 摄像头权限（video 组）
sudo usermod -aG video $USER

# 重新登录生效
```

---

## 2. 桌面环境优化（关键）

Full 版自带桌面环境，**上机飞行时必须切换到无桌面模式**以节省内存和 CPU。

### 2.1 开发阶段：保留桌面但关闭后台服务

```bash
# 禁用不必要的服务
sudo systemctl disable --now bluetooth
sudo systemctl disable --now cups
sudo systemctl disable --now avahi-daemon
sudo systemctl disable --now ModemManager

# 可选：禁用自动更新检查
sudo systemctl disable --now apt-daily.timer
sudo systemctl disable --now apt-daily-upgrade.timer
```

### 2.2 上机阶段：切换到无桌面模式（headless）

```bash
# 切换到命令行模式（重启后生效）
sudo systemctl set-default multi-user.target
sudo reboot

# 需要桌面时切回
sudo systemctl set-default graphical.target
sudo reboot

# 临时启动桌面（不改变默认）
sudo systemctl start lightdm
```

### 2.3 一键切换脚本

```bash
# 安装后可用 fly-headless / fly-desktop 命令
sudo cp scripts/pi/fly-mode-switch.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/fly-mode-switch.sh
sudo ln -sf /usr/local/bin/fly-mode-switch.sh /usr/local/bin/fly-headless
sudo ln -sf /usr/local/bin/fly-mode-switch.sh /usr/local/bin/fly-desktop
```

---

## 3. 内存优化（2GB 专项）

### 3.1 启用 zram（压缩内存）

zram 比 SD 卡 swap 更快，且不伤卡。

```bash
# 安装 zram-tools
sudo apt install -y zram-tools

# 配置 /etc/default/zramswap
sudo tee /etc/default/zramswap > /dev/null << 'EOF'
ALGO=lz4
PERCENT=50
PRIORITY=100
EOF

# 启用
sudo systemctl enable --now zramswap
```

### 3.2 降低 GPU 内存分配

编辑 `/boot/firmware/config.txt`（Bookworm 路径）：

```bash
sudo nano /boot/firmware/config.txt
```

添加或修改：

```ini
# GPU 内存分配（无桌面时可设更低）
gpu_mem=64

# 如果只用命令行，可设为
# gpu_mem=16
```

### 3.3 编译时临时 swap（可选）

pip 编译某些包（如 numpy）时内存不足，可临时开启文件 swap：

```bash
# 创建 1GB swap 文件
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 编译完成后关闭
sudo swapoff /swapfile
sudo rm /swapfile
```

---

## 4. 获取代码与环境

```bash
# 克隆仓库
git clone https://github.com/zhaowenjie817724/fly.git
cd fly

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装依赖（树莓派轻量版）
pip install -r requirements-pi.txt
```

---

## 5. 摄像头配置

### 5.1 USB 摄像头（推荐）

USB 摄像头使用 V4L2 驱动，兼容性好：

```bash
# 检查设备
v4l2-ctl --list-devices

# 检查支持的分辨率和帧率
v4l2-ctl -d /dev/video0 --list-formats-ext

# 测试采集
ffmpeg -f v4l2 -video_size 640x360 -framerate 10 -i /dev/video0 -t 5 test.mp4
```

配置文件 `configs/pi_bookworm.yaml`：

```yaml
camera:
  enabled: true
  mode: device
  device_index: 0
  width: 640
  height: 360
  fps: 10
```

### 5.2 CSI 摄像头（官方摄像头模块）

Raspberry Pi OS Bookworm 使用 libcamera 栈：

```bash
# 检查摄像头
libcamera-hello --list-cameras

# 测试拍照
libcamera-still -o test.jpg

# 测试视频
libcamera-vid -t 5000 -o test.h264
```

**注意**：CSI 摄像头与 OpenCV `VideoCapture(0)` 不直接兼容。如需在 Python 中使用，选择以下方案之一：

1. **使用 picamera2 库**（推荐）：
   ```bash
   pip install picamera2
   ```

2. **使用 v4l2 兼容层**：
   ```bash
   # 加载 v4l2 兼容模块
   sudo modprobe bcm2835-v4l2
   ```

3. **使用 USB 摄像头替代**（最简单）

### 5.3 固化摄像头参数

防止自动曝光/白平衡导致检测阈值波动：

```bash
# 查看可调参数
v4l2-ctl -d /dev/video0 -l

# 固定曝光（示例）
v4l2-ctl -d /dev/video0 -c exposure_auto=1 -c exposure_absolute=300

# 固定白平衡
v4l2-ctl -d /dev/video0 -c white_balance_temperature_auto=0 -c white_balance_temperature=4500
```

---

## 6. MAVLink 配置

### 6.1 mavlink-router 安装

```bash
# 安装依赖
sudo apt install -y meson ninja-build pkg-config

# 编译安装
git clone https://github.com/mavlink-router/mavlink-router.git
cd mavlink-router
meson setup build .
ninja -C build
sudo ninja -C build install
cd ..
```

### 6.2 配置文件

复制配置：

```bash
sudo mkdir -p /etc/mavlink-router
sudo cp configs/mavlink-router.conf /etc/mavlink-router/main.conf
```

配置说明（`/etc/mavlink-router/main.conf`）：

```ini
[General]
ReportStats=false

# 串口输入（连接飞控）
[UartEndpoint flight_controller]
Device=/dev/ttyAMA0
Baud=115200

# UDP 输出：地面站
[UdpEndpoint gcs]
Mode=Normal
Address=127.0.0.1
Port=14550

# UDP 输出：本机程序
[UdpEndpoint companion]
Mode=Normal
Address=127.0.0.1
Port=14551
```

### 6.3 systemd 服务

```bash
sudo cp scripts/pi/mavlink-router.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mavlink-router
```

### 6.4 端口规划

| 端口 | 用途 |
|------|------|
| 14550 | LandState GCS 地面站 |
| 14551 | fly 本机程序 |
| 14552 | 预留（调试/备用） |

---

## 7. 运行服务

### 7.1 手动运行

```bash
# 激活环境
cd ~/fly
source .venv/bin/activate

# 采集服务
python apps/acquisition/run_acq.py --config configs/pi_bookworm.yaml

# API 服务（另一终端）
python apps/service/server.py --config configs/service.yaml --run latest
```

### 7.2 systemd 服务（生产环境）

```bash
# 安装服务
sudo cp scripts/pi/fly-acq.service /etc/systemd/system/
sudo cp scripts/pi/fly-server.service /etc/systemd/system/
sudo systemctl daemon-reload

# 启用
sudo systemctl enable fly-acq fly-server

# 启动
sudo systemctl start fly-acq fly-server

# 查看日志
journalctl -u fly-acq -f
journalctl -u fly-server -f
```

---

## 8. 与 LandState GCS 联调

### 8.1 网络配置

确保地面站 PC 与树莓派在同一网络：

```bash
# 树莓派查看 IP
hostname -I

# PC 测试连通性
ping <树莓派IP>
```

### 8.2 LandState GCS 连接

在 LandState GCS 中：
- **连接类型**：UDP Listen
- **端口**：14550
- 或使用 WebSocket 连接 fly 服务：`ws://<树莓派IP>:8000/ws`

### 8.3 fly 配置

确保 `configs/pi_bookworm.yaml` 中：

```yaml
telemetry:
  enabled: true
  mode: mavlink_udp
  mavlink:
    udp: "udp:127.0.0.1:14551"
```

---

## 9. 存储与清理

### 9.1 数据目录

```
~/fly/
├── runs/          # 采集数据（定期清理）
├── logs/          # 日志文件
└── events/        # 事件截图
```

### 9.2 自动清理

```bash
# 保留最近 5 次运行
python tools/cleanup_runs.py --keep-last 5

# cron 定时清理（每天凌晨 3 点）
echo "0 3 * * * cd ~/fly && .venv/bin/python tools/cleanup_runs.py --keep-last 5" | crontab -
```

### 9.3 日志轮转

```bash
# 配置 logrotate
sudo tee /etc/logrotate.d/fly << 'EOF'
/home/*/fly/logs/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
EOF
```

---

## 10. 故障排除

### 10.1 摄像头无法打开

```bash
# 检查设备
ls -la /dev/video*

# 检查权限
groups $USER  # 应包含 video

# 检查进程占用
fuser /dev/video0
```

### 10.2 MAVLink 无心跳

```bash
# 检查 mavlink-router 状态
sudo systemctl status mavlink-router

# 检查串口
ls -la /dev/ttyAMA0
sudo cat /dev/ttyAMA0  # 应有数据流

# 检查端口监听
ss -uln | grep 1455
```

### 10.3 内存不足

```bash
# 查看内存使用
free -h

# 查看进程内存
ps aux --sort=-%mem | head -10

# 检查 zram 状态
cat /proc/swaps
zramctl
```

### 10.4 SD 卡写入慢

```bash
# 测试写入速度
dd if=/dev/zero of=testfile bs=1M count=100 oflag=direct

# 如果低于 10MB/s，考虑更换 A1/A2 级别的卡
```

---

## 11. 性能基准

### 推荐配置（2GB 内存）

| 参数 | 值 | 说明 |
|------|-----|------|
| 视频分辨率 | 640x360 | 降低内存和 CPU |
| 视频帧率 | 8-12 FPS | 推理足够 |
| 快照间隔 | 5 秒 | 减少写入 |
| 推理跳帧 | 2 | 每 2 帧推理 1 次 |
| 音频 | 禁用 | 除非有麦阵 |

### 预期性能

- CPU 占用：30-50%（无桌面）
- 内存占用：800MB-1.2GB
- 推理延迟：100-300ms（视模型）
- 存储速率：~1MB/min（仅快照）

---

## 附录：快速命令参考

```bash
# 切换到无桌面模式
fly-headless

# 切换回桌面模式
fly-desktop

# 查看系统资源
htop

# 查看温度
vcgencmd measure_temp

# 查看 CPU 频率
vcgencmd get_config arm_freq

# 重启 fly 服务
sudo systemctl restart fly-acq fly-server

# 查看 fly 日志
journalctl -u fly-acq -n 50
```
