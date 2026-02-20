#!/bin/bash
# ==========================================================
#  通感之眼2.0 - Ubuntu 24.04 LTS (ARM64) 部署脚本
#  适用: Raspberry Pi 5 (2GB RAM + 32GB SD)
#  系统: Ubuntu 24.04.x LTS (ARM64)
#  用法: chmod +x pi_deploy_ubuntu.sh && ./pi_deploy_ubuntu.sh [用户名] [用户组] [fly目录]
# ==========================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

TARGET_USER="${1:-${SUDO_USER:-$USER}}"
TARGET_GROUP="${2:-$TARGET_USER}"
TARGET_HOME="/home/$TARGET_USER"
FLY_DIR="${3:-$TARGET_HOME/fly}"
SWAP_SIZE_MB="${SWAP_SIZE_MB:-2048}"

echo ""
echo "=========================================="
echo "  通感之眼2.0 - Ubuntu 24.04 部署"
echo "  硬件: Raspberry Pi 5 (ARM64)"
echo "=========================================="
echo "TARGET_USER : $TARGET_USER"
echo "TARGET_GROUP: $TARGET_GROUP"
echo "FLY_DIR     : $FLY_DIR"
echo ""

# ----------------------------------------------------------
# 0. 系统检查
# ----------------------------------------------------------
log_info "检查系统环境..."

# 检查 FLY_DIR
if [ ! -d "$FLY_DIR" ]; then
    log_error "fly 目录不存在: $FLY_DIR"
    log_info "请先 git clone 代码到 $FLY_DIR"
    exit 1
fi

# 检查 OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    log_ok "系统: ${PRETTY_NAME:-unknown}"
    if [ "${ID:-}" != "ubuntu" ]; then
        log_warn "此脚本面向 Ubuntu 24.04.x; 当前 ID=${ID:-unknown}"
    fi
    if [[ "${VERSION_ID:-}" != 24.04* ]]; then
        log_warn "预期 Ubuntu 24.04.x, 实际 VERSION_ID=${VERSION_ID:-unknown}"
    fi
else
    log_warn "无法检测操作系统版本"
fi

# 检查是否为树莓派
if [ -f /proc/device-tree/model ]; then
    MODEL=$(tr -d '\0' < /proc/device-tree/model)
    log_ok "硬件: $MODEL"
fi

# 检查可用内存
MEM_TOTAL=$(awk '/MemTotal/ {printf "%.0f", $2/1024}' /proc/meminfo)
log_info "总内存: ${MEM_TOTAL}MB"
if [ "$MEM_TOTAL" -lt 1800 ]; then
    log_warn "内存不足 2GB，将增加 swap 空间"
fi

# 检查磁盘空间
DISK_FREE=$(df -BG "$REPO_ROOT" | tail -1 | awk '{print $4}' | tr -d 'G')
log_info "可用磁盘: ${DISK_FREE}GB"
if [ "$DISK_FREE" -lt 5 ]; then
    log_error "磁盘空间不足 5GB，建议清理"
    exit 1
fi

# ----------------------------------------------------------
# 1. 系统依赖
# ----------------------------------------------------------
log_info "[1/8] 安装系统依赖..."

sudo apt-get update -qq

# 基础工具
sudo apt-get install -y -qq \
    git \
    python3-venv \
    python3-pip \
    python3-dev \
    ffmpeg \
    v4l-utils \
    wget \
    curl \
    htop \
    jq \
    net-tools \
    2>/dev/null

# 音频相关
sudo apt-get install -y -qq \
    libportaudio2 \
    libportaudiocpp0 \
    portaudio19-dev \
    2>/dev/null || log_warn "部分音频依赖安装失败，音频功能可能不可用"

# OpenCV 系统依赖 (Ubuntu 24.04)
sudo apt-get install -y -qq \
    libopencv-dev \
    python3-opencv \
    libatlas-base-dev \
    libhdf5-dev \
    2>/dev/null || log_warn "部分 OpenCV 依赖安装失败"

# 摄像头相关 (Ubuntu: libcamera-tools 替代 libcamera-apps)
sudo apt-get install -y -qq \
    libcamera-tools \
    python3-libcamera \
    python3-picamera2 \
    2>/dev/null || log_warn "libcamera/picamera2 不完整，将使用 V4L2 接口"

# 树莓派工具 (Ubuntu 需要单独安装)
sudo apt-get install -y -qq \
    libraspberrypi-bin \
    2>/dev/null || log_warn "libraspberrypi-bin 不可用，vcgencmd 将不可用"

# MAVLink 路由
sudo apt-get install -y -qq \
    mavlink-router \
    2>/dev/null || log_warn "mavlink-router 未在系统源中"

log_ok "系统依赖安装完成"

# ----------------------------------------------------------
# 2. 增加 Swap
# ----------------------------------------------------------
log_info "[2/8] 配置 Swap 空间..."

CURRENT_SWAP=$(swapon --show=SIZE --bytes --noheadings 2>/dev/null | awk '{s+=$1} END {printf "%.0f", s/1048576}')
CURRENT_SWAP=${CURRENT_SWAP:-0}

