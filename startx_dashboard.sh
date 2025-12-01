#!/bin/bash
# =============================================================================
# Luxgen M7 儀表板 - X11 啟動腳本
# 
# 使用方式:
#   startx /home/ac/QTdashboard/startx_dashboard.sh
#   startx /home/ac/QTdashboard/startx_dashboard.sh --perf  # 啟用效能監控
#
# 功能:
#   1. 螢幕旋轉 (HDMI-1 向右旋轉 90 度)
#   2. 觸控校正 (USB2IIC_CTP_CONTROL 配合螢幕旋轉)
#   3. 禁用螢幕保護/電源管理 (防止黑屏)
#   4. 啟動 openbox 視窗管理器
#   5. 啟動 PipeWire 音訊服務
#   6. NTP 時間校正
#   7. 偵測 CANable 裝置，決定啟動模式
#   8. Spotify 授權處理
#   9. 啟動儀表板應用程式
# =============================================================================

SCRIPT_DIR="/home/ac/QTdashboard"
cd "$SCRIPT_DIR"

# === 效能監控模式 ===
# 檢查是否有 --perf 參數
PERF_MODE=""
for arg in "$@"; do
    case "$arg" in
        --perf|--performance)
            PERF_MODE="1"
            export PERF_MONITOR=1
            echo "📊 效能監控模式已啟用"
            ;;
    esac
done

# === 垂直同步 (VSync) 設定 ===
# 針對 480x1920 直式螢幕旋轉 90 度使用 (1920x480)
export vblank_mode=1                    # Mesa VSync
export __GL_SYNC_TO_VBLANK=1           # NVIDIA VSync (如果有)
export QT_QPA_EGLFS_FORCE_VSYNC=1      # Qt EGLFS VSync
export QSG_RENDER_LOOP=basic            # Qt 基本渲染迴圈，更穩定

# 進度更新函數
update_progress() {
    local message="$1"
    local detail="$2"
    local progress="$3"
    "$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/startup_progress.py" --update "$message" "$detail" "$progress" 2>/dev/null || true
}

# 關閉進度視窗函數
close_progress() {
    "$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/startup_progress.py" --close 2>/dev/null || true
    sleep 0.3
}

# --- 1. 顯示設定 ---
# 旋轉螢幕 (向右旋轉 90 度)
xrandr --output HDMI-1 --rotate right

# --- 啟動進度視窗 ---
source "$SCRIPT_DIR/venv/bin/activate"
"$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/startup_progress.py" --serve &
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
update_progress "🪟 啟動視窗管理器" "openbox" 35

# --- 4.5 合成器 (VSync 與畫面撕裂防護) ---
# 暫時禁用 picom，因為可能與 GStreamer 視訊播放衝突
# 等影片播放問題解決後再啟用
# if command -v picom >/dev/null 2>&1; then
#     picom -b --backend xrender --vsync 2>/dev/null || true
#     update_progress "🖼️ 啟動合成器" "picom" 40
# else
#     update_progress "🖼️ 合成器" "未安裝 picom" 40
# fi
update_progress "🖼️ 合成器" "已跳過" 40

# --- 5. 音訊服務 ---
# PipeWire 由 systemd --user 自動管理，不需要手動啟動
# 確保使用者 dbus 和 pipewire 服務已啟動
systemctl --user start pipewire.socket pipewire-pulse.socket 2>/dev/null || true
sleep 0.5
update_progress "🔊 初始化音訊服務" "PipeWire" 50

# --- 6. 啟動 Python 環境 ---
PYTHON_CMD="$SCRIPT_DIR/venv/bin/python"
update_progress "🐍 載入 Python 環境" "虛擬環境已啟用" 55

echo "=============================================="
echo "  Luxgen M7 儀表板 - 自動啟動"
echo "=============================================="
echo ""

# --- 7. NTP 時間校正 ---
echo "🌐 檢查網路連線..."
update_progress "🌐 檢查網路連線" "正在偵測..." 60
if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1; then
    echo "✅ 網路已連線"
    update_progress "🌐 檢查網路連線" "網路已連線" 65
    
    # NTP 時間校正
    echo "🕐 進行 NTP 時間校正..."
    update_progress "🕐 時間校正" "NTP 同步中..." 70
    if command -v timedatectl >/dev/null 2>&1; then
        # 使用 systemd-timesyncd (Raspberry Pi OS / 現代 Linux)
        sudo timedatectl set-ntp true 2>/dev/null || true
        # 強制同步一次
        sudo systemctl restart systemd-timesyncd 2>/dev/null || true
        sleep 2
        echo "   時間: $(date '+%Y-%m-%d %H:%M:%S')"
        update_progress "🕐 時間校正" "$(date '+%Y-%m-%d %H:%M:%S')" 75
    elif command -v ntpdate >/dev/null 2>&1; then
        # 使用 ntpdate (傳統方式)
        sudo ntpdate -u pool.ntp.org 2>/dev/null || sudo ntpdate -u time.google.com 2>/dev/null || true
        echo "   時間: $(date '+%Y-%m-%d %H:%M:%S')"
        update_progress "🕐 時間校正" "$(date '+%Y-%m-%d %H:%M:%S')" 75
    else
        echo "⚠️  未找到 NTP 工具，跳過時間校正"
        update_progress "🕐 時間校正" "跳過 (無 NTP 工具)" 75
    fi
else
    echo "⚠️  無網路連線，跳過 NTP 時間校正"
    update_progress "🌐 檢查網路連線" "無網路連線" 75
fi

echo ""

# --- 8. 偵測 CANable 裝置 ---
echo "🔍 掃描 Serial 裝置..."
update_progress "🔌 掃描 CAN Bus 裝置" "偵測 CANable..." 80

CANABLE_PORT=$($PYTHON_CMD -c "
import serial.tools.list_ports
for p in serial.tools.list_ports.comports():
    if 'canable' in p.description.lower():
        print(p.device)
        break
" 2>/dev/null || echo "")

# 方法 2: 如果 Python 沒找到，嘗試用 dmesg
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

# --- 10. 根據 CANable 偵測結果決定啟動模式 ---
if [ -n "$CANABLE_PORT" ]; then
    echo "=============================================="
    echo "🚗 偵測到 CANable: $CANABLE_PORT"
    echo "   啟動 CAN Bus 模式 (datagrab.py)"
    echo "=============================================="
    echo ""
    
    # 使用 datagrab.py (CAN Bus 模式)
    $PYTHON_CMD "$SCRIPT_DIR/datagrab.py"
else
    echo "=============================================="
    echo "🎮 未偵測到 CANable 裝置"
    echo "   啟動演示模式 (demo_mode.py --spotify)"
    echo "=============================================="
    echo ""
    
    # 使用 demo_mode.py 並自動輸入 Spotify 授權選項
    echo "$SPOTIFY_AUTH_MODE" | $PYTHON_CMD "$SCRIPT_DIR/demo_mode.py" --spotify
fi
