#!/bin/bash
# 設定腳本 - 在 checkout 重構分支後執行
# 將配置檔案複製/連結到新位置

set -e

echo "=== QTdashboard 設定腳本 ==="
echo ""

# 顏色輸出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 檢查是否在正確的目錄
if [ ! -d "spotify" ] || [ ! -d "assets" ]; then
    echo -e "${RED}錯誤: 請在 QTdashboard 根目錄執行此腳本${NC}"
    exit 1
fi

# 備份 existing 檔案的函數
backup_if_exists() {
    if [ -e "$1" ]; then
        if [ ! -L "$1" ]; then  # 不是符號連結
            echo -e "${YELLOW}備份現有檔案: $1 -> $1.bak${NC}"
            cp -r "$1" "$1.bak"
        fi
    fi
}

# 創建目錄的函數
ensure_dir() {
    if [ ! -d "$1" ]; then
        mkdir -p "$1"
        echo -e "${GREEN}創建目錄: $1${NC}"
    fi
}

echo "1. 檢查 Spotify 配置..."
if [ -f "spotify/spotify_config.json" ]; then
    echo -e "${GREEN}✓ spotify/spotify_config.json 存在${NC}"
else
    echo -e "${YELLOW}⚠ spotify/spotify_config.json 不存在${NC}"
fi

if [ -d "spotify/.spotify_cache" ]; then
    echo -e "${GREEN}✓ spotify/.spotify_cache 存在${NC}"
else
    echo -e "${YELLOW}⚠ spotify/.spotify_cache 不存在 (尚未授權過)${NC}"
fi

echo ""
echo "2. 檢查 MQTT 配置..."
if [ -f "mqtt_config.json" ]; then
    echo -e "${GREEN}✓ mqtt_config.json 存在${NC}"
else
    echo -e "${YELLOW}⚠ mqtt_config.json 不存在${NC}"
fi

echo ""
echo "3. 檢查 CAN Bus 配置..."
if [ -f "luxgen_m7_2009.dbc" ]; then
    echo -e "${GREEN}✓ luxgen_m7_2009.dbc 存在${NC}"
else
    echo -e "${YELLOW}⚠ luxgen_m7_2009.dbc 不存在${NC}"
fi

echo ""
echo "4. 檢查 assets 結構..."
if [ -d "assets/video" ]; then
    echo -e "${GREEN}✓ assets/video/ 目錄存在${NC}"
else
    ensure_dir "assets/video"
fi

if [ -d "assets/sprites/carSprite" ]; then
    echo -e "${GREEN}✓ assets/sprites/carSprite/ 目錄存在${NC}"
else
    echo -e "${YELLOW}⚠ assets/sprites/carSprite/ 目錄不存在${NC}"
fi

echo ""
echo "5. 嘗試從 archive 恢復可能需要的檔案..."
if [ -d "archive" ]; then
    if [ -f "archive/main.py.gps_thread" ] && [ ! -f "archive/main.py.gps_thread" ]; then
        # 不自動恢復，保持乾淨
        echo -e "${YELLOW}⚠ archive/main.py.gps_thread 存在 (保留在 archive)${NC}"
    fi
fi

echo ""
echo "=== 設定完成 ==="
echo ""
echo "如果需要從備份恢復配置，請手動執行:"
echo "  cp spotify_config.json.bak spotify/spotify_config.json"
echo "  cp mqtt_config.json.bak mqtt_config.json"
echo ""
echo "對於樹莓派部署，確保以下檔案存在:"
echo "  - spotify/spotify_config.json (Spotify API 憑證)"
echo "  - mqtt_config.json (MQTT 設定，可選)"
echo "  - assets/video/Splash_short.mp4 (開機動畫，可選)"
echo ""
