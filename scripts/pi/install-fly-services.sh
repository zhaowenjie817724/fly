#!/bin/bash
# install-fly-services.sh - 安装 fly 系统服务
# 用法: sudo ./install-fly-services.sh [用户名]

set -e

USER=${1:-pi}
HOME_DIR="/home/$USER"
FLY_DIR="$HOME_DIR/fly"

echo "=== 安装 Fly 系统服务 ==="
echo "用户: $USER"
echo "目录: $FLY_DIR"
echo ""

# 检查目录
if [ ! -d "$FLY_DIR" ]; then
    echo "错误: $FLY_DIR 不存在"
    exit 1
fi

# 检查虚拟环境
if [ ! -f "$FLY_DIR/.venv/bin/python" ]; then
    echo "错误: Python 虚拟环境不存在"
    echo "请先运行: python3 -m venv $FLY_DIR/.venv"
    exit 1
fi

# 创建 mavlink-router 配置目录
echo "配置 mavlink-router..."
sudo mkdir -p /etc/mavlink-router
sudo cp "$FLY_DIR/configs/mavlink-router.conf" /etc/mavlink-router/main.conf

# 修改服务文件中的用户和路径
echo "安装服务文件..."

for svc in mavlink-router fly-acq fly-server fly-infer; do
    SVC_FILE="$FLY_DIR/scripts/pi/${svc}.service"
    if [ -f "$SVC_FILE" ]; then
        # 替换用户名和路径
        sudo sed -e "s|User=pi|User=$USER|g" \
                 -e "s|Group=pi|Group=$USER|g" \
                 -e "s|/home/pi/fly|$FLY_DIR|g" \
                 "$SVC_FILE" > /tmp/${svc}.service
        sudo mv /tmp/${svc}.service /etc/systemd/system/
        echo "  已安装: ${svc}.service"
    fi
done

# 重新加载 systemd
sudo systemctl daemon-reload

echo ""
echo "=== 服务已安装 ==="
echo ""
echo "启用服务:"
echo "  sudo systemctl enable mavlink-router fly-acq fly-server"
echo ""
echo "启动服务:"
echo "  sudo systemctl start mavlink-router fly-acq fly-server"
echo ""
echo "查看状态:"
echo "  sudo systemctl status fly-acq"
echo ""
echo "查看日志:"
echo "  journalctl -u fly-acq -f"
