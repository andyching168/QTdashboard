#!/bin/bash
# =============================================================================
# Luxgen M7 儀表板自動啟動腳本
# 
# 功能:
#   1. 偵測是否有 CANable 裝置 → 有則執行 datagrab.py (CAN Bus 模式)
#   2. 沒有 CANable → 進入 demo_mode.py (演示模式)
#   3. Spotify 授權自動處理:
#      - 有 cache (.cache-spotify) → 瀏覽器授權 (自動開啟)
#      - 沒有 cache → QR Code 授權 (手機掃描)
#
# 環境支援:
#   - macOS/Linux: conda 環境 (QTdashboard)
#   - Raspberry Pi: venv 環境 (./venv)
#
# 使用方式:
#   chmod +x auto_start.sh
#   ./auto_start.sh
# =============================================================================

set -e

# 切換到腳本所在目錄
cd "$(dirname "$0")"

echo "=============================================="
echo "  Luxgen M7 儀表板 - 自動啟動"
echo "=============================================="
echo ""

# =============================================================================
# 偵測並啟動正確的 Python 環境
# =============================================================================
PYTHON_CMD=""

# 檢查是否在 Raspberry Pi 上
IS_RPI=false
if [ -f /proc/device-tree/model ]; then
    if grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
        IS_RPI=true
    fi
fi

if [ "$IS_RPI" = true ]; then
    echo "📟 偵測到 Raspberry Pi"
    # RPi 使用 venv
    if [ -d "./venv" ] && [ -f "./venv/bin/python" ]; then
        echo "🐍 使用 venv 環境: ./venv"
        PYTHON_CMD="./venv/bin/python"
    else
        echo "⚠️  未找到 venv 環境，使用系統 Python"
        PYTHON_CMD="python3"
    fi
else
    # macOS/Linux 使用 conda
    echo "💻 偵測到 macOS/Linux"
    
    # 檢查是否已在 conda 環境中
    if [ -n "$CONDA_PREFIX" ]; then
        CURRENT_ENV=$(basename "$CONDA_PREFIX")
        if [ "$CURRENT_ENV" = "QTdashboard" ]; then
            echo "🐍 已在 conda 環境: QTdashboard"
            PYTHON_CMD="python"
        else
            echo "⚠️  目前在 conda 環境 '$CURRENT_ENV'，非 QTdashboard"
            echo "   請先執行: conda activate QTdashboard"
            echo "   然後重新執行此腳本"
            exit 1
        fi
    else
        # 嘗試直接使用 conda 環境的 Python
        CONDA_PYTHON=""
        for conda_base in "$HOME/miniconda3" "$HOME/anaconda3" "/opt/miniconda3" "/opt/anaconda3"; do
            if [ -f "$conda_base/envs/QTdashboard/bin/python" ]; then
                CONDA_PYTHON="$conda_base/envs/QTdashboard/bin/python"
                echo "🐍 找到 conda 環境: $conda_base/envs/QTdashboard"
                break
            fi
        done
        
        if [ -n "$CONDA_PYTHON" ]; then
            PYTHON_CMD="$CONDA_PYTHON"
        else
            echo "⚠️  未找到 conda 環境 QTdashboard"
            echo "   請先執行: conda activate QTdashboard"
            echo "   然後重新執行此腳本"
            exit 1
        fi
    fi
fi

echo ""

# =============================================================================
# 檢查網路連線並進行 NTP 時間校正
# =============================================================================
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
    elif command -v sntp >/dev/null 2>&1; then
        # macOS 使用 sntp
        sudo sntp -sS pool.ntp.org 2>/dev/null || true
        echo "   時間: $(date '+%Y-%m-%d %H:%M:%S')"
    else
        echo "⚠️  未找到 NTP 工具，跳過時間校正"
    fi
else
    echo "⚠️  無網路連線，跳過 NTP 時間校正"
fi

echo ""

# =============================================================================
# 偵測 CAN Bus 裝置 (SocketCAN 優先)
# =============================================================================
CAN_INTERFACE=""
CAN_TYPE=""

# === 1. 檢查 SocketCAN 介面 (can0, can1, slcan0 等) ===
echo "🔍 掃描 CAN Bus 裝置..."

if [ "$IS_RPI" = true ] || [ "$(uname)" = "Linux" ]; then
    # 檢查是否有 CAN 類型的網路介面
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
fi

# === 2. 如果沒有 SocketCAN，檢查 Serial Port (SLCAN 模式) ===
if [ -z "$CAN_INTERFACE" ]; then
    # 使用 Python 偵測 (更準確)
    CANABLE_PORT=$($PYTHON_CMD -c "
import serial.tools.list_ports
for p in serial.tools.list_ports.comports():
    if 'canable' in p.description.lower():
        print(p.device)
        break
" 2>/dev/null || echo "")

    # 方法 2: 如果 Python 沒找到，嘗試用 dmesg (Linux/RPi)
    if [ -z "$CANABLE_PORT" ] && [ "$IS_RPI" = true ]; then
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

# =============================================================================
# 檢查 Spotify cache 是否存在
# =============================================================================
SPOTIFY_CACHE=".spotify_cache"
SPOTIFY_AUTH_MODE=""

if [ -f "$SPOTIFY_CACHE" ]; then
    echo "✅ Spotify cache 已存在，使用瀏覽器授權"
    SPOTIFY_AUTH_MODE="1"
else
    echo "📱 Spotify cache 不存在，將使用 QR Code 授權"
    SPOTIFY_AUTH_MODE="2"
fi

echo ""

# =============================================================================
# 根據 CAN Bus 偵測結果決定啟動模式
# =============================================================================
if [ -n "$CAN_INTERFACE" ]; then
    echo "=============================================="
    echo "🚗 偵測到 CAN Bus 裝置"
    echo "   介面: $CAN_INTERFACE ($CAN_TYPE)"
    echo "   啟動 CAN Bus 模式 (datagrab.py)"
    echo "=============================================="
    echo ""
    
    # 使用 datagrab.py (CAN Bus 模式)
    $PYTHON_CMD datagrab.py
    
else
    echo "=============================================="
    echo "🎮 未偵測到 CAN Bus 裝置"
    echo "   啟動演示模式 (demo_mode.py --spotify)"
    echo "=============================================="
    echo ""
    
    # 使用 demo_mode.py 並自動輸入 Spotify 授權選項
    # 傳遞使用者額外參數（例如 --control-data）
    echo "$SPOTIFY_AUTH_MODE" | $PYTHON_CMD demo_mode.py --spotify "$@"
fi
