#!/bin/bash
# setup-zram.sh - 配置 zram 压缩内存
# 兼容 Ubuntu 24.04 / Raspberry Pi OS
set -euo pipefail

ALGO="${ZRAM_ALGO:-lz4}"
PERCENT="${ZRAM_PERCENT:-50}"
PRIORITY="${ZRAM_PRIORITY:-100}"

echo "=== 配置 zram 压缩内存 (Ubuntu/RPi OS 兼容) ==="

configure_systemd_generator() {
    echo "使用 systemd-zram-generator 后端..."
    sudo install -d -m 0755 /etc/systemd
    sudo tee /etc/systemd/zram-generator.conf > /dev/null <<EOF
[zram0]
zram-size = ram / 2
compression-algorithm = ${ALGO}
swap-priority = ${PRIORITY}
EOF
    sudo systemctl daemon-reload
    sudo systemctl restart systemd-zram-setup@zram0.service 2>/dev/null || true
}

configure_zram_tools() {
    echo "使用 zram-tools 后端..."
    sudo tee /etc/default/zramswap > /dev/null <<EOF
# zram 配置 - 适用于低内存 Pi 设备
ALGO=${ALGO}
PERCENT=${PERCENT}
PRIORITY=${PRIORITY}
EOF
    sudo systemctl enable --now zramswap
}

# 自动检测并选择后端
if dpkg -s systemd-zram-generator >/dev/null 2>&1; then
    configure_systemd_generator
elif dpkg -s zram-tools >/dev/null 2>&1; then
    configure_zram_tools
else
    echo "安装 zram 后端..."
    sudo apt-get update -y -qq
    if sudo apt-get install -y -qq systemd-zram-generator 2>/dev/null; then
        configure_systemd_generator
    else
        sudo apt-get install -y -qq zram-tools
        configure_zram_tools
    fi
fi

# 验证
echo ""
echo "=== zram 状态 ==="
if command -v zramctl >/dev/null 2>&1; then
    zramctl || true
fi
echo ""
cat /proc/swaps

echo ""
echo "zram 配置完成！"
