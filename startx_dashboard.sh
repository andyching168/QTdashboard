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
#   6. NTP 時間校正
#   7. 偵測 CANable 裝置，決定啟動模式
#   8. Spotify 授權處理
#   9. 啟動儀表板應用程式
# =============================================================================

SCRIPT_DIR="/home/ac/QTdashboard"
cd "$SCRIPT_DIR"

# --- 1. 顯示設定 ---
# 旋轉螢幕 (向右旋轉 90 度)
xrandr --output HDMI-1 --rotate right

# --- 2. 觸控校正 ---
# 針對 wch.cn USB2IIC_CTP_CONTROL 進行 90 度旋轉校正
# 矩陣說明: 0 1 0 -1 0 1 0 0 1 = 順時針旋轉 90 度
xinput set-prop "wch.cn USB2IIC_CTP_CONTROL" --type=float "Coordinate Transformation Matrix" 0 1 0 -1 0 1 0 0 1

# --- 3. 電源管理 (禁止黑屏) ---
xset s off       # 關閉螢幕保護程式
xset -dpms       # 關閉 DPMS (Display Power Management Signaling)
xset s noblank   # 禁止螢幕變黑

# --- 4. 視窗管理器 ---
openbox &

# --- 5. 音訊服務 ---
# PipeWire 由 systemd --user 自動管理，不需要手動啟動
# 確保使用者 dbus 和 pipewire 服務已啟動
systemctl --user start pipewire.socket pipewire-pulse.socket 2>/dev/null || true
sleep 0.5

# --- 6. 啟動 Python 環境 ---
source "$SCRIPT_DIR/venv/bin/activate"
PYTHON_CMD="$SCRIPT_DIR/venv/bin/python"

echo "=============================================="
echo "  Luxgen M7 儀表板 - 自動啟動"
echo "=============================================="
echo ""

# --- 7. NTP 時間校正 ---
echo "🌐 檢查網路連線..."
if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1; then
    echo "✅ 網路已連線"
    
    # NTP 時間校正
    echo "🕐 進行 NTP 時間校正..."
    if command -v timedatectl >/dev/null 2>&1; then
        # 使用 systemd-timesyncd (Raspberry Pi OS / 現代 Linux)
        sudo timedatectl set-ntp true 2>/dev/null || true
        # 強制同步一次
        sudo systemctl restart systemd-timesyncd 2>/dev/null || true
        sleep 2
        echo "   時間: $(date '+%Y-%m-%d %H:%M:%S')"
    elif command -v ntpdate >/dev/null 2>&1; then
        # 使用 ntpdate (傳統方式)
        sudo ntpdate -u pool.ntp.org 2>/dev/null || sudo ntpdate -u time.google.com 2>/dev/null || true
        echo "   時間: $(date '+%Y-%m-%d %H:%M:%S')"
    else
        echo "⚠️  未找到 NTP 工具，跳過時間校正"
    fi
else
    echo "⚠️  無網路連線，跳過 NTP 時間校正"
fi

echo ""

# --- 8. 偵測 CANable 裝置 ---
echo "🔍 掃描 Serial 裝置..."

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

if [ -f "$SPOTIFY_CACHE" ]; then
    echo "✅ Spotify cache 已存在，使用瀏覽器授權"
    SPOTIFY_AUTH_MODE="1"
else
    echo "📱 Spotify cache 不存在，將使用 QR Code 授權"
    SPOTIFY_AUTH_MODE="2"
fi

echo ""

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
