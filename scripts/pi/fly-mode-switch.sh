#!/bin/bash
# fly-mode-switch.sh - 桌面/无桌面模式切换
# 用法: fly-headless 或 fly-desktop

SCRIPT_NAME=$(basename "$0")

case "$SCRIPT_NAME" in
    fly-headless)
        echo "切换到无桌面模式（headless）..."
        sudo systemctl set-default multi-user.target
        echo "设置完成。重启后生效："
        echo "  sudo reboot"
        echo ""
        echo "临时停止桌面（不重启）："
        echo "  sudo systemctl stop lightdm"
        ;;
    fly-desktop)
        echo "切换到桌面模式..."
        sudo systemctl set-default graphical.target
        echo "设置完成。重启后生效："
        echo "  sudo reboot"
        echo ""
        echo "临时启动桌面（不重启）："
        echo "  sudo systemctl start lightdm"
        ;;
    *)
        echo "用法: fly-headless | fly-desktop"
        echo ""
        echo "  fly-headless  - 切换到命令行模式（省内存）"
        echo "  fly-desktop   - 切换到桌面模式"
        echo ""
        echo "当前默认模式:"
        systemctl get-default
        exit 1
        ;;
esac
