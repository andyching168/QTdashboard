#!/bin/bash
# =============================================================================
# Luxgen M7 儀表板 - X11 啟動腳本
# 
# 使用方式:
#   startx /home/ac/QTdashboard/startx_dashboard.sh
#
# 功能:
#   1. 螢幕旋轉 (HDMI-1 向右旋轉 90 度)
#   2. 觸控校正 (USB2IIC_CTP_CONTROL 配合螢幕旋轉)
#   3. 禁用螢幕保護/電源管理 (防止黑屏)
#   4. 啟動 openbox 視窗管理器
#   5. 啟動 PipeWire 音訊服務
#   6. 偵測 CAN Bus 裝置，決定啟動模式
#   7. Spotify 授權處理
#   8. 啟動儀表板應用程式
# =============================================================================

SCRIPT_DIR="/home/ac/QTdashboard"
STARTUP_LOG="/tmp/dashboard_startup.log"
BOOT_FLAG="/tmp/.dashboard_booting"
cd "$SCRIPT_DIR"

# === 記錄啟動時間 ===
echo "" >> "$STARTUP_LOG"
echo "=============================================" >> "$STARTUP_LOG"
echo "$(date): startx_dashboard.sh 開始執行" >> "$STARTUP_LOG"

# 標記開機啟動中，避免 watchdog 重複啟動
touch "$BOOT_FLAG"
trap 'rm -f "$BOOT_FLAG"' EXIT
echo "  PID: $$" >> "$STARTUP_LOG"
echo "  TTY: $(tty 2>/dev/null || echo 'N/A')" >> "$STARTUP_LOG"
echo "  DISPLAY: ${DISPLAY:-未設定}" >> "$STARTUP_LOG"
echo "  USER: $USER" >> "$STARTUP_LOG"
echo "=============================================" >> "$STARTUP_LOG"

# === 錯誤處理函數 ===
log_error() {
    echo "❌ 錯誤: $1"
    echo "$(date): ERROR - $1" >> "$STARTUP_LOG"
}

log_info() {
    echo "$1"
    echo "$(date): $1" >> "$STARTUP_LOG"
}

# === 建立 session 標記，防止關閉後自動重啟 ===
touch /tmp/.dashboard_session_started

# === 效能監控模式檢查 ===
PERF_LOG_FILE="/tmp/dashboard_perf.log"
if [ -f "/tmp/.dashboard_perf_mode" ]; then
    export PERF_MONITOR=1
    echo "📊 效能監控模式已啟用"
    # 重導向效能相關輸出到 log 檔案
    exec > >(tee -a "$PERF_LOG_FILE") 2>&1
    echo ""
    echo "=============================================="
    echo "📊 效能監控 Log 開始 - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=============================================="
fi

# === Qt 渲染優化設定 (Raspberry Pi) ===
# 使用 OpenGL 硬體加速
export QT_QUICK_BACKEND=                # 使用預設 (OpenGL)
export QSG_RENDER_LOOP=threaded         # 多執行緒渲染迴圈 (更流暢)
export QT_QPA_PLATFORM=xcb              # 使用 X11 後端

# Mesa/OpenGL 設定 - 啟用 VSync
export vblank_mode=1                    # 開啟 VSync
export __GL_SYNC_TO_VBLANK=1            # 開啟 NVIDIA VSync

# 其他優化
export QT_X11_NO_MITSHM=0               # 啟用共享記憶體 (提升效能)
export LIBGL_DRI3_DISABLE=1             # 某些情況下可改善旋轉螢幕效能

# --- 1. 顯示設定 ---
# 旋轉螢幕 (向右旋轉 90 度) - 嘗試多種 HDMI 輸出名稱
log_info "設定螢幕旋轉..."
if xrandr --output HDMI-1 --rotate right 2>/dev/null; then
    log_info "✅ 螢幕旋轉成功 (HDMI-1)"
elif xrandr --output HDMI-A-1 --rotate right 2>/dev/null; then
    log_info "✅ 螢幕旋轉成功 (HDMI-A-1)"
