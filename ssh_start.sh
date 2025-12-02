#!/bin/bash
# =============================================================================
# SSH 遠端啟動儀表板腳本
# 
# 使用方式 (從 SSH 連線執行):
#   ./ssh_start.sh           # 正常啟動
#   ./ssh_start.sh -p        # 效能監控模式 (啟用 PERF_MONITOR)
#   ./ssh_start.sh -w        # 效能監控 + 持續觀察 log
#   ./ssh_start.sh --watch   # 同 -w
#
# 此腳本會在 TTY1 上啟動 X server
# =============================================================================

SCRIPT_DIR="/home/ac/QTdashboard"
PERF_MODE=0
WATCH_MODE=0
LOG_FILE="/tmp/dashboard_perf.log"

# 解析參數
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--perf)
            PERF_MODE=1
            shift
            ;;
        -w|--watch)
            PERF_MODE=1
            WATCH_MODE=1
            shift
            ;;
        -h|--help)
            echo "使用方式: $0 [選項]"
            echo ""
            echo "選項:"
            echo "  -p, --perf   啟用效能監控模式"
            echo "  -w, --watch  效能監控 + 持續觀察 log"
            echo "  -h, --help   顯示此說明"
            exit 0
            ;;
        *)
            echo "未知選項: $1"
            echo "使用 -h 查看說明"
            exit 1
            ;;
    esac
done

echo "=============================================="
echo "  SSH 遠端啟動 - Luxgen M7 儀表板"
if [[ $PERF_MODE -eq 1 ]]; then
    echo "  📊 效能監控模式已啟用"
fi
if [[ $WATCH_MODE -eq 1 ]]; then
    echo "  👁️  持續觀察 log 模式"
fi
echo "=============================================="

# 檢查是否有其他 X server 正在執行
if pgrep -x "Xorg" > /dev/null || pgrep -x "X" > /dev/null; then
    echo "⚠️  X server 已在執行中"
    echo "   如果要重新啟動，請先執行: ./ssh_stop.sh"
    exit 1
fi

echo ""
echo "🚀 正在啟動儀表板..."
echo ""

# 刪除所有標記，允許重新啟動
rm -f /tmp/.dashboard_session_started /tmp/.dashboard_manual_exit /tmp/.dashboard_force_start

# 建立強制啟動標記
touch /tmp/.dashboard_force_start

# 如果啟用效能監控模式，建立環境變數標記檔案
if [[ $PERF_MODE -eq 1 ]]; then
    echo "1" > /tmp/.dashboard_perf_mode
    # 清空舊的 log 檔案
    > "$LOG_FILE"
    echo "📊 效能監控已啟用，log 輸出到: $LOG_FILE"
else
    rm -f /tmp/.dashboard_perf_mode
fi

# 重新啟動 getty@tty1 服務，觸發 autologin -> .bashrc -> startx
sudo systemctl restart getty@tty1

echo "✅ 已觸發啟動，儀表板應該在 HDMI 螢幕上顯示"
echo ""
echo "   查看狀態: pgrep -la 'Xorg|python'"
echo "   停止儀表板: ./ssh_stop.sh"

# 如果是 watch 模式，持續觀察 log
if [[ $WATCH_MODE -eq 1 ]]; then
    echo ""
    echo "=============================================="
    echo "📊 效能監控 Log (Ctrl+C 停止觀察)"
    echo "=============================================="
    echo ""
    
    # 等待 log 檔案產生
    sleep 3
    
    # 持續觀察 log，高亮顯示關鍵字
    tail -f "$LOG_FILE" 2>/dev/null | while read -r line; do
        # 卡頓警告 - 紅色
        if [[ "$line" == *"[JANK]"* ]] || [[ "$line" == *"🔴"* ]]; then
            echo -e "\033[1;31m$line\033[0m"
        # 慢呼叫警告 - 黃色
        elif [[ "$line" == *"[PERF]"* ]] || [[ "$line" == *"⚠️"* ]]; then
            echo -e "\033[1;33m$line\033[0m"
        # 效能報告 - 青色
        elif [[ "$line" == *"效能報告"* ]] || [[ "$line" == *"📊"* ]]; then
            echo -e "\033[1;36m$line\033[0m"
        # GC 相關 - 紫色
        elif [[ "$line" == *"GC"* ]]; then
            echo -e "\033[1;35m$line\033[0m"
        # 一般訊息
        else
            echo "$line"
        fi
    done
fi
