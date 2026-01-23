#!/bin/bash
# =============================================================================
# 儀表板 Watchdog 腳本
# 
# 功能:
#   監控儀表板程式狀態，如果 X 已啟動但 Python 腳本未執行，
#   自動嘗試在現有 X session 中啟動儀表板
#
# 使用方式:
#   此腳本會由 cron 或 systemd timer 每分鐘執行一次
#   手動執行: ./dashboard_watchdog.sh
#
# 安裝 (cron):
#   crontab -e
#   * * * * * /home/ac/QTdashboard/dashboard_watchdog.sh >> /tmp/dashboard_watchdog.log 2>&1
# =============================================================================

SCRIPT_DIR="/home/ac/QTdashboard"
WATCHDOG_LOG="/tmp/dashboard_watchdog.log"
LOCK_FILE="/tmp/.dashboard_watchdog.lock"
COOLDOWN_FILE="/tmp/.dashboard_watchdog_cooldown"
COOLDOWN_SECONDS=120  # 冷卻時間 2 分鐘，避免重複觸發

# 取得鎖，避免多個 watchdog 同時執行
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "$(date): Watchdog 已在執行中，退出"
    exit 0
fi

log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1"
}

# 檢查冷卻時間
if [ -f "$COOLDOWN_FILE" ]; then
    LAST_RUN=$(cat "$COOLDOWN_FILE" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    ELAPSED=$((NOW - LAST_RUN))
    if [ $ELAPSED -lt $COOLDOWN_SECONDS ]; then
        # 仍在冷卻中，靜默退出
        exit 0
    fi
fi

# 檢查 X Server 狀態
X_RUNNING=false
if pgrep -x "Xorg" > /dev/null || pgrep -x "X" > /dev/null; then
    X_RUNNING=true
fi

# 檢查 Python 儀表板程式狀態
DASHBOARD_RUNNING=false
if pgrep -f "datagrab.py|demo_mode.py|main.py" > /dev/null; then
    DASHBOARD_RUNNING=true
fi

# 檢查是否有手動退出標記
MANUAL_EXIT=false
if [ -f "/tmp/.dashboard_manual_exit" ]; then
    MANUAL_EXIT=true
fi

# 決策邏輯
if [ "$X_RUNNING" = "true" ] && [ "$DASHBOARD_RUNNING" = "false" ] && [ "$MANUAL_EXIT" = "false" ]; then
    log_msg "⚠️  偵測到異常: X 已啟動但儀表板未執行"
    
    # 設定冷卻時間
    date +%s > "$COOLDOWN_FILE"
    
    # 取得 DISPLAY
    DISPLAY_NUM=$(pgrep -a Xorg | grep -oP ':\d+' | head -1)
    if [ -z "$DISPLAY_NUM" ]; then
        DISPLAY_NUM=":0"
    fi
    
    log_msg "嘗試在 DISPLAY=$DISPLAY_NUM 啟動儀表板..."
    
    # 設定環境變數
    export DISPLAY="$DISPLAY_NUM"
    export XAUTHORITY="/home/ac/.Xauthority"
    
    # 確定 Python 路徑
    if [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
        PYTHON_CMD="$SCRIPT_DIR/venv/bin/python"
        source "$SCRIPT_DIR/venv/bin/activate" 2>/dev/null || true
    else
        PYTHON_CMD="python3"
    fi
    
    # 偵測 CAN Bus
    CAN_MODE="demo"
    if ip link show can0 2>/dev/null | grep -q "UP"; then
        CAN_MODE="can"
    elif ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -1 | xargs -I{} sh -c 'lsusb 2>/dev/null | grep -qi canable && echo found' | grep -q found; then
        CAN_MODE="can"
    fi
    
    cd "$SCRIPT_DIR"
    
    if [ "$CAN_MODE" = "can" ]; then
        log_msg "啟動 CAN Bus 模式 (datagrab.py)"
        nohup $PYTHON_CMD "$SCRIPT_DIR/datagrab.py" >> "$WATCHDOG_LOG" 2>&1 &
    else
        log_msg "啟動演示模式 (demo_mode.py)"
        echo "2" | nohup $PYTHON_CMD "$SCRIPT_DIR/demo_mode.py" --spotify >> "$WATCHDOG_LOG" 2>&1 &
    fi
    
    sleep 3
    
    # 確認啟動成功
    if pgrep -f "datagrab.py|demo_mode.py" > /dev/null; then
        log_msg "✅ 儀表板已成功啟動"
    else
        log_msg "❌ 儀表板啟動失敗"
    fi
    
elif [ "$X_RUNNING" = "false" ]; then
    # X 未啟動，這是正常情況（開機中或已關閉）
    # 不做任何動作
    :
elif [ "$MANUAL_EXIT" = "true" ]; then
    # 使用者手動退出，不自動重啟
    :
else
    # 一切正常
    :
fi

# 釋放鎖
flock -u 200
