# Spotify Connect 整合設定指南

本專案整合了 Spotify Web API，可即時顯示您正在 Spotify 播放的音樂資訊。

## 功能特點

- 🎵 即時顯示正在播放的歌曲名稱和藝人
- 🖼️ 自動下載並顯示專輯封面
- ⏱️ 同步播放進度條
- 🔄 自動偵測歌曲切換
- 🎨 整合到車機儀表板 UI

## 前置需求

1. **Spotify 帳號**（免費或 Premium 皆可）
2. **Spotify Developer 應用程式**（下方會教您如何建立）
3. **Python 套件**：
   - `spotipy` - Spotify API Python 客戶端
   - `requests` - HTTP 請求
   - `Pillow` - 圖片處理

## 第一步：建立 Spotify Developer 應用程式

### 1. 前往 Spotify Developer Dashboard

訪問：https://developer.spotify.com/dashboard

使用您的 Spotify 帳號登入。

### 2. 建立新應用程式

1. 點擊 **"Create app"** 按鈕
2. 填寫應用程式資訊：
   - **App name**: `QT Dashboard` (或任意名稱)
   - **App description**: `Car dashboard with Spotify integration`
   - **Redirect URI**: `http://localhost:8888/callback`
   - **APIs used**: 勾選 **Web API**
3. 同意 Terms of Service
4. 點擊 **Save**

### 3. 取得 Client ID 和 Client Secret

1. 在應用程式頁面點擊 **Settings**
2. 複製 **Client ID**
3. 點擊 **View client secret**，複製 **Client Secret**

⚠️ **重要**：Client Secret 是敏感資訊，請勿分享給他人或上傳到 Git！

## 第二步：設定專案配置

### 1. 複製配置檔範本

```bash
cd /Users/ac/Documents/GitHub/QTdashboard
cp spotify_config.json.example spotify_config.json
```

### 2. 編輯 `spotify_config.json`

```json
{
  "client_id": "您的 Client ID",
  "client_secret": "您的 Client Secret",
  "redirect_uri": "http://localhost:8888/callback"
}
```

將 `client_id` 和 `client_secret` 替換為您從 Spotify Dashboard 取得的值。

### 3. 將配置檔加入 .gitignore

```bash
echo "spotify_config.json" >> .gitignore
echo ".spotify_cache" >> .gitignore
```

這樣可以防止您的憑證意外上傳到 Git。

## 第三步：安裝 Python 套件

套件已在專案建立時安裝，如需手動安裝：

```bash
conda activate QTdashboard
pip install spotipy requests Pillow
```

## 第四步：測試認證

### 1. 測試 Spotify 認證

有兩種認證方式：

#### 方式 A: 瀏覽器授權（桌機推薦）

```bash
python spotify_auth.py
```

程式會自動開啟瀏覽器：
1. 登入您的 Spotify 帳號（如果尚未登入）
2. 點擊 **Agree** 授權應用程式存取您的 Spotify 資料
3. 瀏覽器會跳轉到 `localhost:8888/callback`（可能顯示無法連線，這是正常的）
4. 認證成功後，終端會顯示您的 Spotify 使用者資訊

#### 方式 B: QR Code 授權（觸控螢幕推薦） 🆕

```bash
python spotify_qr_auth.py
```

程式會顯示全螢幕授權介面：
1. 視窗顯示一個大型 QR Code
2. 使用手機相機或任何 QR 掃描 App 掃描
3. 在手機上登入 Spotify 並授權
4. 授權完成後車機自動繼續

**優點**：
- ✅ 無需在車機螢幕輸入帳號密碼
- ✅ 適合觸控螢幕操作
- ✅ 手機授權更安全方便
- ✅ 支援 1920x480 橫向螢幕

### 2. 測試播放監聽

```bash
python spotify_listener.py
```

**在開始測試前**，請先在 Spotify 應用程式（電腦版、手機版或網頁版）開始播放音樂。

測試程式會：
- 顯示當前播放的歌曲資訊
- 即時更新播放進度
- 當您切換歌曲時自動偵測

按 `Ctrl+C` 停止測試。

## 第五步：整合到儀表板

### 選項 1: 使用 Demo 模式測試（含 Spotify）

```bash
python demo_mode.py --spotify
```

首次使用時會提示選擇授權方式：
- **選項 1**: 瀏覽器授權（桌機推薦）
- **選項 2**: QR Code 授權（觸控螢幕推薦，預設）

此模式會：
- 模擬車輛數據（速度、轉速、油量、水溫）
- 整合真實的 Spotify 播放資訊
- 支援觸控/滑鼠手勢切換卡片
- 自動選擇最適合的授權方式

### 選項 2: 完整系統（CAN Bus + Spotify）

```bash
python datagrab.py --enable-spotify
```

此模式會：
- 讀取真實的 CAN Bus 數據
- 整合真實的 Spotify 播放資訊
- 完整的車機功能

## 使用說明

### 認證流程

首次使用時會要求您授權：

1. 程式自動開啟瀏覽器
2. 登入 Spotify 並授權應用程式
3. 認證成功後會儲存 token 到 `.spotify_cache`
4. 下次使用時會自動載入快取的 token（無需重新授權）

### Token 有效期

- Access Token 有效期為 **1 小時**
- 程式會在 token 過期前 **自動更新**
- 如果超過 token 有效期未使用，需要重新認證

### 重新認證

如需重新認證（例如切換帳號）：

```bash
rm .spotify_cache
python spotify_auth.py
```