if [ "$CURRENT_SWAP" -lt 1024 ]; then
    log_info "当前 Swap: ${CURRENT_SWAP}MB，扩展到 ${SWAP_SIZE_MB}MB..."

    # Ubuntu 使用 swapfile（非 dphys-swapfile）
    if [ ! -f /swapfile_wurenji ]; then
        sudo fallocate -l ${SWAP_SIZE_MB}M /swapfile_wurenji
        sudo chmod 600 /swapfile_wurenji
        sudo mkswap /swapfile_wurenji >/dev/null
    fi
    sudo swapon /swapfile_wurenji || true

    if ! grep -q '^/swapfile_wurenji ' /etc/fstab; then
        echo '/swapfile_wurenji none swap sw 0 0' | sudo tee -a /etc/fstab > /dev/null
    fi
    log_ok "Swap 文件已创建 (${SWAP_SIZE_MB}MB)"
else
    log_ok "Swap 空间充足: ${CURRENT_SWAP}MB"
fi

# ----------------------------------------------------------
# 3. 配置 zram
# ----------------------------------------------------------
log_info "[3/8] 配置 zram 压缩内存..."

if [ -f "$REPO_ROOT/scripts/pi/setup-zram.sh" ]; then
    bash "$REPO_ROOT/scripts/pi/setup-zram.sh" || log_warn "zram 配置失败"
else
    log_warn "setup-zram.sh 未找到，跳过 zram 配置"
fi

# ----------------------------------------------------------
# 4. Python 虚拟环境
# ----------------------------------------------------------
log_info "[4/8] 创建 Python 虚拟环境..."

cd "$FLY_DIR"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv --system-site-packages
    log_ok "虚拟环境已创建 (含系统包)"
else
    log_ok "虚拟环境已存在"
fi

source .venv/bin/activate

# 升级 pip
pip install --upgrade pip setuptools wheel -q

# ----------------------------------------------------------
# 5. 安装 Python 依赖
# ----------------------------------------------------------
log_info "[5/8] 安装 Python 依赖..."

if [ -f requirements-pi.txt ]; then
    pip install -r requirements-pi.txt -q 2>&1 | tail -5
    log_ok "Python 依赖安装完成 (requirements-pi.txt)"
else
    pip install -r requirements.txt -q 2>&1 | tail -5
    log_ok "Python 依赖安装完成 (requirements.txt)"
fi

# 验证关键依赖
python3 -c "import cv2; print(f'  OpenCV: {cv2.__version__}')" 2>/dev/null || log_warn "OpenCV 未安装"
python3 -c "import pymavlink; print('  pymavlink: OK')" 2>/dev/null || log_error "pymavlink 未安装"
python3 -c "import fastapi; print('  FastAPI: OK')" 2>/dev/null || log_error "FastAPI 未安装"
python3 -c "import numpy; print(f'  numpy: {numpy.__version__}')" 2>/dev/null || log_error "numpy 未安装"

# ----------------------------------------------------------
# 6. 检测摄像头
# ----------------------------------------------------------
log_info "[6/8] 检测摄像头..."

CAM_DETECTED=false

# 方法1: v4l2 (USB摄像头)
if command -v v4l2-ctl &>/dev/null; then
    if v4l2-ctl --list-devices 2>/dev/null | grep -q "video"; then
        log_ok "V4L2 摄像头已检测到:"
        v4l2-ctl --list-devices 2>/dev/null | head -6
        CAM_DETECTED=true
    fi
fi

# 方法2: libcamera (Ubuntu 用 cam 命令)
if command -v cam &>/dev/null; then
    if cam --list-cameras 2>/dev/null | grep -q "camera"; then
        log_ok "CSI 摄像头 (libcamera/cam) 已检测到"
        CAM_DETECTED=true
    fi
elif command -v libcamera-hello &>/dev/null; then
    if libcamera-hello --list-cameras 2>/dev/null | grep -q "Available"; then
        log_ok "CSI 摄像头 (libcamera) 已检测到"
        CAM_DETECTED=true
    fi
fi

if [ "$CAM_DETECTED" = false ]; then
    log_warn "未检测到摄像头，请检查 USB/CSI 连接"
    log_warn "USB: 插入后运行 ls /dev/video*"
    log_warn "CSI: 运行 cam --list-cameras 或 libcamera-hello --list-cameras"
fi

# ----------------------------------------------------------
# 7. 检测飞控连接
# ----------------------------------------------------------
log_info "[7/8] 检测飞控..."

FC_DETECTED=false
FC_PORT=""

for port in /dev/ttyACM0 /dev/ttyACM1 /dev/ttyUSB0 /dev/ttyUSB1 /dev/serial0; do
    if [ -e "$port" ]; then
        log_ok "检测到串口设备: $port"
        FC_DETECTED=true
        FC_PORT="$port"
        break
    fi
done

if [ "$FC_DETECTED" = false ]; then
    log_warn "未检测到飞控设备"
    log_warn "USB飞控: 插入 Pixhawk 后检查 /dev/ttyACM0"
    log_warn "UART飞控: 检查 /dev/serial0"
