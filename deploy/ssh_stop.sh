#!/bin/bash
# =============================================================================
# SSH 遠端停止儀表板腳本
# =============================================================================

PERF_LOG_FILE="/tmp/dashboard_perf.log"

echo "🛑 停止儀表板..."

# 停止 X server
sudo pkill -9 Xorg 2>/dev/null

# 停止 Python 程式
pkill -9 -f "demo_mode.py|datagrab.py" 2>/dev/null

sleep 1

if pgrep -x "Xorg" > /dev/null; then
    echo "⚠️  X server 仍在執行"
else
    echo "✅ 儀表板已停止"
fi

# 如果有效能監控 log，顯示摘要
if [ -f "/tmp/.dashboard_perf_mode" ]; then
    echo ""
    echo "=============================================="
    echo "📊 效能監控摘要"
    echo "=============================================="
    
    if [ -f "$PERF_LOG_FILE" ]; then
        JANK_COUNT=$(grep -c "\[JANK\]" "$PERF_LOG_FILE" 2>/dev/null || echo "0")
        SLOW_COUNT=$(grep -c "慢呼叫" "$PERF_LOG_FILE" 2>/dev/null || echo "0")
        
        echo "🔴 卡頓次數: $JANK_COUNT"
        echo "⚠️  慢呼叫次數: $SLOW_COUNT"
        echo ""
        echo "📄 完整 log: $PERF_LOG_FILE"
        echo "   查看: cat $PERF_LOG_FILE"
        echo "   搜尋卡頓: grep JANK $PERF_LOG_FILE"
        
        # 顯示最後幾個卡頓
        if [ "$JANK_COUNT" -gt 0 ]; then
            echo ""
            echo "最後 5 次卡頓:"
            grep "\[JANK\]" "$PERF_LOG_FILE" 2>/dev/null | tail -5
        fi
    else
        echo "⚠️  未找到 log 檔案"
    fi
    
    # 清理效能監控標記
    rm -f /tmp/.dashboard_perf_mode
    echo ""
fi
