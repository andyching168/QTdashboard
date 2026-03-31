#!/bin/bash
# =============================================================================
# Luxgen M7 儀表板 - 開機自動啟動設定腳本
#
# 使用方式：
#   sudo bash /home/ac/QTdashboard/auto_start_setup.sh
#
# 功能：
#   1. 設定 tty1 自動登入 (使用者: ac)
#   2. 設定登入後自動啟動 X11 + 儀表板
#   3. 禁用桌面環境 (如果有)
# =============================================================================

set -e

SCRIPT_DIR="/home/ac/QTdashboard"
USERNAME="ac"

echo "=============================================="
echo "  Luxgen M7 儀表板 - 開機自動啟動設定"
echo "=============================================="
echo ""

# 檢查是否以 root 執行
if [ "$EUID" -ne 0 ]; then
    echo "❌ 請使用 sudo 執行此腳本"
    echo "   sudo bash $0"
    exit 1
fi

# --- 1. 設定 tty1 自動登入 ---
echo "📝 設定 tty1 自動登入..."

mkdir -p /etc/systemd/system/getty@tty1.service.d

cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $USERNAME --noclear %I \$TERM
Type=idle
EOF

echo "   ✅ 已設定自動登入使用者: $USERNAME"

# --- 2. 設定登入後自動啟動 X11 ---
echo "📝 設定登入後自動啟動儀表板..."

# 建立啟動腳本 (在 .bashrc 末尾調用，確保 login 和 non-login shell 都能執行)
DASHBOARD_AUTOSTART="/home/$USERNAME/.dashboard_autostart.sh"
cat > $DASHBOARD_AUTOSTART << 'AUTOSTART_EOF'
#!/bin/bash
# 儀表板自動啟動腳本 - 由 .bashrc 調用

BOOT_LOG="/tmp/dashboard_boot.log"

# 永遠記錄診斷資訊（無論條件是否滿足）
{
    echo ""
    echo "============================================="
    echo "$(date): .dashboard_autostart.sh 被呼叫"
    echo "  TTY 輸出: $(tty 2>&1)"
    echo "  DISPLAY: ${DISPLAY:-<空>}"
    echo "  USER: $USER"
    echo "  TERM: $TERM"
    echo "  PS1: ${PS1:0:20}..."
    echo "  XDG_SESSION_TYPE: ${XDG_SESSION_TYPE:-<未設定>}"
    echo "  強制啟動標記: $([ -f /tmp/.dashboard_force_start ] && echo '存在' || echo '不存在')"
    echo "  X Server 狀態: $(pgrep -x Xorg >/dev/null 2>&1 && echo '執行中' || echo '未執行')"
    echo "============================================="
} >> "$BOOT_LOG"

# TTY 檢測邏輯 (更可靠)
CURRENT_TTY="$(tty 2>/dev/null)"
IS_TTY1=false

# 方式 1: 標準 tty 命令
if [ "$CURRENT_TTY" = "/dev/tty1" ]; then
    IS_TTY1=true
    echo "$(date): 透過 tty=/dev/tty1 判定" >> "$BOOT_LOG"
# 方式 2: 環境變數 XDG_VTNR (systemd 設定)
elif [ "${XDG_VTNR:-}" = "1" ]; then
    IS_TTY1=true
    echo "$(date): 透過 XDG_VTNR=1 判定為 tty1" >> "$BOOT_LOG"
# 方式 3: 強制啟動標記 (由 ssh_start.sh 建立)
elif [ -f /tmp/.dashboard_force_start ]; then
    # 確保 X server 沒有在執行
    if ! pgrep -x "Xorg" > /dev/null 2>&1 && ! pgrep -x "X" > /dev/null 2>&1; then
        IS_TTY1=true
        echo "$(date): 透過 force_start 標記強制啟動" >> "$BOOT_LOG"
    else
        echo "$(date): 有 force_start 標記但 X 已在執行，跳過" >> "$BOOT_LOG"
    fi
# 方式 4: XDG_SESSION_TYPE=tty 且 X server 未執行 (解決 tty 返回 /dev/pts/x 的問題)
elif [ "${XDG_SESSION_TYPE:-}" = "tty" ]; then
    if ! pgrep -x "Xorg" > /dev/null 2>&1 && ! pgrep -x "X" > /dev/null 2>&1; then
        IS_TTY1=true
        echo "$(date): 透過 XDG_SESSION_TYPE=tty 且 X 未執行判定" >> "$BOOT_LOG"
    else
        echo "$(date): XDG_SESSION_TYPE=tty 但 X 已在執行，跳過" >> "$BOOT_LOG"
    fi
fi