## 常見問題

### Q1: 瀏覽器顯示 "This site can't be reached"

**A**: 這是正常的！認證完成後，Spotify 會將您導向 `http://localhost:8888/callback`，但我們沒有在這個埠運行伺服器。只要 URL 包含 `code=` 參數，認證就成功了。

### Q2: 顯示 "No active device found"

**A**: 請確保您在任何設備（電腦、手機、平板）上開啟 Spotify 應用程式並開始播放音樂。免費帳號也支援。

### Q3: 認證失敗 "Invalid client"

**A**: 請檢查：
- Client ID 和 Client Secret 是否正確複製
- Redirect URI 是否完全一致（包括 http://）
- 在 Spotify Dashboard 中是否正確設定了 Redirect URI

### Q4: 圖片無法顯示

**A**: 請確保：
- 已安裝 Pillow 套件：`pip install Pillow`
- 網路連線正常（需要下載專輯封面）
- 檢查終端是否有相關錯誤訊息

### Q5: 免費帳號能用嗎？

**A**: 可以！本整合功能支援 Spotify 免費帳號，但有以下限制：
- 只能讀取播放資訊，無法控制播放
- 需要在其他設備開啟 Spotify 並播放音樂
- 廣告播放時也會顯示廣告資訊

Premium 帳號額外功能：
- 可透過 API 控制播放（播放/暫停/上下首）
- 可切換播放設備
- 可調整音量

## 隱私與安全

### 資料使用

本應用程式：
- ✅ 僅讀取當前播放資訊
- ✅ 所有資料都在本地處理
- ✅ 不會上傳任何資料到第三方伺服器
- ✅ 不會儲存您的 Spotify 帳號密碼

### 權限說明

應用程式請求的權限：

| 權限 | 用途 |
|------|------|
| `user-read-currently-playing` | 讀取正在播放的歌曲 |
| `user-read-playback-state` | 讀取播放狀態（播放/暫停/進度） |
| `user-read-recently-played` | 讀取最近播放（未來功能） |
| `user-modify-playback-state` | 控制播放（Premium 功能） |

### 撤銷權限

如需撤銷應用程式的存取權限：

1. 前往 Spotify 帳號設定：https://www.spotify.com/account/apps/
2. 找到 "QT Dashboard" 應用程式
3. 點擊 **Remove Access**

## 進階設定

### 調整更新頻率

編輯 `demo_mode.py` 或 `datagrab.py`：

```python
# 預設 1 秒更新一次
listener = SpotifyListener(auth, update_interval=1.0)

# 改為 2 秒更新一次（省電）
listener = SpotifyListener(auth, update_interval=2.0)

# 改為 0.5 秒更新一次（更即時）
listener = SpotifyListener(auth, update_interval=0.5)
```

### 自訂專輯封面尺寸

編輯 `main.py` 的 MusicCard：

```python
# 預設 180x180
self.album_art.setFixedSize(180, 180)

# 改為更大尺寸
self.album_art.setFixedSize(240, 240)
```

### 變更 Redirect URI

如果 `localhost:8888` 被其他程式佔用：

1. 在 Spotify Dashboard 新增 Redirect URI，例如：`http://localhost:9999/callback`
2. 修改 `spotify_config.json` 中的 `redirect_uri`
3. 重新認證

## 樹莓派部署注意事項

在樹莓派上使用時：

1. **首次認證建議在桌機完成**
   ```bash
   # 在桌機執行認證
   python spotify_auth.py
   
   # 將認證檔複製到樹莓派
   scp .spotify_cache pi@raspberrypi.local:/home/pi/QTdashboard/
   ```

2. **無頭模式認證**（樹莓派無螢幕）
   ```python
   # 修改 spotify_auth.py
   auth_manager = SpotifyOAuth(
       # ...
       open_browser=False  # 不自動開啟瀏覽器
   )
   # 手動在其他設備開啟認證 URL
   ```

3. **效能優化**
   ```python
   # 降低更新頻率以節省 CPU
   listener = SpotifyListener(auth, update_interval=2.0)
   ```

## 參考資源

- [Spotify Web API 文件](https://developer.spotify.com/documentation/web-api)
- [Spotipy 套件文件](https://spotipy.readthedocs.io/)
- [OAuth 2.0 Authorization Code Flow](https://developer.spotify.com/documentation/web-api/tutorials/code-flow)

## 技術實作參考

本專案參考了 [FreekBes/spotify_web_controller](https://github.com/FreekBes/spotify_web_controller) 的實作方式，使用：

- **OAuth 2.0 Authorization Code Flow** 進行認證
- **Polling 機制**每秒查詢 `/me/player/currently-playing` API
- **Token 快取**避免重複認證
- **自動 token 更新**確保連續運作

## 故障排除

### 啟用詳細日誌

```bash
# 設定環境變數啟用 DEBUG 日誌
export SPOTIPY_LOG_LEVEL=DEBUG
python demo_mode.py --spotify
```

### 查看 API 呼叫

監控 Spotify API 請求：

```bash
# 在程式碼中啟用
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 清除所有快取重新開始

```bash
rm .spotify_cache
rm spotify_config.json
cp spotify_config.json.example spotify_config.json
# 重新填寫配置並認證
```

## 支援

如有問題或建議，請在 GitHub 開 issue 或查閱：
- 專案 README.md
- Spotify API 官方論壇
- Spotipy GitHub Issues

---

**祝您使用愉快！🚗🎵**
