#!/bin/bash
# =============================================================================
# 切換到 systemd service 啟動方式
# 
# 使用方式：
#   sudo bash setup_systemd_service.sh
#
# 這會：
#   1. 禁用舊的 getty 自動登入 + .bashrc 啟動方式
#   2. 安裝並啟用 dashboard.service
#   3. 設定開機自動啟動
# =============================================================================

set -e

SCRIPT_DIR="/home/ac/QTdashboard"
SERVICE_FILE="$SCRIPT_DIR/dashboard.service"
USERNAME="ac"

echo "=============================================="
echo "  切換到 systemd service 啟動方式"
echo "=============================================="
echo ""

# 檢查是否以 root 執行
if [ "$EUID" -ne 0 ]; then
    echo "❌ 請使用 sudo 執行此腳本"
    echo "   sudo bash $0"
    exit 1
fi

# 檢查 service 檔案是否存在
if [ ! -f "$SERVICE_FILE" ]; then
    echo "❌ 找不到 service 檔案: $SERVICE_FILE"
    exit 1
fi

echo "📝 步驟 1/5: 停止現有的 X Server（如果有）..."
pkill -9 Xorg 2>/dev/null || true
pkill -9 xinit 2>/dev/null || true
sleep 1
echo "   ✅ 完成"

echo ""
echo "📝 步驟 2/5: 禁用舊的 getty 自動登入方式..."

# 移除 getty@tty1 的 autologin 設定
if [ -f /etc/systemd/system/getty@tty1.service.d/autologin.conf ]; then
    rm -f /etc/systemd/system/getty@tty1.service.d/autologin.conf
    echo "   已移除 getty@tty1 autologin 設定"
fi

# 注釋掉 .bashrc 中的自動啟動
BASHRC="/home/$USERNAME/.bashrc"
if grep -q "dashboard_autostart" "$BASHRC" 2>/dev/null; then
    sed -i 's/^\(\[ -f ~\/.dashboard_autostart.sh \] && source ~\/.dashboard_autostart.sh\)$/# \1  # 已切換到 systemd service/' "$BASHRC"
    echo "   已注釋 .bashrc 中的自動啟動"
fi

echo "   ✅ 完成"

echo ""
echo "📝 步驟 3/5: 安裝 dashboard.service..."

# 複製 service 檔案
cp "$SERVICE_FILE" /etc/systemd/system/dashboard.service
echo "   已複製到 /etc/systemd/system/"

# 重新載入 systemd
systemctl daemon-reload
echo "   已重新載入 systemd"

echo "   ✅ 完成"

echo ""
echo "📝 步驟 4/5: 啟用 dashboard.service..."

# 停用 getty@tty1（因為我們的 service 會接管 tty1）
systemctl disable getty@tty1.service 2>/dev/null || true

# 啟用 dashboard.service
systemctl enable dashboard.service
echo "   dashboard.service 已設定為開機自動啟動"

echo "   ✅ 完成"

echo ""
echo "📝 步驟 5/5: 設定 X Server 權限..."

# 確保 Xwrapper.config 正確設定
mkdir -p /etc/X11
cat > /etc/X11/Xwrapper.config << 'EOF'
allowed_users=anybody
needs_root_rights=yes
EOF
echo "   已設定 Xwrapper.config"

# 確保使用者在正確的群組中
usermod -a -G tty,video,input "$USERNAME" 2>/dev/null || true
echo "   已確認使用者群組權限"

echo "   ✅ 完成"

echo ""
echo "=============================================="
echo "  ✅ 設定完成！"
echo "=============================================="
echo ""
echo "🎯 現在可以："
echo ""
echo "   1. 立即啟動測試："
echo "      sudo systemctl start dashboard.service"
echo ""
echo "   2. 查看狀態："
echo "      sudo systemctl status dashboard.service"
echo ""
echo "   3. 查看日誌："
echo "      journalctl -u dashboard.service -f"
echo ""
echo "   4. 重新啟動系統測試開機自動啟動："
echo "      sudo reboot"
echo ""
echo "💡 如需切換回舊的 getty 方式："
echo "   sudo bash $SCRIPT_DIR/auto_start_setup.sh"
echo ""