fi

# ----------------------------------------------------------
# 8. 安装 systemd 服务
# ----------------------------------------------------------
log_info "[8/8] 安装系统服务..."

if [ -f "$REPO_ROOT/scripts/pi/install-fly-services.sh" ]; then
    bash "$REPO_ROOT/scripts/pi/install-fly-services.sh" "$TARGET_USER" "$TARGET_GROUP" "$FLY_DIR" "configs/pi_ubuntu.yaml"
else
    log_warn "install-fly-services.sh 未找到，跳过服务安装"
fi

# 创建便捷启动脚本（手动调试用）
cat > "$FLY_DIR/start.sh" << 'STARTEOF'
#!/bin/bash
# 通感之眼2.0 便捷启动 (手动调试用，生产环境请使用 systemd 服务)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
source .venv/bin/activate

DURATION=${1:-600}
CONFIG="configs/pi_ubuntu.yaml"

echo "=========================================="
echo "  通感之眼2.0 启动中..."
echo "  时长: ${DURATION}s | 配置: $CONFIG"
echo "=========================================="

# 清理旧进程
pkill -f "run_acq.py" 2>/dev/null || true
pkill -f "apps/service/server.py" 2>/dev/null || true
pkill -f "fsm_runner.py" 2>/dev/null || true
pkill -f "yolo_infer.py" 2>/dev/null || true
pkill -f "thermal_infer.py" 2>/dev/null || true
pkill -f "doa_runner.py" 2>/dev/null || true
sleep 1

# 启动数据采集（遥测+观测管线）
echo "[1/6] 数据采集..."
python apps/acquisition/run_acq.py --config "$CONFIG" --duration "$DURATION" &
ACQ_PID=$!
sleep 3

# 启动 YOLO 推理（独占可见光相机）
echo "[2/6] YOLO 视觉推理..."
python apps/vision/yolo_infer.py --config configs/vision.yaml --camera 0 --run latest &
INFER_PID=$!
sleep 1

# 启动热成像推理（独占热像仪）
echo "[3/6] 热成像推理..."
python apps/thermal/thermal_infer.py --config "$CONFIG" --run latest &
THERMAL_PID=$!
sleep 1

# 启动 DOA（麦克风阵列声源定位）
echo "[4/6] DOA 声源定位..."
python apps/audio/doa_runner.py --config "$CONFIG" --run latest &
DOA_PID=$!
sleep 1

# 启动后端服务
echo "[5/6] 后端服务..."
python apps/service/server.py --config configs/service.yaml --run latest &
SERVICE_PID=$!
sleep 1

# 启动 FSM（dry-run，待飞控接入后去掉 --dry-run）
echo "[6/6] FSM 状态机..."
python apps/control/fsm_runner.py --config configs/fsm.yaml --run latest --dry-run &
FSM_PID=$!

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
echo "=========================================="
echo "  所有服务已启动"
echo "  仪表板: http://${IP:-localhost}:8000"
echo "  健康:   http://${IP:-localhost}:8000/health"
echo "  按 Ctrl+C 停止"
echo "=========================================="

cleanup() {
    echo ""
    echo "停止服务..."
    kill $ACQ_PID $INFER_PID $THERMAL_PID $DOA_PID $SERVICE_PID $FSM_PID 2>/dev/null || true
    wait 2>/dev/null
    echo "已停止"
}
trap cleanup EXIT INT TERM

wait $ACQ_PID 2>/dev/null
STARTEOF

chmod +x "$FLY_DIR/start.sh"
log_ok "便捷启动脚本: $FLY_DIR/start.sh (调试用)"

# ----------------------------------------------------------
# 部署完成
# ----------------------------------------------------------
echo ""
echo "=========================================="
echo -e "  ${GREEN}Ubuntu 24.04 部署完成!${NC}"
echo "=========================================="
echo ""
echo "  启动服务 (推荐):"
echo "    sudo systemctl start mavlink-router wurenji-acq wurenji-api wurenji-infer wurenji-thermal wurenji-doa wurenji-fsm wurenji-watchdog"
echo ""
echo "  查看状态:"
echo "    sudo systemctl status wurenji-acq wurenji-infer wurenji-thermal wurenji-doa"
echo ""
echo "  查看日志:"
echo "    journalctl -u wurenji-acq -f"
echo "    journalctl -u wurenji-infer -f"
echo ""
echo "  手动调试:"
echo "    cd $FLY_DIR"
echo "    ./start.sh           # 默认10分钟"
echo "    ./start.sh 3600      # 1小时"
echo ""
if [ -n "$FC_PORT" ]; then
    echo "  飞控连接 ($FC_PORT):"
    echo "    编辑 configs/pi_ubuntu.yaml → telemetry.mavlink.serial_port = \"$FC_PORT\""
    echo ""
fi
echo "  系统优化:"
echo "    bash scripts/pi/disable-services.sh"
echo "    bash scripts/pi/setup-zram.sh"
echo "=========================================="
