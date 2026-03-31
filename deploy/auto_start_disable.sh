#!/bin/bash
# =============================================================================
# Luxgen M7 儀表板 - 取消開機自動啟動
#
# 使用方式：
#   sudo bash /home/ac/QTdashboard/auto_start_disable.sh
# =============================================================================

set -e

USERNAME="ac"

echo "=============================================="
echo "  Luxgen M7 儀表板 - 取消開機自動啟動"
echo "=============================================="
echo ""

# 檢查是否以 root 執行
if [ "$EUID" -ne 0 ]; then
    echo "❌ 請使用 sudo 執行此腳本"
    exit 1
fi

# 移除自動登入設定
echo "📝 移除自動登入設定..."
rm -f /etc/systemd/system/getty@tty1.service.d/autologin.conf
rmdir /etc/systemd/system/getty@tty1.service.d 2>/dev/null || true

# 移除 .bash_profile 中的自動啟動
echo "📝 移除 .bash_profile..."
rm -f /home/$USERNAME/.bash_profile

# 使用 raspi-config 恢復桌面 (如果需要)
if command -v raspi-config >/dev/null 2>&1; then
    echo "📝 恢復桌面登入模式..."
    raspi-config nonint do_boot_behaviour B4 2>/dev/null || true
fi

# 重新載入 systemd
systemctl daemon-reload

echo ""
echo "=============================================="
echo "  ✅ 已取消開機自動啟動"
echo "=============================================="
echo ""
echo "重新啟動後會進入正常桌面環境"
echo "  sudo reboot"
echo ""
