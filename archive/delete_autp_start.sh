#!/bin/bash
echo "=== 清除所有儀表板自動啟動設定 ==="

# 1. systemd autologin
sudo rm -rf /etc/systemd/system/getty@tty1.service.d/
echo "✓ 已移除 getty autologin"

# 2. bash_profile
rm -f ~/.bash_profile
echo "✓ 已移除 .bash_profile"

# 3. bashrc 中的啟動行
sed -i '/dashboard_autostart/d' ~/.bashrc
sed -i '/startx.*dashboard/d' ~/.bashrc
echo "✓ 已清理 .bashrc"

# 4. dashboard_autostart.sh
rm -f ~/.dashboard_autostart.sh
echo "✓ 已移除 .dashboard_autostart.sh"

# 5. xinitrc
rm -f ~/.xinitrc
echo "✓ 已移除 .xinitrc"

# 6. crontab 中的 dashboard 相關
crontab -l 2>/dev/null | grep -v "dashboard" | crontab -
echo "✓ 已清理 crontab"

# 7. systemd service
sudo systemctl disable dashboard.service 2>/dev/null
sudo rm -f /etc/systemd/system/dashboard.service
echo "✓ 已移除 dashboard.service"

# 8. 桌面 autostart
rm -f ~/.config/autostart/*dashboard*.desktop 2>/dev/null
echo "✓ 已清理桌面 autostart"

# 重載 systemd
sudo systemctl daemon-reload

echo ""
echo "=== 清除完成 ==="
echo "重開機後系統將正常啟動到 CLI 或桌面"