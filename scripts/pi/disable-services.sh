#!/bin/bash
# disable-services.sh - 禁用不必要的系统服务
# 适用于 Raspberry Pi OS Full

set -e

echo "=== 禁用不必要的系统服务 ==="

# 要禁用的服务列表
SERVICES=(
    "bluetooth"           # 蓝牙（通常不需要）
    "cups"                # 打印服务
    "cups-browsed"        # 打印机发现
    "avahi-daemon"        # 局域网服务发现
    "ModemManager"        # 调制解调器管理
    "wpa_supplicant"      # 如果用有线网络，可禁用 WiFi
    # "apt-daily.timer"   # 自动更新（可选）
    # "apt-daily-upgrade.timer"
)

for svc in "${SERVICES[@]}"; do
    if systemctl is-enabled "$svc" &> /dev/null; then
        echo "禁用 $svc..."
        sudo systemctl disable --now "$svc" 2>/dev/null || true
    else
        echo "$svc 已禁用或不存在"
    fi
done

echo ""
echo "=== 当前运行的服务 ==="
systemctl list-units --type=service --state=running | head -20

echo ""
echo "服务优化完成！"
echo "注意：如果禁用了 wpa_supplicant，WiFi 将不可用"
