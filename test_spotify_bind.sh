#!/bin/bash
# 測試 Spotify 綁定流程
# 模擬首次使用，需要在儀表板上點擊授權

echo "=== 測試 Spotify 綁定流程 ==="
echo ""
echo "準備測試環境..."

# 備份現有的配置檔和快取（如果存在）


if [ -f ".spotify_cache" ]; then
    echo "備份現有快取..."
    mv .spotify_cache .spotify_cache.backup
fi

echo ""
echo "啟動儀表板（無 Spotify 配置）..."
echo "請在音樂卡片上點擊「綁定 Spotify」按鈕進行授權"
echo ""
echo "測試步驟："
echo "  1. 啟動後應該會看到「Spotify 未連結」的畫面"
echo "  2. 點擊「綁定 Spotify」按鈕"
echo "  3. 會開啟 QR Code 授權視窗"
echo "  4. 掃描 QR Code 完成授權"
echo "  5. 授權成功後應該會自動切換到播放器介面"
echo ""
echo "按 Ctrl+C 結束測試"
echo "=========================================="
echo ""

# 啟動主程式（演示模式）
python main.py

# 測試結束後恢復配置
echo ""
echo "測試結束，恢復環境..."


if [ -f ".spotify_cache.backup" ]; then
    echo "恢復快取..."
    mv .spotify_cache.backup .spotify_cache
fi

echo "環境已恢復"
