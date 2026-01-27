#!/bin/bash
# Mission Planner / SITL 联调脚本 (Linux/WSL)

echo "============================================================"
echo "Mission Planner / SITL 联调脚本"
echo "============================================================"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# 激活虚拟环境
source .venv/bin/activate

echo ""
echo "[1/4] 检查MAVLink连接..."
python tools/test_mavlink_connection.py --udp udp:127.0.0.1:14551 --api http://127.0.0.1:8000

if [ $? -ne 0 ]; then
    echo ""
    echo "============================================================"
    echo "连接测试失败！请确保："
    echo "1. SITL 已启动: sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14551"
    echo "2. 端口 14551 可用"
    echo "============================================================"
    exit 1
fi

echo ""
echo "[2/4] 启动遥测接收器 (后台)..."
python apps/acquisition/mavlink_receiver.py --udp udp:127.0.0.1:14551 --run latest &
RECEIVER_PID=$!
echo "遥测接收器 PID: $RECEIVER_PID"

echo ""
echo "[3/4] 启动后端服务 (后台)..."
python apps/service/server.py --config configs/service.yaml --run latest &
SERVER_PID=$!
echo "后端服务 PID: $SERVER_PID"

echo ""
echo "[4/4] 等待服务启动..."
sleep 5

echo ""
echo "============================================================"
echo "联调环境已启动！"
echo ""
echo "服务地址："
echo "  - REST API:   http://127.0.0.1:8000"
echo "  - WebSocket:  ws://127.0.0.1:8000/ws"
echo "  - 健康检查:   http://127.0.0.1:8000/health"
echo ""
echo "测试命令："
echo '  curl -X POST http://127.0.0.1:8000/api/control/yaw -H "Content-Type: application/json" -d '"'"'{"yaw_deg": 30}'"'"
echo ""
echo "停止服务："
echo "  kill $RECEIVER_PID $SERVER_PID"
echo "============================================================"

# 等待用户中断
trap "kill $RECEIVER_PID $SERVER_PID 2>/dev/null; exit 0" INT TERM
wait
