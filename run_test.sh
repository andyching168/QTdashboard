#!/bin/bash
# 快速測試腳本 - 自動設定虛擬環境並執行

echo "========================================"
echo "Luxgen M7 儀表板測試環境"
echo "========================================"
echo ""

# 檢查作業系統
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macOS"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="Linux"
else
    OS="Unknown"
fi

echo "偵測到作業系統: $OS"
echo ""

# 選項選單
echo "請選擇測試模式:"
echo "  1) 演示模式 - 自動模擬車輛行駛 (推薦)"
echo "  2) 使用虛擬 Serial Port"
echo "  3) 連接實際硬體"
echo "  4) 僅測試前端介面 (鍵盤控制)"
echo ""
read -p "請輸入選項 [1-4]: " choice

case $choice in
    1)
        echo ""
        echo "=== 啟動演示模式 ==="
        echo ""
        echo "此模式會自動模擬車輛行駛狀態"
        echo "無需任何硬體或虛擬設備"
        echo ""
        python demo_mode.py
        ;;
    
    2)
        echo ""
        echo "=== 啟動虛擬 Serial Port 模式 ==="
        echo ""
        echo "步驟 1: 在新終端執行以下命令建立虛擬 port 對:"
        echo "  socat -d -d pty,raw,echo=0 pty,raw,echo=0"
        echo ""
        echo "步驟 2: 記下顯示的兩個 port 路徑"
        echo ""
        read -p "請輸入模擬器要使用的 port (例如 /dev/ttys002): " sim_port
        
        echo ""
        echo "在新終端執行模擬器:"
        echo "  python simple_simulator.py $sim_port"
        echo ""
        echo "按 Enter 繼續執行主程式 (請選擇另一個 port)..."
        read
        
        python datagrab.py
        ;;
    
    3)
        echo ""
        echo "=== 連接實際硬體模式 ==="
        echo ""
        python datagrab.py
        ;;
    
    4)
        echo ""
        echo "=== 僅測試前端介面 ==="
        echo ""
        python main.py
        ;;
    
    *)
        echo "無效的選項"
        exit 1
        ;;
esac

echo ""
echo "程式已結束"
