#!/bin/bash
# =============================================================================
# 儀表板開機問題診斷腳本
# 
# 使用方式:
#   ./diagnose_boot.sh
#
# 當儀表板卡在黑畫面時，使用 SSH 連入執行此腳本
# =============================================================================

echo "=============================================="
echo "  儀表板開機診斷"
echo "  $(date)"
echo "=============================================="
echo ""

# 1. 系統運行時間
echo "📊 系統運行時間:"
uptime
echo ""

# 2. X Server 狀態
echo "🖥️  X Server 狀態:"
if pgrep -x "Xorg" > /dev/null || pgrep -x "X" > /dev/null; then
    echo "   ✅ X Server 正在執行"
    pgrep -la "Xorg\|^X$"
else
    echo "   ❌ X Server 未執行"
fi
echo ""

# 3. Python 程式狀態
echo "🐍 Python 程式狀態:"
if pgrep -f "datagrab.py\|demo_mode.py\|main.py" > /dev/null; then
    echo "   ✅ 儀表板程式正在執行"
    pgrep -la "datagrab.py\|demo_mode.py\|main.py"
else
    echo "   ❌ 儀表板程式未執行"
fi
echo ""

# 4. openbox 狀態
echo "🪟 視窗管理器狀態:"
if pgrep -x "openbox" > /dev/null; then
    echo "   ✅ openbox 正在執行"
else
    echo "   ❌ openbox 未執行"
fi
echo ""

# 5. GPU/DRM 狀態
echo "🎮 GPU/顯示狀態:"
echo "   DRI 裝置:"
ls -la /dev/dri/ 2>/dev/null || echo "   ❌ /dev/dri 不存在"
echo ""
echo "   DRM 連接器:"
ls /sys/class/drm/ 2>/dev/null | grep -E "card.*-" || echo "   ❌ 未找到連接器"
echo ""

# 6. 啟動日誌
echo "📋 啟動日誌 (/tmp/dashboard_boot.log):"
if [ -f /tmp/dashboard_boot.log ]; then
    echo "--- 最後 20 行 ---"
    tail -20 /tmp/dashboard_boot.log
else
    echo "   ❌ 日誌檔案不存在"
fi
echo ""

echo "📋 startx 日誌 (/tmp/dashboard_startup.log):"
if [ -f /tmp/dashboard_startup.log ]; then
    echo "--- 最後 30 行 ---"
    tail -30 /tmp/dashboard_startup.log
else
    echo "   ❌ 日誌檔案不存在"
fi
echo ""

# 7. Session 標記狀態
echo "🏷️  Session 標記狀態:"
[ -f /tmp/.dashboard_session_started ] && echo "   ✅ .dashboard_session_started 存在" || echo "   ❌ .dashboard_session_started 不存在"
[ -f /tmp/.dashboard_force_start ] && echo "   ✅ .dashboard_force_start 存在" || echo "   ❌ .dashboard_force_start 不存在"
[ -f /tmp/.dashboard_manual_exit ] && echo "   ✅ .dashboard_manual_exit 存在" || echo "   ❌ .dashboard_manual_exit 不存在"
echo ""

# 8. 系統日誌
echo "📋 系統日誌 (最近的 getty@tty1 訊息):"
journalctl -u getty@tty1 --no-pager -n 10 2>/dev/null || echo "   無法讀取"
echo ""

# 9. 建議操作
echo "=============================================="
echo "  建議操作"
echo "=============================================="
echo ""

if pgrep -x "Xorg" > /dev/null && ! pgrep -f "datagrab.py\|demo_mode.py" > /dev/null; then
    echo "⚠️  X Server 已啟動但儀表板程式未執行"
    echo "   可能原因:"
    echo "   1. startx_dashboard.sh 啟動失敗"
    echo "   2. Python 程式發生錯誤"
    echo ""
    echo "   建議: 先停止後重啟"
    echo "   ./ssh_stop.sh && sleep 2 && ./ssh_start.sh"
elif ! pgrep -x "Xorg" > /dev/null; then
    echo "❌ X Server 未啟動"
    echo "   可能原因:"
    echo "   1. GPU 未就緒"
    echo "   2. startx 指令失敗"
    echo ""
    echo "   建議: 直接啟動"
    echo "   ./ssh_start.sh"
else
    echo "✅ 儀表板看起來正常運行中"
fi
echo ""
