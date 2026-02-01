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
cd "$SCRIPT_DIR"

# === 記錄啟動時間 ===
echo "" >> "$STARTUP_LOG"
echo "=============================================" >> "$STARTUP_LOG"
echo "$(date): startx_dashboard.sh 開始執行" >> "$STARTUP_LOG"
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

# --- 7. 啟動儀表板 ---
log_info "=============================================="
log_info "🚀 啟動 Luxgen M7 儀表板"
log_info "   由 datagrab.py 內部處理硬體檢測與重試..."
log_info "=============================================="

# 關閉 shell 層級的進度視窗（datagrab.py 會自己開一個）
close_progress

# 啟動應用程式
# 由 datagrab.py 內部處理：
# 1. 顯示新的硬體檢測進度視窗
# 2. 持續重試 CAN/GPS/GPIO
# 3. 失敗時顯示 "--"
"$PYTHON_CMD" "$SCRIPT_DIR/datagrab.py" 2>&1 | tee -a "$STARTUP_LOG"
PYTHON_EXIT=${PIPESTATUS[0]}

# 記錄結束狀態
log_info "儀表板程式結束，退出碼: $PYTHON_EXIT"
echo "$(date): startx_dashboard.sh 結束 (exit: $PYTHON_EXIT)" >> "$STARTUP_LOG"
