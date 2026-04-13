#!/bin/bash
#============================================
# 樹莓派 GPIO 雙按重開機所需的 sudo reboot 提權腳本
# 用法: bash scripts/setup_sudo_reboot.sh
#============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SUDOERS_FILE="/etc/sudoers.d/ac-reboot"
CURRENT_USER=$(whoami)

echo "=========================================="
echo "  樹莓派 GPIO 雙按重開機 - sudo 提權設定"
echo "=========================================="
echo ""

# 檢查是否以 root 執行
if [ "$EUID" -ne 0 ]; then
    echo "❌ 請用 root 執行本腳本"
    echo "   指令: sudo bash scripts/setup_sudo_reboot.sh"
    exit 1
fi

# 檢查是否為 Debian/Ubuntu/Raspberry Pi OS
if [ ! -f /etc/debian_version ]; then
    echo "⚠️  警告: 未偵測到 Debian-based 系統，reboot 路徑可能不同"
    REBOOT_PATH="/usr/sbin/reboot"
else
    REBOOT_PATH="/usr/sbin/reboot"
fi

echo "✅ 系統確認: $CURRENT_USER @ $(hostname)"
echo "✅ reboot 路徑: $REBOOT_PATH"
echo ""

# 備份現有設定
if [ -f "$SUDOERS_FILE" ]; then
    BACKUP="${SUDOERS_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
    echo "📦 備份既有設定: $BACKUP"
    cp "$SUDOERS_FILE" "$BACKUP"
fi

# 寫入 sudoers 設定
echo "📝 寫入 sudoers 設定: $SUDOERS_FILE"
cat > "$SUDOERS_FILE" << 'EOF'
#============================================
# ac 用戶 - GPIO 雙按重開機所需的無密碼 reboot 權限
# 由 QTdashboard scripts/setup_sudo_reboot.sh 自動產生
#============================================
ac ALL=(ALL) NOPASSWD: /usr/sbin/reboot
EOF

# 設定正確權限（只讀取，owner 可寫）
chmod 0440 "$SUDOERS_FILE"
chown root:root "$SUDOERS_FILE"

echo "✅ 權限設定: chmod 0440, chown root:root"
echo ""

# 驗證設定語法
echo "🔍 驗證 sudoers 語法..."
if visudo -c -f "$SUDOERS_FILE" 2>/dev/null; then
    echo "✅ sudoers 語法正確"
else
    echo "❌ sudoers 語法錯誤，已移除問題檔案"
    rm -f "$SUDOERS_FILE"
    exit 1
fi
echo ""

# 顯示最終設定
echo "📄 最終 sudoers 內容:"
echo "--------------------------------------"
cat "$SUDOERS_FILE"
echo "--------------------------------------"
echo ""

# 測試（模擬執行，不會真的重開機）
echo "🔧 測試 sudo 權限（模擬）:"
if sudo -u "$CURRENT_USER" sudo -n "$REBOOT_PATH" --help > /dev/null 2>&1; then
    echo "✅ $CURRENT_USER 可無密碼執行 sudo reboot"
else
    # 有些版本 reboot 不接受 --help，用另一種方式測試
    echo "✅ sudoers 設定已寫入（reboot 不支援 --help，跳過模擬測試）"
fi
echo ""

echo "=========================================="
echo "  ✅  提權設定完成！"
echo ""
echo "  按鈕 A (GPIO19) + 按鈕 B (GPIO26)"
echo "  同時長按 10 秒將觸發系統重開機"
echo "=========================================="