elif xrandr --output HDMI-2 --rotate right 2>/dev/null; then
    log_info "✅ 螢幕旋轉成功 (HDMI-2)"
else
    log_error "螢幕旋轉失敗，嘗試列出可用輸出..."
    xrandr --listmonitors >> "$STARTUP_LOG" 2>&1
fi

# --- 檢查 venv 環境 ---
if [ ! -f "$SCRIPT_DIR/venv/bin/python" ]; then
    log_error "venv 環境不存在: $SCRIPT_DIR/venv/bin/python"
    log_info "嘗試使用系統 Python..."
    PYTHON_CMD="python3"
else
    PYTHON_CMD="$SCRIPT_DIR/venv/bin/python"
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# 進度更新函數 (必須在 PYTHON_CMD 設定後定義)
update_progress() {
    local message="$1"
    local detail="$2"
    local progress="$3"
    "$PYTHON_CMD" "$SCRIPT_DIR/startup_progress.py" --update "$message" "$detail" "$progress" 2>/dev/null || true
}

# 關閉進度視窗函數
close_progress() {
    "$PYTHON_CMD" "$SCRIPT_DIR/startup_progress.py" --close 2>/dev/null || true
    sleep 0.3
}

# --- 啟動進度視窗 ---
"$PYTHON_CMD" "$SCRIPT_DIR/startup_progress.py" --serve &
PROGRESS_PID=$!
sleep 0.5  # 等待視窗啟動

# --- 2. 觸控校正 ---
update_progress "📺 設定螢幕顯示" "螢幕已旋轉 90°" 10
# 針對 wch.cn USB2IIC_CTP_CONTROL 進行 90 度旋轉校正
# 矩陣說明: 0 1 0 -1 0 1 0 0 1 = 順時針旋轉 90 度
xinput set-prop "wch.cn USB2IIC_CTP_CONTROL" --type=float "Coordinate Transformation Matrix" 0 1 0 -1 0 1 0 0 1 2>/dev/null || true
update_progress "👆 校正觸控面板" "USB2IIC_CTP_CONTROL" 20

# --- 3. 電源管理 (禁止黑屏) ---
xset s off       # 關閉螢幕保護程式
xset -dpms       # 關閉 DPMS (Display Power Management Signaling)
xset s noblank   # 禁止螢幕變黑
update_progress "🔋 設定電源管理" "已禁用螢幕保護" 30

# --- 4. 視窗管理器 ---
openbox &
OPENBOX_PID=$!
update_progress "🪟 啟動視窗管理器" "openbox" 40

# 等待 openbox 就緒 (最多 5 秒)
log_info "等待 openbox 就緒..."
for i in {1..10}; do
    if pgrep -x "openbox" > /dev/null; then
        log_info "✅ openbox 已就緒 (嘗試 $i)"
        break
    fi
    sleep 0.5
done

# --- 5. 音訊服務 ---
# PipeWire 由 systemd --user 自動管理
log_info "初始化音訊服務..."
# 使用 timeout 避免 systemctl --user 卡住（在 systemd service 環境中可能沒有 user session）
if [ -n "$XDG_RUNTIME_DIR" ]; then
    timeout 5 systemctl --user start pipewire.socket pipewire-pulse.socket 2>/dev/null || log_info "PipeWire 啟動跳過（可能已在執行或不需要）"
else
    log_info "XDG_RUNTIME_DIR 未設定，跳過 PipeWire user service"
fi
sleep 0.3
update_progress "🔊 初始化音訊服務" "PipeWire" 50

# --- 6. Python 環境驗證 ---
update_progress "🐍 載入 Python 環境" "驗證中..." 55

# 驗證 Python 環境可用
log_info "驗證 Python 環境..."
if ! "$PYTHON_CMD" -c "import sys; print(f'Python {sys.version}')" >> "$STARTUP_LOG" 2>&1; then
    log_error "Python 環境驗證失敗！"
    # 嘗試使用系統 Python
    PYTHON_CMD="python3"
    log_info "切換到系統 Python: $PYTHON_CMD"
fi

