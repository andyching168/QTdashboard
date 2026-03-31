#!/bin/bash
# 自動化設定腳本 - 將配置檔案複製/連結到新位置
# 使用方式: bash setup.sh

set -e

echo "=== QTdashboard 自動化設定 ==="
echo ""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 專案根目錄
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# 檢查是否在正確的目錄
if [ ! -d "$PROJECT_ROOT/spotify" ] || [ ! -d "$PROJECT_ROOT/assets" ]; then
    echo -e "${RED}錯誤: 請在 QTdashboard 根目錄執行此腳本${NC}"
    exit 1
fi

cd "$PROJECT_ROOT"

echo "目前目錄: $(pwd)"
echo ""

# 創建備份目錄
BACKUP_DIR="$PROJECT_ROOT/config_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 備份函數
backup_and_copy() {
    local src="$1"
    local dst="$2"
    local name="$3"
    
    if [ -e "$src" ]; then
        echo -e "${YELLOW}備份並複製: $name${NC}"
        cp -r "$src" "$BACKUP_DIR/"
        if [ -L "$dst" ]; then
            rm "$dst"
        elif [ -e "$dst" ]; then
            mv "$dst" "$dst.bak"
        fi
        cp -r "$src" "$dst"
        echo -e "${GREEN}✓ 完成: $name -> $dst${NC}"
    else
        echo -e "${YELLOW}⚠ 跳過 (不存在): $src${NC}"
    fi
}

echo "1. Spotify 配置..."
backup_and_copy "spotify/spotify_config.json" "spotify/spotify_config.json" "spotify_config.json"
backup_and_copy "spotify/.spotify_cache" "spotify/.spotify_cache" ".spotify_cache"

echo ""
echo "2. MQTT 配置..."
backup_and_copy "mqtt_config.json" "mqtt_config.json" "mqtt_config.json"

echo ""
echo "3. CAN Bus DBC..."
backup_and_copy "luxgen_m7_2009.dbc" "luxgen_m7_2009.dbc" "luxgen_m7_2009.dbc"

echo ""
echo "4. 開機動畫..."
if [ -f "assets/video/Splash_short.mp4" ]; then
    echo -e "${GREEN}✓ Splash_short.mp4 已存在${NC}"
else
    echo -e "${YELLOW}⚠ 缺少 Splash_short.mp4${NC}"
fi

echo ""
echo "5. 確保目錄結構完整..."
[ -d "assets/video" ] || mkdir -p "assets/video"
[ -d "assets/sprites/carSprite" ] || mkdir -p "assets/sprites/carSprite"

echo ""
echo "=== 備份資訊 ==="
echo "備份位置: $BACKUP_DIR"
echo ""

echo "=== 設定完成 ==="
echo ""
echo "現在可以 checkout 到 refactor 分支測試了"
echo "如果有問題，備份在: $BACKUP_DIR"
