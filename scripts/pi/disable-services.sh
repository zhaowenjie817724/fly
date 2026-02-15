#!/bin/bash
# disable-services.sh - 禁用不必要的系统服务
# 兼容 Ubuntu 24.04 / Raspberry Pi OS
set -euo pipefail

DISABLE_SNAPD="${DISABLE_SNAPD:-1}"
DISABLE_WIFI="${DISABLE_WIFI:-0}"

# 通用服务列表
SERVICES=(
    bluetooth
    cups
    cups-browsed
    avahi-daemon
    ModemManager
    whoopsie
    apport
)

# 可选定时器
TIMERS=(
    motd-news.timer
    ua-timer.timer
)

# snapd（Ubuntu 默认安装，树莓派场景通常不需要）
if [ "$DISABLE_SNAPD" = "1" ]; then
    SERVICES+=(snapd snapd.socket snapd.seeded.service)
fi

# WiFi（仅在确认用有线网络时禁用）
if [ "$DISABLE_WIFI" = "1" ]; then
    SERVICES+=(wpa_supplicant)
fi

unit_exists() {
    local unit="$1"
    systemctl list-unit-files --all --no-legend 2>/dev/null | awk '{print $1}' | grep -Fxq "$unit"
}

disable_unit() {
    local unit="$1"
    if unit_exists "$unit"; then
        echo "禁用 $unit ..."
        sudo systemctl disable --now "$unit" 2>/dev/null || true
    else
        echo "跳过 $unit (未安装)"
    fi
}

echo "=== 禁用不必要的系统服务 ==="

for svc in "${SERVICES[@]}"; do
    disable_unit "$svc"
done

for t in "${TIMERS[@]}"; do
    disable_unit "$t"
done

echo ""
echo "=== 当前运行的服务 ==="
systemctl list-units --type=service --state=running | head -20

echo ""
echo "服务优化完成！"
echo ""
echo "注意:"
echo "  - NetworkManager/systemd-networkd 未被禁用"
echo "  - 设置 DISABLE_WIFI=1 仅当确认使用有线网络"
echo "  - 设置 DISABLE_SNAPD=0 如果依赖 snap 包"
