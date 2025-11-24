#!/bin/bash
# Spotify 整合測試腳本

echo "=========================================="
echo "Spotify Connect 整合測試"
echo "=========================================="
echo ""

# 檢查 Python 環境
echo "1. 檢查 Python 環境..."
which python
python --version
echo ""

# 檢查套件安裝
echo "2. 檢查必要套件..."
python -c "import spotipy; print(f'✅ spotipy {spotipy.__version__}')" 2>/dev/null || echo "❌ spotipy 未安裝"
python -c "import requests; print(f'✅ requests {requests.__version__}')" 2>/dev/null || echo "❌ requests 未安裝"
python -c "import PIL; print(f'✅ Pillow {PIL.__version__}')" 2>/dev/null || echo "❌ Pillow 未安裝"
python -c "import PyQt6; print(f'✅ PyQt6 已安裝')" 2>/dev/null || echo "❌ PyQt6 未安裝"
echo ""

# 檢查配置檔
echo "3. 檢查配置檔..."
if [ -f "spotify_config.json" ]; then
    echo "✅ spotify_config.json 存在"
    # 檢查是否為範例檔（包含 YOUR_SPOTIFY_CLIENT_ID）
    if grep -q "YOUR_SPOTIFY_CLIENT_ID" spotify_config.json; then
        echo "⚠️  警告: spotify_config.json 尚未設定"
        echo "   請編輯檔案並填入您的 Spotify API 憑證"
    else
        echo "✅ spotify_config.json 已設定"
    fi
else
    echo "❌ spotify_config.json 不存在"
    echo "   請執行: cp spotify_config.json.example spotify_config.json"
fi
echo ""

# 提供測試選項
echo "=========================================="
echo "測試選項:"
echo "=========================================="
echo ""
echo "1) 測試 Spotify 認證"
echo "2) 測試 Spotify 監聽器"
echo "3) 測試演示模式 (無 Spotify)"
echo "4) 測試演示模式 (含 Spotify)"
echo "5) 退出"
echo ""
read -p "請選擇測試項目 (1-5): " choice

case $choice in
    1)
        echo ""
        echo "執行 Spotify 認證測試..."
        echo "瀏覽器將自動開啟進行授權"
        python spotify_auth.py
        ;;
    2)
        echo ""
        echo "執行 Spotify 監聽器測試..."
        echo "請先在 Spotify 開始播放音樂"
        echo "按 Ctrl+C 停止測試"
        python spotify_listener.py
        ;;
    3)
        echo ""
        echo "啟動演示模式（模擬音樂）..."
        python demo_mode.py
        ;;
    4)
        echo ""
        echo "啟動演示模式（Spotify 整合）..."
        echo "請先在 Spotify 開始播放音樂"
        python demo_mode.py --spotify
        ;;
    5)
        echo "退出測試"
        exit 0
        ;;
    *)
        echo "無效的選擇"
        exit 1
        ;;
esac
