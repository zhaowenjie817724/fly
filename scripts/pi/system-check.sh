#!/bin/bash
# system-check.sh - 系统状态检查
# 用于故障排除

echo "=========================================="
echo "  Fly 系统状态检查"
echo "=========================================="
echo ""

# 系统信息
echo "=== 系统信息 ==="
echo "主机名: $(hostname)"
echo "内核:   $(uname -r)"
echo "架构:   $(uname -m)"
cat /etc/os-release | grep PRETTY_NAME
echo ""

# 硬件信息
echo "=== 硬件信息 ==="
if [ -f /proc/device-tree/model ]; then
    echo "型号: $(cat /proc/device-tree/model)"
fi
echo "CPU 温度: $(vcgencmd measure_temp 2>/dev/null || echo 'N/A')"
echo "CPU 频率: $(vcgencmd get_config arm_freq 2>/dev/null || echo 'N/A')"
echo ""

# 内存
echo "=== 内存状态 ==="
free -h
echo ""

# zram
echo "=== Swap/Zram ==="
cat /proc/swaps
echo ""

# 磁盘
echo "=== 磁盘空间 ==="
df -h / /home 2>/dev/null | head -3
echo ""

# 网络
echo "=== 网络 ==="
hostname -I
echo ""

# 服务状态
echo "=== Fly 服务状态 ==="
for svc in mavlink-router fly-acq fly-server fly-infer; do
    status=$(systemctl is-active $svc 2>/dev/null || echo "not-found")
    printf "  %-20s %s\n" "$svc:" "$status"
done
echo ""

# MAVLink 端口
echo "=== MAVLink 端口 ==="
ss -uln | grep -E "1455[0-2]" || echo "  无 MAVLink 端口监听"
echo ""

# 摄像头
echo "=== 摄像头设备 ==="
ls -la /dev/video* 2>/dev/null || echo "  无视频设备"
echo ""

# 串口
echo "=== 串口设备 ==="
ls -la /dev/ttyAMA* /dev/ttyUSB* 2>/dev/null || echo "  无串口设备"
echo ""

# 进程
echo "=== 进程（按内存排序 Top 10） ==="
ps aux --sort=-%mem | head -11
echo ""

echo "=========================================="
echo "  检查完成"
echo "=========================================="
