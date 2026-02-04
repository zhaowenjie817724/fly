#!/bin/bash
# setup-zram.sh - 配置 zram 压缩内存
# 适用于 Raspberry Pi OS Bookworm

set -e

echo "=== 配置 zram 压缩内存 ==="

# 安装 zram-tools
if ! dpkg -s zram-tools &> /dev/null; then
    echo "安装 zram-tools..."
    sudo apt update
    sudo apt install -y zram-tools
fi

# 配置 zram
echo "配置 /etc/default/zramswap..."
sudo tee /etc/default/zramswap > /dev/null << 'EOF'
# zram 配置 - 适用于 2GB 内存
ALGO=lz4
PERCENT=50
PRIORITY=100
EOF

# 启用服务
echo "启用 zramswap 服务..."
sudo systemctl enable zramswap
sudo systemctl restart zramswap

# 验证
echo ""
echo "=== zram 状态 ==="
zramctl
echo ""
cat /proc/swaps

echo ""
echo "zram 配置完成！"
