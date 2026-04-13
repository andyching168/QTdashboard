#!/bin/bash
#============================================
# 安裝 USB 重置 systemd service + timer
# 用法: sudo bash scripts/install_reset_usb_service.sh
#============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_FILE="$PROJECT_ROOT/../tmp/reset-usb.service"
TIMER_FILE="$PROJECT_ROOT/../tmp/reset-usb.timer"

# systemd 安裝目標
SYSTEMD_DIR="/etc/systemd/system"
SERVICE_LINK="$SYSTEMD_DIR/reset-usb.service"
TIMER_LINK="$SYSTEMD_DIR/reset-usb.timer"
SCRIPT_TARGET="/home/ac/QTdashboard/scripts/reset_usb.sh"

echo "=========================================="
echo "  USB 重置 systemd Service 安裝腳本"
echo "=========================================="

#------------------
# 檢查
#------------------
if [ "$EUID" -ne 0 ]; then
    echo "❌ 需要 root 執行"
    echo "   sudo bash scripts/install_reset_usb_service.sh"
    exit 1
fi

if [ ! -f "$SCRIPT_TARGET" ]; then
    echo "❌ 找不到 reset_usb.sh: $SCRIPT_TARGET"
    exit 1
fi

# 從專案的 tmp/ 目錄讀 service/timer（如果存在的話）
# 或是直接用專案內的
if [ -f "$PROJECT_ROOT/reset-usb.service" ]; then
    SERVICE_SRC="$PROJECT_ROOT/reset-usb.service"
    TIMER_SRC="$PROJECT_ROOT/reset-usb.timer"
elif [ -f "$PROJECT_ROOT/../tmp/reset-usb.service" ]; then
    SERVICE_SRC="$PROJECT_ROOT/../tmp/reset-usb.service"
    TIMER_SRC="$PROJECT_ROOT/../tmp/reset-usb.timer"
else
    echo "❌ 找不到 service/timer 檔案"
    echo "   請確認 reset-usb.service 和 reset-usb.timer 在專案目錄中"
    exit 1
fi

echo "✅ Service: $SERVICE_SRC"
echo "✅ Timer:   $TIMER_SRC"
echo "✅ Script:  $SCRIPT_TARGET"
echo ""

#------------------
# 安裝 service
#------------------
echo "📦 安裝 systemd service..."
cp "$SERVICE_SRC" "$SERVICE_LINK"
chmod 644 "$SERVICE_LINK"
echo "✅ 已安裝: $SERVICE_LINK"

#------------------
# 安裝 timer
#------------------
echo "📦 安裝 systemd timer..."
cp "$TIMER_SRC" "$TIMER_LINK"
chmod 644 "$TIMER_LINK"
echo "✅ 已安裝: $TIMER_LINK"

#------------------
# 重新載入 systemd
#------------------
echo "🔄 重新載入 systemd daemon..."
systemctl daemon-reload

#------------------
# 啟用並啟動 timer
#------------------
echo ""
echo "🚀 啟用並啟動 USB 重置計時器..."
systemctl enable reset-usb.timer
systemctl start  reset-usb.timer

#------------------
# 顯示狀態
#------------------
echo ""
echo "📊 Timer 狀態："
systemctl status reset-usb.timer --no-pager || true

echo ""
echo "📊 Service 歷史記錄："
systemctl list-unit-files reset-usb.service --no-pager || true

echo ""
echo "=========================================="
echo "  ✅ 安裝完成！"
echo ""
echo "  常用指令："
echo "  ────────────────────────────────"
echo "  檢查 Timer:   systemctl status reset-usb.timer"
echo "  檢查 Service: journalctl -u reset-usb -f"
echo "  手動執行:     sudo bash $SCRIPT_TARGET --force"
echo "  停止 Timer:   sudo systemctl stop reset-usb.timer"
echo "  解除安裝:     sudo systemctl disable reset-usb.timer reset-usb.service"
echo "              && sudo rm /etc/systemd/system/reset-usb.{service,timer}"
echo "=========================================="
