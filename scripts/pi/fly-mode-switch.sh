#!/bin/bash
# fly-mode-switch.sh - 桌面/无桌面模式切换
# 兼容 Ubuntu 24.04 (gdm3) / Raspberry Pi OS (lightdm)
# 用法: fly-headless 或 fly-desktop 或 fly-mode-switch.sh headless/desktop
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
DM_UNIT="display-manager.service"
ACTION="${1:-}"

# 根据脚本名推断 action
case "$SCRIPT_NAME" in
    fly-headless) ACTION="headless" ;;
    fly-desktop)  ACTION="desktop" ;;
esac

has_display_manager() {
    systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}' | grep -Fxq "$DM_UNIT"
}

case "$ACTION" in
    headless)
        echo "切换到无桌面模式（headless）..."
        sudo systemctl set-default multi-user.target
        if has_display_manager; then
            sudo systemctl stop "$DM_UNIT" || true
            echo "已停止 $DM_UNIT"
        else
            echo "未安装桌面管理器，无需停止"
        fi
        echo "设置完成。重启后生效: sudo reboot"
        ;;
    desktop)
        echo "切换到桌面模式..."
        sudo systemctl set-default graphical.target
        if has_display_manager; then
            sudo systemctl start "$DM_UNIT" || true
            echo "已启动 $DM_UNIT"
        else
            echo "未安装桌面管理器，请先安装 gdm3 或 lightdm"
        fi
        echo "设置完成。重启后生效: sudo reboot"
        ;;
    *)
        echo "用法: fly-headless | fly-desktop"
        echo "  或: $(basename "$0") headless"
        echo "  或: $(basename "$0") desktop"
        echo ""
        echo "  headless - 切换到命令行模式（省内存）"
        echo "  desktop  - 切换到桌面模式"
        echo ""
        echo "当前默认模式:"
        echo "  $(systemctl get-default)"
        if has_display_manager; then
            echo "桌面管理器: $DM_UNIT (已安装)"
        else
            echo "桌面管理器: 未安装"
        fi
        exit 1
        ;;
esac
