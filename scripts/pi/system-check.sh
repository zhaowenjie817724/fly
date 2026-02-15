#!/bin/bash
# system-check.sh - 系统状态检查
# 兼容 Ubuntu 24.04 / Raspberry Pi OS
set -u

SERVICES=(
    mavlink-router
    wurenji-acq
    wurenji-api
    wurenji-fsm
    wurenji-watchdog
    fly-acq
    fly-server
    fly-infer
)

cpu_temp() {
    if command -v vcgencmd >/dev/null 2>&1; then
        vcgencmd measure_temp 2>/dev/null || echo "N/A"
        return
    fi
    if [ -r /sys/class/thermal/thermal_zone0/temp ]; then
        awk '{printf "%.1fC\n", $1/1000}' /sys/class/thermal/thermal_zone0/temp
    else
        echo "N/A"
    fi
}

cpu_freq() {
    if command -v vcgencmd >/dev/null 2>&1; then
        vcgencmd measure_clock arm 2>/dev/null | awk -F= '{printf "%.0fMHz\n", $2/1000000}'
        return
    fi
    if [ -r /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq ]; then
        awk '{printf "%.0fMHz\n", $1/1000}' /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
    else
        echo "N/A"
    fi
}

netplan_renderer() {
    if ls /etc/netplan/*.yaml >/dev/null 2>&1; then
        grep -Rhs "renderer:" /etc/netplan/*.yaml 2>/dev/null | awk '{print $2}' | head -1
    fi
}

echo "=========================================="
echo "  WuRenji 系统状态检查"
echo "=========================================="
echo ""

# 系统信息
echo "=== 系统信息 ==="
echo "主机名: $(hostname)"
echo "内核:   $(uname -r)"
echo "架构:   $(uname -m)"
grep -E '^PRETTY_NAME=' /etc/os-release 2>/dev/null | cut -d= -f2-
echo ""

# 硬件信息
echo "=== 硬件信息 ==="
if [ -r /proc/device-tree/model ]; then
    echo "型号: $(tr -d '\0' < /proc/device-tree/model)"
fi
echo "CPU 温度: $(cpu_temp)"
echo "CPU 频率: $(cpu_freq)"
if command -v vcgencmd >/dev/null 2>&1; then
    echo "vcgencmd:  可用"
else
    echo "vcgencmd:  不可用 (退化模式)"
fi
echo ""

# 内存
echo "=== 内存状态 ==="
free -h
echo ""

# zram/swap
echo "=== Swap/Zram ==="
cat /proc/swaps
if command -v zramctl >/dev/null 2>&1; then
    zramctl 2>/dev/null || true
fi
echo ""

# 磁盘
echo "=== 磁盘空间 ==="
df -h / /home 2>/dev/null | head -3
echo ""

# 网络
echo "=== 网络 ==="
echo "IP:      $(hostname -I 2>/dev/null)"
renderer="$(netplan_renderer)"
echo "Netplan: ${renderer:-unknown}"
echo "NM:     $(systemctl is-active NetworkManager 2>/dev/null || echo inactive)"
echo ""

# 服务状态
echo "=== 服务状态 ==="
for svc in "${SERVICES[@]}"; do
    status=$(systemctl is-active "$svc" 2>/dev/null || echo "not-found")
    printf "  %-20s %s\n" "$svc:" "$status"
done
echo ""

# MAVLink 端口
echo "=== MAVLink 端口 ==="
ss -uln 2>/dev/null | grep -E "1455[0-2]" || echo "  无 MAVLink 端口监听"
echo ""

# 摄像头
echo "=== 摄像头设备 ==="
if command -v cam >/dev/null 2>&1; then
    cam --list-cameras 2>/dev/null || true
elif command -v libcamera-hello >/dev/null 2>&1; then
    libcamera-hello --list-cameras 2>/dev/null || true
fi
ls -la /dev/video* 2>/dev/null || echo "  无视频设备"
echo ""

# 串口
echo "=== 串口设备 ==="
ls -la /dev/serial0 /dev/ttyAMA* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo "  无串口设备"
echo ""

# 进程
echo "=== 进程（按内存排序 Top 10） ==="
ps aux --sort=-%mem | head -11
echo ""

echo "=========================================="
echo "  检查完成"
echo "=========================================="
