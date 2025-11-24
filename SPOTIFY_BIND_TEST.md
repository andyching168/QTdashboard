# Spotify 綁定流程測試指南

## 測試目的
測試使用者首次使用時，需要在儀表板上點擊授權按鈕來綁定 Spotify 帳號的完整流程。

## 測試前準備

### 1. 確保有 Spotify 配置檔
複製範例配置檔並填入你的 Spotify API 憑證：

```bash
cp spotify_config.json.example spotify_config.json
```

編輯 `spotify_config.json`，填入：
- `client_id`: 你的 Spotify Client ID
- `client_secret`: 你的 Spotify Client Secret
- `redirect_uri`: 保持為 `http://localhost:8888/callback`（稍後會自動更新）

### 2. 確保沒有授權快取
如果之前已經授權過，需要刪除快取來模擬首次使用：

```bash
rm -f .spotify_cache
```

## 測試步驟

### 方法一：使用測試腳本（推薦）

測試腳本會自動備份並恢復你的配置：

```bash
./test_spotify_bind.sh
```

### 方法二：手動測試

1. **備份現有配置**（如果有）：
   ```bash
   mv spotify_config.json spotify_config.json.backup
   mv .spotify_cache .spotify_cache.backup
   ```

2. **只恢復配置檔**（模擬有配置但未授權的狀態）：
   ```bash
   mv spotify_config.json.backup spotify_config.json
   ```

3. **啟動儀表板**：
   ```bash
   python main.py
   ```

4. **執行授權流程**：
   - 啟動後應該會看到音樂卡片顯示「Spotify 未連結」
   - 點擊「綁定 Spotify」按鈕
   - 會開啟 QR Code 授權視窗
   - 按照視窗指示完成授權

5. **恢復環境**（測試完成後）：
   ```bash
   mv spotify_config.json.backup spotify_config.json
   mv .spotify_cache.backup .spotify_cache
   ```

## 預期結果

### 1. 啟動時（未授權狀態）
- ✅ 音樂卡片顯示「Spotify 未連結」
- ✅ 顯示「綁定 Spotify」按鈕
- ✅ 終端輸出：「未發現授權快取，顯示綁定介面」

### 2. 點擊綁定按鈕後
- ✅ 開啟 QR Code 授權視窗
- ✅ 左側顯示三個步驟的說明（可切換）
- ✅ 右側顯示授權用的 QR Code
- ✅ 顯示當前的 Redirect URI

### 3. 掃描 QR Code 後
- ✅ 手機開啟 Spotify 授權頁面
- ✅ 同意授權後自動回調
- ✅ 視窗顯示「授權成功！正在完成設定...」
- ✅ 視窗自動關閉

### 4. 授權完成後
- ✅ 音樂卡片切換到播放器介面
- ✅ 如果正在播放音樂，會顯示歌曲資訊
- ✅ 專輯封面會非同步載入
- ✅ 終端輸出：「Spotify 授權成功！」

### 5. 下次啟動時
- ✅ 因為已有 `.spotify_cache` 檔案
- ✅ 直接顯示播放器介面，無需重新授權
- ✅ 終端輸出：「發現 Spotify 設定檔和快取，正在初始化...」

## 常見問題

### Q1: 視窗開啟後沒有顯示 QR Code
**A:** 檢查 `spotify_config.json` 是否存在且格式正確。視窗應該會顯示錯誤訊息。

### Q2: 掃描 QR Code 後沒有反應
**A:** 
- 檢查 Spotify Dashboard 中的 Redirect URIs 是否包含視窗中顯示的 URI
- 確認手機和電腦在同一網路
- 檢查防火牆是否阻擋 8888 端口

### Q3: 授權成功但播放器沒有顯示音樂
**A:** 
- 確認 Spotify 應用程式正在播放音樂
- 檢查終端是否有錯誤訊息
- `.spotify_cache` 檔案應該已經被建立

### Q4: 如何重置測試環境
**A:** 刪除快取檔案即可：
```bash
rm -f .spotify_cache
```

## 技術細節

### 授權流程架構

```
Dashboard 啟動
    ↓
check_spotify_config()
    ↓
檢查 spotify_config.json 和 .spotify_cache
    ↓
    ├─ 都存在 → 自動初始化 Spotify → 顯示播放器
    └─ 缺少任一 → 顯示綁定介面
                    ↓
            使用者點擊「綁定 Spotify」
                    ↓
            start_spotify_auth()
                    ↓
            開啟 SpotifyQRAuthDialog
                    ↓
            使用者掃描 QR Code 授權
                    ↓
            on_auth_completed(success)
                    ↓
            切換到播放器介面 + 初始化 Spotify
```

### 相關檔案

- `main.py`: 主程式，包含 Dashboard 類別和 MusicCard 類別
- `spotify_qr_auth.py`: QR Code 授權視窗
- `spotify_auth.py`: Spotify 認證管理器
- `spotify_integration.py`: Spotify 整合邏輯
- `spotify_listener.py`: Spotify 播放狀態監聽器

### 相關方法

- `Dashboard.check_spotify_config()`: 檢查配置並決定顯示哪個介面
- `Dashboard.start_spotify_auth()`: 啟動授權流程
- `Dashboard.on_auth_completed()`: 授權完成回調
- `MusicCard.show_bind_ui()`: 顯示綁定介面
- `MusicCard.show_player_ui()`: 顯示播放器介面