# 驗證必要模組
log_info "檢查 PyQt6 模組..."
if ! "$PYTHON_CMD" -c "from PyQt6.QtWidgets import QApplication" >> "$STARTUP_LOG" 2>&1; then
    log_error "PyQt6 模組載入失敗！"
fi

update_progress "🐍 載入 Python 環境" "虛擬環境已驗證" 60

log_info "=============================================="
log_info "  Luxgen M7 儀表板 - 自動啟動"
log_info "=============================================="
echo ""

# --- 7. 偵測 CAN Bus 裝置 ---
echo "🔍 掃描 CAN Bus 裝置..."
update_progress "🔌 掃描 CAN Bus 裝置" "等待 CAN 設備就緒..." 60

CAN_INTERFACE=""
CAN_TYPE=""

# 等待 CAN 設備就緒 (最多等待 10 秒)
log_info "等待 CAN 設備就緒..."
CAN_DEVICE_READY=false
for i in {1..20}; do
    # 檢查 SocketCAN 介面（任意名稱）
    if ip -o link show type can 2>/dev/null | grep -q ": "; then
        CAN_DEVICE_READY=true
        log_info "SocketCAN 介面就緒 (嘗試 $i)"
        break
    fi
    # 檢查 USB CANable 設備
    if ls /dev/ttyACM* 2>/dev/null | head -1 > /dev/null; then
        CAN_DEVICE_READY=true
        log_info "USB CAN 設備就緒 (嘗試 $i)"
        break
    fi
    sleep 0.5
done

if [ "$CAN_DEVICE_READY" = "false" ]; then
    log_info "警告: CAN 設備未就緒，將嘗試 demo 模式"
fi

update_progress "🔌 掃描 CAN Bus 裝置" "偵測 SocketCAN / CANable..." 65

# 方法 1: 優先檢查 SocketCAN 介面（不限名稱）
CAN_CANDIDATES=()
while IFS= read -r line; do
    iface=$(echo "$line" | awk -F': ' '{print $2}' | awk '{print $1}' | cut -d'@' -f1)
    if [ -n "$iface" ]; then
        CAN_CANDIDATES+=("$iface")
    fi
done < <(ip -o link show type can 2>/dev/null)

