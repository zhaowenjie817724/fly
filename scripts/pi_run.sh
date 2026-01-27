#!/bin/bash
# 树莓派一键启动脚本
# 用法: ./pi_run.sh [采集时长秒数]

set -e

DURATION=${1:-600}  # 默认10分钟
CONFIG_ACQ="configs/pi_2gb.yaml"
CONFIG_VISION="configs/vision_pi.yaml"
CONFIG_FSM="configs/fsm.yaml"
CONFIG_SERVICE="configs/service.yaml"

echo "=========================================="
echo "  通感之眼2.0 - 启动中..."
echo "  采集时长: ${DURATION}s"
echo "=========================================="

# 激活虚拟环境
source .venv/bin/activate

# 启动采集 (后台)
echo "[1/4] 启动数据采集..."
python apps/acquisition/run_acq.py --config $CONFIG_ACQ --duration $DURATION &
ACQ_PID=$!
sleep 3

# 获取最新run目录
RUN_DIR=$(ls -td runs/*/ | head -1)
echo "  Run目录: $RUN_DIR"

# 启动视觉推理 (后台)
echo "[2/4] 启动视觉推理..."
python apps/vision/yolo_infer.py --config $CONFIG_VISION --camera 0 &
VISION_PID=$!
sleep 2

# 启动后端服务 (后台)
echo "[3/4] 启动后端服务..."
python apps/service/server.py --config $CONFIG_SERVICE --run latest &
SERVICE_PID=$!
sleep 1

echo ""
echo "=========================================="
echo "  所有服务已启动"
echo "=========================================="
echo "  采集 PID:   $ACQ_PID"
echo "  视觉 PID:   $VISION_PID"
echo "  服务 PID:   $SERVICE_PID"
echo ""
echo "  Web仪表板: http://$(hostname -I | awk '{print $1}'):8000"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo "=========================================="

# 捕获退出信号
cleanup() {
    echo ""
    echo "正在停止服务..."
    kill $ACQ_PID $VISION_PID $SERVICE_PID 2>/dev/null || true
    wait
    echo "已停止"
}
trap cleanup EXIT INT TERM

# 等待采集完成
wait $ACQ_PID