# 檢查是否應該啟動
if [ "$IS_TTY1" = "true" ] && [ -z "$DISPLAY" ]; then
    echo "$(date): 條件滿足，開始啟動流程" >> "$BOOT_LOG"
    
    # 清除強制啟動標記
    rm -f /tmp/.dashboard_force_start
    
    echo "🚗 Luxgen M7 儀表板自動啟動中..."
    
    # 等待系統穩定 (GPU, 檔案系統等)
    echo "$(date): 等待系統穩定..." >> "$BOOT_LOG"
    sleep 3
    
    # 檢查 GPU 是否就緒 (最多等待 10 秒)
    echo "$(date): 檢查 GPU 狀態..." >> "$BOOT_LOG"
    GPU_READY=false
    for i in {1..20}; do
        if [ -e /dev/dri/card0 ] || [ -e /dev/dri/card1 ]; then
            GPU_READY=true
            echo "$(date): GPU 就緒 (嘗試 $i)" >> "$BOOT_LOG"
            break
        fi
        sleep 0.5
    done
    
    if [ "$GPU_READY" = "false" ]; then
        echo "$(date): 警告: GPU 未就緒，仍嘗試啟動" >> "$BOOT_LOG"
    fi
    
    # 檢查 CAN 設備是否就緒 (最多等待 15 秒)
    echo "$(date): 檢查 CAN 設備狀態..." >> "$BOOT_LOG"
    CAN_READY=false
    for i in {1..30}; do
        # 方式 1: 檢查 SocketCAN 介面 (can0)
        if ip link show can0 2>/dev/null | grep -q "state UP"; then
            CAN_READY=true
            echo "$(date): SocketCAN can0 就緒 (嘗試 $i)" >> "$BOOT_LOG"
            break
        fi
        # 方式 2: 檢查 USB CANable 設備
        if ls /dev/ttyACM* 2>/dev/null | head -1 > /dev/null; then
            CAN_READY=true
            echo "$(date): USB CAN 設備就緒 (嘗試 $i)" >> "$BOOT_LOG"
            break
        fi
        sleep 0.5
    done
    
    if [ "$CAN_READY" = "false" ]; then
        echo "$(date): 警告: CAN 設備未就緒，仍嘗試啟動 (將進入 demo 模式)" >> "$BOOT_LOG"
    fi
    
    # 檢查啟動腳本是否存在
    STARTX_SCRIPT="/home/ac/QTdashboard/startx_dashboard.sh"
    if [ ! -f "$STARTX_SCRIPT" ]; then
        echo "$(date): 錯誤: 啟動腳本不存在: $STARTX_SCRIPT" >> "$BOOT_LOG"
        echo "❌ 啟動腳本不存在: $STARTX_SCRIPT"
        return 1
    fi
    
    # startx 重試機制
    MAX_RETRIES=10
    RETRY_DELAY=1
    STARTX_SUCCESS=false
    
    for attempt in $(seq 1 $MAX_RETRIES); do
        echo "$(date): startx 嘗試 $attempt/$MAX_RETRIES..." >> "$BOOT_LOG"
        echo "🚀 啟動 X Server (嘗試 $attempt/$MAX_RETRIES)..."
        
        # 執行 startx，明確指定 vt1 避免 /dev/tty0 權限問題
        startx "$STARTX_SCRIPT" -- -nocursor vt1 >> "$BOOT_LOG" 2>&1
        STARTX_EXIT=$?
        echo "$(date): startx 結束，exit code: $STARTX_EXIT" >> "$BOOT_LOG"
        
        # 檢查結果
        if [ $STARTX_EXIT -eq 0 ]; then
            STARTX_SUCCESS=true
            echo "$(date): startx 成功完成" >> "$BOOT_LOG"
            break
        else
            echo "$(date): startx 失敗 (exit: $STARTX_EXIT)" >> "$BOOT_LOG"
            
            # 如果還有重試機會
            if [ $attempt -lt $MAX_RETRIES ]; then
                echo "⚠️  startx 失敗，${RETRY_DELAY} 秒後重試..."
                echo "$(date): 等待 ${RETRY_DELAY} 秒後重試..." >> "$BOOT_LOG"
                sleep $RETRY_DELAY
                
                # 確保 X 進程已完全停止
                pkill -9 Xorg 2>/dev/null || true
                pkill -9 X 2>/dev/null || true
                sleep 1
            fi
        fi
    done
    
    # 如果所有重試都失敗
    if [ "$STARTX_SUCCESS" != "true" ]; then
        echo "❌ startx 失敗，已重試 $MAX_RETRIES 次"
        echo "   請檢查: cat /tmp/dashboard_boot.log"
        echo "$(date): startx 最終失敗，已重試 $MAX_RETRIES 次" >> "$BOOT_LOG"
        sleep 30
    fi
else
    # 記錄未啟動的原因
    {
        echo "$(date): 條件不滿足，跳過啟動"
        echo "  IS_TTY1=$IS_TTY1"
        echo "  DISPLAY=${DISPLAY:-<空>}"
        if [ "$IS_TTY1" != "true" ]; then
            echo "  原因: 不在 tty1 上"
        fi
        if [ -n "$DISPLAY" ]; then
            echo "  原因: DISPLAY 已設定 (X 可能已在執行)"
        fi
    } >> "$BOOT_LOG"
