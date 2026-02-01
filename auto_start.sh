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
# 啟動儀表板
# =============================================================================
# 由 datagrab.py 內部處理硬體檢測與重試機制
# 真實環境（RPi）：會顯示硬體檢測進度，成功後啟動，失敗顯示 "--"
# 開發環境：直接啟動
echo "=============================================="
echo "🚀 啟動 Luxgen M7 儀表板"
echo "   由 datagrab.py 處理硬體初始化..."
echo "=============================================="
echo ""

# 使用 datagrab.py (CAN Bus 模式)
# 所有參數都會傳遞給 Python 程式
$PYTHON_CMD datagrab.py "$@"
