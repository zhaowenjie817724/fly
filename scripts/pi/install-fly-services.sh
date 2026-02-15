#!/bin/bash
# install-fly-services.sh - 安装 WuRenji 系统服务
# 用法: sudo ./install-fly-services.sh [用户名] [用户组] [fly目录] [采集配置]
# 兼容 Ubuntu 24.04 / Raspberry Pi OS
#
# 服务模板使用 __PLACEHOLDER__ 占位符，安装时渲染为实际值
set -euo pipefail

APP_USER="${1:-${SUDO_USER:-$USER}}"
APP_GROUP="${2:-$APP_USER}"
FLY_DIR="${3:-/home/$APP_USER/fly}"
ACQ_CONFIG="${4:-configs/pi_bookworm.yaml}"
API_CONFIG="configs/service.yaml"
FSM_CONFIG="configs/fsm.yaml"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
UNIT_SRC_DIR="${FLY_DIR}/scripts/systemd"
if [ ! -d "$UNIT_SRC_DIR" ]; then
    UNIT_SRC_DIR="${REPO_ROOT}/scripts/systemd"
fi

# ----------------------------------------------------------
# 输入校验
# ----------------------------------------------------------
validate_input() {
    # 校验用户名格式
    if ! echo "$APP_USER" | grep -qE '^[a-z_][a-z0-9_-]*$'; then
        echo "错误: 无效用户名 '$APP_USER' (需匹配 [a-z_][a-z0-9_-]*)"
        exit 1
    fi
    if ! echo "$APP_GROUP" | grep -qE '^[a-z_][a-z0-9_-]*$'; then
        echo "错误: 无效用户组 '$APP_GROUP'"
        exit 1
    fi
    # 校验路径为绝对路径
    if [[ "$FLY_DIR" != /* ]]; then
        echo "错误: FLY_DIR 必须是绝对路径，当前: '$FLY_DIR'"
        exit 1
    fi
    # 校验用户存在
    if ! id "$APP_USER" &>/dev/null; then
        echo "错误: 用户 '$APP_USER' 不存在"
        exit 1
    fi
}

echo "=== 安装 WuRenji 系统服务 ==="
echo "APP_USER  : $APP_USER"
echo "APP_GROUP : $APP_GROUP"
echo "FLY_DIR   : $FLY_DIR"
echo "ACQ_CONFIG: $ACQ_CONFIG"
echo ""

validate_input

# 检查目录
if [ ! -d "$FLY_DIR" ]; then
    echo "错误: $FLY_DIR 不存在"
    exit 1
fi

# 检查虚拟环境
if [ ! -x "$FLY_DIR/.venv/bin/python" ]; then
    echo "错误: Python 虚拟环境不存在: $FLY_DIR/.venv/bin/python"
    echo "请先运行: python3 -m venv $FLY_DIR/.venv"
    exit 1
fi

# 检查服务文件目录
if [ ! -d "$UNIT_SRC_DIR" ]; then
    echo "错误: 服务文件目录不存在: $UNIT_SRC_DIR"
    exit 1
fi

# ----------------------------------------------------------
# 创建运行时目录
# ----------------------------------------------------------
echo "创建运行时目录..."
sudo install -d -m 0755 -o "$APP_USER" -g "$APP_GROUP" "$FLY_DIR/runs" "$FLY_DIR/logs"
sudo mkdir -p /etc/mavlink-router

# 安装 mavlink-router 配置
if [ -f "$FLY_DIR/configs/mavlink-router.conf" ]; then
    sudo install -m 0644 "$FLY_DIR/configs/mavlink-router.conf" /etc/mavlink-router/main.conf
elif [ -f "$REPO_ROOT/configs/mavlink-router.conf" ]; then
    sudo install -m 0644 "$REPO_ROOT/configs/mavlink-router.conf" /etc/mavlink-router/main.conf
else
    echo "警告: mavlink-router.conf 未找到，跳过"
fi

# ----------------------------------------------------------
# 渲染并安装服务文件
# ----------------------------------------------------------
render_and_install() {
    local src="$1"
    local dst="$2"

    if [ ! -f "$src" ]; then
        echo "错误: 缺少服务模板: $src"
        exit 1
    fi

    sed \
        -e "s|__APP_USER__|${APP_USER}|g" \
        -e "s|__APP_GROUP__|${APP_GROUP}|g" \
        -e "s|__FLY_DIR__|${FLY_DIR}|g" \
        -e "s|__ACQ_CONFIG__|${ACQ_CONFIG}|g" \
        -e "s|__API_CONFIG__|${API_CONFIG}|g" \
        -e "s|__FSM_CONFIG__|${FSM_CONFIG}|g" \
        "$src" | sudo tee "$dst" > /dev/null
    sudo chmod 644 "$dst"
    echo "  已安装: $(basename "$dst")"
}

echo "安装 WuRenji 服务文件..."
for svc in wurenji-acq wurenji-api wurenji-fsm wurenji-watchdog; do
    render_and_install "$UNIT_SRC_DIR/$svc.service" "/etc/systemd/system/$svc.service"
done

# 安装 mavlink-router 服务
if [ -f "$FLY_DIR/scripts/pi/mavlink-router.service" ]; then
    # 探测 mavlink-routerd 实际路径
    MAVLINK_BIN="$(command -v mavlink-routerd 2>/dev/null || echo '/usr/local/bin/mavlink-routerd')"
    sed "s|/usr/local/bin/mavlink-routerd|${MAVLINK_BIN}|g" \
        "$FLY_DIR/scripts/pi/mavlink-router.service" | sudo tee /etc/systemd/system/mavlink-router.service > /dev/null
    sudo chmod 644 /etc/systemd/system/mavlink-router.service
    echo "  已安装: mavlink-router.service (bin: $MAVLINK_BIN)"
fi

# ----------------------------------------------------------
# 写入环境变量文件（供脚本和调试使用，不再用于 systemd 变量展开）
# ----------------------------------------------------------
sudo mkdir -p /etc/wurenji
TMP_ENV="$(mktemp)"
cat > "$TMP_ENV" <<EOF
# WuRenji runtime environment (for scripts and debugging)
APP_USER=$APP_USER
APP_GROUP=$APP_GROUP
FLY_DIR=$FLY_DIR
RUNS_DIR=$FLY_DIR/runs
LOGS_DIR=$FLY_DIR/logs
FLY_ACQ_CONFIG=$ACQ_CONFIG
FLY_API_CONFIG=$API_CONFIG
FLY_FSM_CONFIG=$FSM_CONFIG
EOF
sudo install -m 0644 "$TMP_ENV" /etc/wurenji/wurenji.env
rm -f "$TMP_ENV"
echo "  已写入: /etc/wurenji/wurenji.env"

# ----------------------------------------------------------
# 禁用旧版 fly-* 服务
# ----------------------------------------------------------
echo "禁用旧版 fly-* 服务..."
for legacy in fly-acq.service fly-server.service fly-infer.service; do
    if systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}' | grep -Fxq "$legacy"; then
        sudo systemctl disable --now "$legacy" 2>/dev/null || true
        echo "  已禁用: $legacy"
    fi
done

# ----------------------------------------------------------
# 重新加载并启用服务
# ----------------------------------------------------------
sudo systemctl daemon-reload

echo "启用服务..."
ENABLE_LIST="wurenji-acq wurenji-api wurenji-fsm wurenji-watchdog"
if [ -f /etc/systemd/system/mavlink-router.service ]; then
    ENABLE_LIST="mavlink-router $ENABLE_LIST"
fi

for svc in $ENABLE_LIST; do
    if sudo systemctl enable "$svc" 2>/dev/null; then
        echo "  已启用: $svc"
    else
        echo "  警告: 启用 $svc 失败"
    fi
done

echo ""
echo "=== 服务安装完成 ==="
echo ""
echo "启动服务:"
echo "  sudo systemctl start $ENABLE_LIST"
echo ""
echo "查看状态:"
echo "  sudo systemctl status wurenji-acq"
echo ""
echo "查看日志:"
echo "  journalctl -u wurenji-acq -f"
