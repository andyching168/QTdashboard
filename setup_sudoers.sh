#!/bin/bash
# ============================================================
# QTdashboard 免密碼權限設定腳本
# 此腳本需要在 Raspberry Pi 上執行一次
# 執行後，儀表板程式可以無需密碼執行重啟、關機、NTP同步
# ============================================================

set -e

echo "=============================================="
echo "QTdashboard 免密碼權限設定"
echo "=============================================="

# 檢查是否為 root 或有 sudo 權限
if [ "$EUID" -ne 0 ]; then
    echo "此腳本需要 sudo 權限執行"
    echo "請使用: sudo bash setup_sudoers.sh"
    exit 1
fi

# 取得當前使用者（如果用 sudo 執行，取得原始使用者）
if [ -n "$SUDO_USER" ]; then
    TARGET_USER="$SUDO_USER"
else
    TARGET_USER="$(whoami)"
fi

echo ""
echo "目標使用者: $TARGET_USER"
echo ""

# 建立 sudoers.d 設定檔
SUDOERS_FILE="/etc/sudoers.d/qtdashboard"

echo "正在建立 sudoers 設定檔: $SUDOERS_FILE"

cat > "$SUDOERS_FILE" << EOF
# QTdashboard 免密碼權限設定
# 此檔案由 setup_sudoers.sh 自動產生
# 產生時間: $(date)

# 允許 $TARGET_USER 執行以下指令不需要密碼:

# 系統電源控制
$TARGET_USER ALL=(ALL) NOPASSWD: /sbin/reboot
$TARGET_USER ALL=(ALL) NOPASSWD: /sbin/shutdown
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/sbin/reboot
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/sbin/shutdown

# NTP 時間同步
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/sbin/ntpdate
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/timedatectl
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/chronyc

# systemd 時間同步服務
$TARGET_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart systemd-timesyncd
$TARGET_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart systemd-timesyncd
EOF

# 設定正確的權限（sudoers 檔案必須是 0440）
chmod 0440 "$SUDOERS_FILE"

# 驗證語法
echo ""
echo "驗證 sudoers 語法..."
if visudo -c -f "$SUDOERS_FILE"; then
    echo "✓ 語法正確"
else
    echo "✗ 語法錯誤，移除設定檔"
    rm -f "$SUDOERS_FILE"
    exit 1
fi

echo ""
echo "=============================================="
echo "✓ 設定完成！"
echo "=============================================="
echo ""
echo "已授權 $TARGET_USER 執行以下指令不需要密碼:"
echo "  - sudo reboot       (系統重啟)"
echo "  - sudo shutdown     (系統關機)"
echo "  - sudo ntpdate      (NTP 時間同步)"
echo "  - sudo timedatectl  (時間設定)"
echo ""
echo "現在 QTdashboard 可以:"
echo "  ✓ 從控制面板直接重啟/關機"
echo "  ✓ 啟動時自動同步網路時間"
echo ""
echo "如需移除這些權限，執行:"
echo "  sudo rm $SUDOERS_FILE"
echo ""