fi
AUTOSTART_EOF

chown $USERNAME:$USERNAME $DASHBOARD_AUTOSTART
chmod 755 $DASHBOARD_AUTOSTART

echo "   ✅ 已建立 .dashboard_autostart.sh"

# 在 .bashrc 末尾加入啟動調用 (如果還沒有)
BASHRC="/home/$USERNAME/.bashrc"
if ! grep -q "dashboard_autostart" "$BASHRC" 2>/dev/null; then
    echo "" >> "$BASHRC"
    echo "# 儀表板自動啟動 (tty1)" >> "$BASHRC"
    echo "[ -f ~/.dashboard_autostart.sh ] && source ~/.dashboard_autostart.sh" >> "$BASHRC"
    echo "   ✅ 已更新 .bashrc"
else
    echo "   ℹ️  .bashrc 已包含啟動調用"
fi

# 建立 .bash_profile (確保 login shell 也能執行)
cat > /home/$USERNAME/.bash_profile << 'EOF'
# ~/.bash_profile - 登入時執行

# 載入 .bashrc (其中包含儀表板自動啟動邏輯)
if [ -f ~/.bashrc ]; then
    . ~/.bashrc
fi
EOF

chown $USERNAME:$USERNAME /home/$USERNAME/.bash_profile
chmod 644 /home/$USERNAME/.bash_profile

echo "   ✅ 已設定 .bash_profile"

# --- 3. 設定 .xinitrc (備用) ---
echo "📝 設定 .xinitrc (備用)..."

cat > /home/$USERNAME/.xinitrc << 'EOF'
#!/bin/bash
# ~/.xinitrc - startx 預設腳本 (備用)
exec /home/ac/QTdashboard/startx_dashboard.sh
EOF

chown $USERNAME:$USERNAME /home/$USERNAME/.xinitrc
chmod 755 /home/$USERNAME/.xinitrc

echo "   ✅ 已設定 .xinitrc"

# --- 4. 確保啟動腳本有執行權限 ---
echo "📝 檢查腳本權限..."

chmod +x $SCRIPT_DIR/startx_dashboard.sh
chmod +x $SCRIPT_DIR/startup_progress.py 2>/dev/null || true
chmod +x $SCRIPT_DIR/dashboard_watchdog.sh 2>/dev/null || true

echo "   ✅ 腳本權限已設定"

# --- 4.5. 設定 Watchdog (cron) ---
echo "📝 設定 Watchdog 監控..."

# 移除舊的 watchdog cron 任務
crontab -u $USERNAME -l 2>/dev/null | grep -v "dashboard_watchdog.sh" | crontab -u $USERNAME - 2>/dev/null || true

# 新增 watchdog cron 任務 (每分鐘執行)
(crontab -u $USERNAME -l 2>/dev/null; echo "* * * * * $SCRIPT_DIR/dashboard_watchdog.sh >> /tmp/dashboard_watchdog.log 2>&1") | crontab -u $USERNAME -

echo "   ✅ Watchdog cron 已設定"

# --- 5. 設定系統為 multi-user (CLI) 模式 ---
echo "📝 設定系統為 CLI 模式..."

# 使用 raspi-config 設定為 CLI 自動登入
if command -v raspi-config >/dev/null 2>&1; then
    # B1 = Console, B2 = Console Autologin, B3 = Desktop, B4 = Desktop Autologin
    raspi-config nonint do_boot_behaviour B2 2>/dev/null || true
    echo "   ✅ 已設定為 Console 自動登入模式"
else
    # 手動設定 default target
    systemctl set-default multi-user.target
    echo "   ✅ 已設定 multi-user.target"
fi

# --- 6. 禁用不需要的服務 (加快開機) ---
echo "📝 優化開機速度..."

# 禁用藍牙 (如果不需要)
# systemctl disable bluetooth 2>/dev/null || true

# 禁用 ModemManager (如果有)
systemctl disable ModemManager 2>/dev/null || true

echo "   ✅ 已優化"

# --- 7. 重新載入 systemd ---
echo "📝 重新載入 systemd..."
systemctl daemon-reload

echo ""
echo "=============================================="
echo "  ✅ 設定完成！"
echo "=============================================="
echo ""
echo "重新啟動後，系統會自動："
echo "  1. 登入使用者 '$USERNAME'"
echo "  2. 啟動 X11"
echo "  3. 執行儀表板程式"
echo ""
echo "請執行以下命令重新啟動："
echo "  sudo reboot"
echo ""
echo "如需取消自動啟動，執行："
echo "  sudo bash $SCRIPT_DIR/auto_start_disable.sh"
echo ""