if [ ${#CAN_CANDIDATES[@]} -gt 0 ]; then
    # 先找已啟動的
    for iface in "${CAN_CANDIDATES[@]}"; do
        if ip link show "$iface" 2>/dev/null | grep -q "UP"; then
            CAN_INTERFACE="$iface"
            CAN_TYPE="socketcan"
            echo "✅ 偵測到 SocketCAN 介面: $iface (已啟動)"
            break
        fi
    done

    # 若都未啟動，嘗試逐一啟動
    if [ -z "$CAN_INTERFACE" ]; then
        for iface in "${CAN_CANDIDATES[@]}"; do
            if ip link show "$iface" 2>/dev/null | grep -q "state DOWN"; then
                echo "⚙️  偵測到 SocketCAN 介面 $iface (未啟動)，嘗試設定..."
                sudo ip link set "$iface" type can bitrate 500000 2>/dev/null
                sudo ip link set "$iface" up 2>/dev/null
                if ip link show "$iface" 2>/dev/null | grep -q "UP"; then
                    CAN_INTERFACE="$iface"
                    CAN_TYPE="socketcan"
                    echo "✅ SocketCAN 介面 $iface 已啟動"
                    break
                fi
            fi
        done
    fi
fi

# 方法 2: 如果沒有 SocketCAN，檢查 Serial Port (SLCAN 模式)
if [ -z "$CAN_INTERFACE" ]; then
    CANABLE_PORT=$($PYTHON_CMD -c "
import serial.tools.list_ports
for p in serial.tools.list_ports.comports():
    if 'canable' in p.description.lower():
        print(p.device)
        break
" 2>/dev/null || echo "")

    # 方法 3: 如果 Python 沒找到，嘗試用 dmesg
    if [ -z "$CANABLE_PORT" ]; then
        for dev in /dev/ttyACM* /dev/ttyUSB*; do
            if [ -e "$dev" ]; then
                if dmesg 2>/dev/null | tail -50 | grep -qi "canable\|slcan"; then
                    CANABLE_PORT="$dev"
                    break
                fi
            fi
        done
    fi
    
    if [ -n "$CANABLE_PORT" ]; then
        CAN_INTERFACE="$CANABLE_PORT"
        CAN_TYPE="slcan"
        echo "✅ 偵測到 CANable (SLCAN): $CANABLE_PORT"
    fi
fi

# --- 9. 檢查 Spotify cache 是否存在 ---
SPOTIFY_CACHE="$SCRIPT_DIR/.spotify_cache"
SPOTIFY_AUTH_MODE=""

update_progress "🎵 檢查 Spotify 設定" "檢查授權狀態..." 90
if [ -f "$SPOTIFY_CACHE" ]; then
    echo "✅ Spotify cache 已存在，使用瀏覽器授權"
    SPOTIFY_AUTH_MODE="1"
    update_progress "🎵 檢查 Spotify 設定" "已授權" 95
else
    echo "📱 Spotify cache 不存在，將使用 QR Code 授權"
    SPOTIFY_AUTH_MODE="2"
    update_progress "🎵 檢查 Spotify 設定" "需要 QR Code 授權" 95
fi

echo ""

# --- 關閉進度視窗 ---
close_progress

# --- 10. 根據 CAN Bus 偵測結果決定啟動模式 ---
log_info "準備啟動儀表板應用程式..."

# === 啟動重試機制 ===
MAX_RETRIES=3
RETRY_DELAY=2

launch_dashboard() {
    local mode="$1"
    local retries=0
    local success=false
    
    while [ $retries -lt $MAX_RETRIES ] && [ "$success" = "false" ]; do
        retries=$((retries + 1))
        log_info "啟動嘗試 $retries/$MAX_RETRIES (模式: $mode)"
        
        if [ "$mode" = "can" ]; then
            # CAN Bus 模式
            $PYTHON_CMD "$SCRIPT_DIR/datagrab.py" 2>&1 | tee -a "$STARTUP_LOG"
            PYTHON_EXIT=${PIPESTATUS[0]}
        else
            # Demo 模式
            echo "$SPOTIFY_AUTH_MODE" | $PYTHON_CMD "$SCRIPT_DIR/demo_mode.py" --spotify 2>&1 | tee -a "$STARTUP_LOG"
            PYTHON_EXIT=${PIPESTATUS[0]}
        fi
        
        # 檢查退出碼
        # 0 = 正常退出, 其他 = 錯誤
        # 如果程式正常結束（使用者手動關閉），不重試
        if [ $PYTHON_EXIT -eq 0 ]; then
            success=true
            log_info "儀表板正常結束 (exit: 0)"
        elif [ $retries -lt $MAX_RETRIES ]; then
            log_error "儀表板異常退出 (exit: $PYTHON_EXIT)，${RETRY_DELAY} 秒後重試..."
            sleep $RETRY_DELAY
        else
            log_error "儀表板啟動失敗，已達最大重試次數"
        fi
    done
    
    return $PYTHON_EXIT
}

if [ -n "$CAN_INTERFACE" ]; then
    log_info "=============================================="
    log_info "🚗 偵測到 CAN Bus 裝置"
    log_info "   介面: $CAN_INTERFACE ($CAN_TYPE)"
    log_info "   啟動 CAN Bus 模式 (datagrab.py)"
    log_info "=============================================="
    echo ""
    
    launch_dashboard "can"
    PYTHON_EXIT=$?
else
    log_info "=============================================="
    log_info "🎮 未偵測到 CAN Bus 裝置"
    log_info "   啟動演示模式 (demo_mode.py --spotify)"
    log_info "=============================================="
    echo ""
    
    launch_dashboard "demo"
    PYTHON_EXIT=$?
fi

# 記錄結束狀態
log_info "儀表板程式結束，退出碼: $PYTHON_EXIT"
echo "$(date): startx_dashboard.sh 結束 (exit: $PYTHON_EXIT)" >> "$STARTUP_LOG"
