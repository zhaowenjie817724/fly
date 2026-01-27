#!/bin/bash
# 树莓派一键部署脚本 (Ubuntu 24.04)
# 用法: chmod +x pi_deploy.sh && ./pi_deploy.sh

set -e

echo "=========================================="
echo "  通感之眼2.0 - 树莓派部署脚本"
echo "=========================================="

# 1. 系统依赖
echo "[1/5] 安装系统依赖..."
sudo apt update
sudo apt install -y git python3-venv python3-pip ffmpeg libportaudio2 v4l-utils

# 2. Python虚拟环境
echo "[2/5] 创建Python虚拟环境..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# 3. 安装Python依赖
echo "[3/5] 安装Python依赖..."
pip install --upgrade pip
pip install -r requirements-pi.txt

# 4. 验证摄像头
echo "[4/5] 检测摄像头..."
if v4l2-ctl --list-devices 2>/dev/null | grep -q "video"; then
    echo "  [OK] 摄像头已检测到"
    v4l2-ctl --list-devices
else
    echo "  [WARN] 未检测到摄像头，请检查连接"
fi

# 5. 创建systemd服务 (可选)
echo "[5/5] 部署完成!"
echo ""
echo "=========================================="
echo "  启动命令:"
echo "=========================================="
echo "  # 采集模式"
echo "  source .venv/bin/activate"
echo "  python apps/acquisition/run_acq.py --config configs/pi_2gb.yaml"
echo ""
echo "  # 后端服务"
echo "  python apps/service/server.py --config configs/service.yaml --run latest"
echo ""
echo "  # 视觉推理"
echo "  python apps/vision/yolo_infer.py --config configs/vision_pi.yaml --run latest"
echo ""
echo "  # 声源定位"
echo "  python apps/audio/doa_offline.py --config configs/doa.yaml --run latest"
echo ""
echo "  # FSM状态机"
echo "  python apps/control/fsm_runner.py --config configs/fsm.yaml --run latest"
echo "=========================================="
