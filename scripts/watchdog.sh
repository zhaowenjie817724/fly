#!/bin/bash
# ==========================================================
#  通感之眼2.0 - 进程看门狗
#  监控关键进程存活状态，崩溃时重启对应 systemd 服务
#  兼容 Ubuntu 24.04 / Raspberry Pi OS
# ==========================================================
set -euo pipefail

CHECK_INTERVAL="${CHECK_INTERVAL:-30}"
MAX_MEM_PCT="${MAX_MEM_PCT:-85}"
MIN_FREE_MB="${MIN_FREE_MB:-500}"
KEEP_RUNS="${KEEP_RUNS:-5}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_FLY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
FLY_DIR="${FLY_DIR:-$DEFAULT_FLY_DIR}"
RUNS_DIR="${RUNS_DIR:-$FLY_DIR/runs}"

SYSTEMCTL_CMD=(systemctl)
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
    SYSTEMCTL_CMD=(sudo systemctl)
fi

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WATCHDOG] $1"
}

restart_service() {
    local service="$1"
    log "服务 ${service} 已停止，正在重启..."
    "${SYSTEMCTL_CMD[@]}" restart "$service" || true
    sleep 3
    if "${SYSTEMCTL_CMD[@]}" is-active --quiet "$service"; then
        log "服务 ${service} 重启成功"
    else
        log "服务 ${service} 重启失败!"
    fi
}

check_service() {
    local service="$1"
    if "${SYSTEMCTL_CMD[@]}" is-active --quiet "$service"; then
        return 0
    fi
    restart_service "$service"
    return 1
}

drop_caches() {
    sync
    if [ "$(id -u)" -eq 0 ]; then
        echo 3 > /proc/sys/vm/drop_caches || true
    elif command -v sudo >/dev/null 2>&1; then
        echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null 2>&1 || true
    fi
}

check_memory() {
    local used_pct
    used_pct=$(free | awk '/Mem:/ {printf "%.0f", $3/$2*100}')
    if [ "$used_pct" -gt "$MAX_MEM_PCT" ]; then
        log "内存使用率过高: ${used_pct}%，清理缓存..."
        drop_caches
    fi
}

check_disk() {
    [ -d "$RUNS_DIR" ] || return 0

    local free_mb
    local cutoff
    free_mb=$(df -BM "$RUNS_DIR" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'M')
    if [ -n "${free_mb:-}" ] && [ "$free_mb" -lt "$MIN_FREE_MB" ]; then
        log "磁盘空间不足 ${free_mb}MB，清理旧 run 数据..."
        cutoff=$((KEEP_RUNS + 1))
        (
            cd "$RUNS_DIR" || exit 0
            ls -1td -- */ 2>/dev/null | tail -n +"${cutoff}" | xargs -r rm -rf --
        )
        log "旧数据已清理 (保留最近 ${KEEP_RUNS} 个)"
    fi
}

check_temperature() {
    if [ -r /sys/class/thermal/thermal_zone0/temp ]; then
        local temp
        local temp_c
        temp=$(cat /sys/class/thermal/thermal_zone0/temp)
        temp_c=$((temp / 1000))
        if [ "$temp_c" -gt 80 ]; then
            log "CPU 温度过高: ${temp_c}C"
        fi
    fi
}

log "看门狗启动 (间隔: ${CHECK_INTERVAL}s, fly_dir: ${FLY_DIR})"

while true; do
    check_service "wurenji-acq"
    check_service "wurenji-api"
    check_service "wurenji-fsm"
    check_memory
    check_disk
    check_temperature
    sleep "$CHECK_INTERVAL"
done
