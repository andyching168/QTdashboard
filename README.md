# Luxgen M7 數位儀表板系統

## 功能說明

這是一個針對 Luxgen 7 MPV 的數位儀表板系統，整合了 CAN Bus 監聽、OBD-II 診斷功能、Spotify 音樂播放器、MQTT 導航資訊、WiFi 管理、速限顯示，以及車輛方向燈指示，並透過 PyQt6 提供現代化的儀表板顯示介面。

### 核心功能

#### 1. 車輛數據顯示
- **轉速**: 透過 OBD-II 讀取 (PID 0x0C)，使用 EMA 平滑演算法，20Hz 查詢頻率
- **水箱溫度**: 透過 OBD-II 讀取 (PID 0x05)
- **速度**: 讀取 CAN Bus 上的 `SPEED_FL` 訊號 (ID 0x38A / 906)
- **油量**: 讀取 CAN Bus 上的 `FUEL` 訊號 (ID 0x335 / 821)
- **檔位**: 解析 CAN Bus 上的 `ENGINE_RPM1` 訊號中的變速箱模式 (ID 0x340 / 832)
- **渦輪增壓**: 顯示進氣歧管壓力 (bar)，正壓時紅色顯示（熱血模式）
- **電瓶電壓**: 即時監控電瓶狀態

#### 2. 速限顯示系統
- **國道速限查詢**: 根據 GPS 座標和行駛方向顯示速限
- **雙向速限顯示**: 當方向不明時，顯示「N:XX / S:XX」格式
- **超速閃爍警示**: 超速 10 km/h 以上時速限標籤閃爍
- **GPS 狀態整合**:
  - 綠色：內部 GPS 定位成功
  - 黃色：MQTT 外部 GPS（即時）
  - 灰色：MQTT 外部 GPS（數據過時）
  - 紅色：無 GPS 裝置
- **自動暂停**: GPS 不可靠時自動停止查詢

#### 3. 方向燈指示系統
- **85 BPM 閃爍頻率**: 符合原廠規格 (週期 0.706 秒)
- **漸層動畫效果**:
  - 亮起時：瞬間全亮
  - 熄滅時：從中央向邊緣漸暗消失
- **頂部狀態欄**: 50px 高度，左右兩側各佔 1/4 螢幕寬度 (480px)
- **CAN Bus 整合**: 接收左轉、右轉、雙閃訊號
- **執行緒安全**: 透過 Qt Signal/Slot 機制確保多執行緒環境下的安全性

#### 4. Spotify 音樂整合
- **QR Code 授權**: 掃描 QR Code 即可完成 Spotify 帳號綁定
- **即時播放資訊**: 顯示歌曲名稱、演出者、專輯封面
- **跑馬燈效果**: 過長的歌曲名稱自動滾動顯示
- **播放進度顯示**: 即時更新播放進度條和時間
- **非同步專輯封面載入**: 背景執行緒載入圖片，不阻塞 UI
- **自動重新連線**: 偵測斷線並自動重新建立連線

#### 5. MQTT 導航整合
- **即時導航資訊**: 接收來自手機的 Google Maps 導航資料
- **方向圖標顯示**: 顯示下一個轉彎的方向圖標 (Base64 PNG)
- **轉彎距離**: 顯示距離下一個轉彎的距離
- **預計到達時間**: 顯示 ETA 和總剩餘時間
- **外部 GPS 注入**: 當內部 GPS 未定位時，使用 MQTT GPS 作為備援

#### 6. 里程統計
- **總里程 (ODO)**: 持久化儲存，自動累積
- **單次里程 (Trip1/Trip2)**: 兩組可獨立重置的里程計
- **資料持久化**: 里程資料自動儲存至 `mileage_data.json`

#### 7. 下拉控制面板
從螢幕頂部下滑開啟控制面板，提供快速設定：

| 按鈕 | 功能 |
|------|------|
| WiFi | 開啟 WiFi 管理器，掃描並連接無線網路 |
| 亮度 | 軟體亮度調節：100% → 75% → 50% 循環 |
| 校正 | 時間校正（需網路連線）|
| 更新 | 自動更新：選擇分支後執行 git pull 並重啟 |
| 電源 | 電源選項：程式重啟 / 系統重啟 / 關機 |
| 設定 | 開啟 MQTT 設定 QR Code |

#### 8. 車門狀態顯示
- **圖形化顯示**: 俯視車輛圖，顯示各門開關狀態
- **支援車門**: 前左/前右/後左/後右門 + 油箱蓋
- **自動切換**: 開門時自動切換到車門狀態卡片

## 系統需求

### 硬體需求
- **顯示螢幕**: 1920x480 解析度 (針對此規格優化)
- **CAN Bus 轉接器**: CANable 或其他支援 slcan 協定的 CAN-USB 轉接器
- **車輛介面**: 連接到 Luxgen M7 的 OBD-II 接口
- **運算平台**:
  - Raspberry Pi 4/5 (推薦)
  - 或任何支援 PyQt6 的 Linux/macOS 系統

### 軟體需求
- Python 3.8 或更高版本
- PyQt6 6.10.0+
- 完整相依套件列表見 `requirements.txt`

## 安裝步驟

### 1. 複製專案

```bash
git clone https://github.com/andyching168/QTdashboard.git
cd QTdashboard
```

### 2. 安裝 Python 相依套件

```bash
pip install -r requirements.txt
```

### 3. Spotify 設定 (選用)

如需使用 Spotify 功能，請參考 [Spotify 設定指南](docs/setup/SPOTIFY_SETUP.md) 或 [QR Code 授權指南](docs/features/QR_AUTH_GUIDE.md)。

```bash
cp spotify_config.json.example spotify_config.json
# 編輯 spotify_config.json，填入 Client ID 和 Client Secret
```

### 4. Raspberry Pi 免密碼權限設定

在 Raspberry Pi 上執行一次，允許電源控制和 NTP 同步無需密碼：

```bash
sudo bash deploy/setup_sudoers.sh
```

## 使用方法

### 方式 1: 直接啟動 (推薦)

```bash
python main.py
```

會自動偵測 CAN Bus 裝置：
- 有 CANable → 使用實車模式
- 無 CANable → 使用演示模式

### 方式 2: 手動指定模式

```bash
# 實車模式（需有 CANable 裝置）
python main.py

# 演示模式（模擬數據，無需硬體）
python main.py --mode demo
```

### 方式 3: 自動啟動腳本

```bash
./deploy/auto_start.sh
```

腳本會自動：
1. 偵測 Python 環境 (conda / venv)
2. 檢查網路連線並進行 NTP 時間同步
3. 偵測 CANable 裝置並選擇模式
4. 處理 Spotify 認證

## 專案結構

```
QTdashboard/
├── main.py                    # 主程式入口
├── ui/                       # UI 模組
│   ├── control_panel.py      # 下拉控制面板
│   ├── trip_card.py          # 里程/Trip 卡片
│   ├── music_card.py         # Spotify 音樂卡片
│   ├── navigation_card.py    # MQTT 導航卡片
│   ├── door_card.py          # 車門狀態卡片
│   ├── gauge_card.py         # 四宮格儀表卡片
│   ├── analog_gauge.py       # 類比錶盤元件
│   ├── splash_screen.py      # 啟動畫面
│   ├── scalable_window.py    # 可縮放視窗（開發環境）
│   └── threads.py            # GPS/Radar 監控執行緒
├── core/                     # 核心工具模組
│   ├── shutdown_monitor.py   # 電源監控
│   ├── max_value_logger.py   # 最大值日誌記錄器
│   └── utils.py              # 工具函數
├── spotify/                  # Spotify 整合
│   ├── spotify_integration.py
│   ├── spotify_auth.py
│   ├── spotify_qr_auth.py
│   └── spotify_listener.py
├── navigation/               # 導航相關模組
│   └── speed_limit.py        # 速限查詢模組
├── vehicle/                  # 車輛 CAN Bus 模組
│   ├── datagrab.py           # CAN Bus 和 OBD-II 資料擷取
│   └── demo_mode.py          # 演示模式
├── hardware/                # 硬體相關
│   └── gpio_buttons.py       # GPIO 按鈕處理
├── deploy/                   # 部署腳本
│   ├── auto_start.sh
│   └── setup_sudoers.sh
├── docs/                    # 文件
│   ├── setup/               # 設定指南
│   ├── features/            # 功能說明
│   └── development/         # 開發文件
├── tests/                  # 測試檔案
│   └── test_*.py           # 各模組測試
├── assets/                  # 靜態資源
│   ├── sprites/             # 車輛精靈圖
│   ├── video/               # 啟動影片
│   └── docs/                # 資料檔案
│       ├── 國道交通標誌位.csv    # 速限標誌位置
│       └── 國道速限資訊整理.csv  # 速限規則
└── requirements.txt
```

## Raspberry Pi 部署

### 快速設定

```bash
# 1. 複製專案
git clone https://github.com/andyching168/QTdashboard.git
cd QTdashboard

# 2. 建立虛擬環境
python3 -m venv venv
source venv/bin/activate

# 3. 安裝相依套件
pip install -r requirements.txt

# 4. 設定免密碼權限
sudo bash deploy/setup_sudoers.sh

# 5. 測試執行
./deploy/auto_start.sh
```

### 開機自動啟動

編輯 `~/.config/lxsession/LXDE-pi/autostart`，加入：

```
@bash /home/pi/QTdashboard/deploy/auto_start.sh
```

### 全螢幕設定

詳見 [RPI_FULLSCREEN_NOTES.md](docs/setup/RPI_FULLSCREEN_NOTES.md)

## 設定檔說明

### spotify_config.json

```json
{
    "client_id": "your_spotify_client_id",
    "client_secret": "your_spotify_client_secret",
    "redirect_uri": "http://localhost:8888/callback"
}
```

### mqtt_config.json

```json
{
    "broker": "your_mqtt_broker_address",
    "port": 1883,
    "username": "optional_username",
    "password": "optional_password",
    "topic": "navigation/info"
}
```

## 技術細節

### 多執行緒架構

```
主執行緒 (PyQt6 GUI)
├── CAN Bus 接收執行緒
├── OBD-II 查詢執行緒
├── GPS 監控執行緒
├── Radar 監控執行緒
├── Spotify 監聽執行緒
├── MQTT 接收執行緒
└── 動畫更新執行緒 (60 FPS)
```

所有背景執行緒透過 **Qt Signal/Slot** 機制與 UI 溝通，確保執行緒安全。

### 效能指標

| 項目 | 頻率 |
|------|------|
| GUI 更新 | 10 Hz |
| 動畫幀率 | 60 FPS |
| Spotify 輪詢 | 1 Hz |
| CAN Bus 接收 | 即時 |
| OBD-II 查詢 | 20 Hz |
| 速限查詢 | 每 5 秒 (僅 GPS 可靠時) |

## 除錯與日誌

### 查看即時日誌

```bash
tail -f qtdashboard.log
```

### 執行測試

```bash
# 速限查詢測試
python tests/test_speed_limit.py

# 方向燈測試
python tests/test_turn_signals.py
```

### 常見問題

#### CAN Bus 相關

**問題**: 找不到 CANable 裝置
```bash
# 檢查 USB 裝置
ls -l /dev/ttyACM* /dev/ttyUSB*

# 檢查裝置描述
python -c "import serial.tools.list_ports; print([(p.device, p.description) for p in serial.tools.list_ports.comports()])"
```

**問題**: 權限不足
```bash
sudo usermod -a -G dialout $USER
# 登出後重新登入
```

#### Spotify 相關

**問題**: QR Code 掃描後無反應
- 確認 `spotify_config.json` 的 Redirect URI 為 `http://localhost:8888/callback`
- 確認防火牆未阻擋 Port 8888

**問題**: Token 過期
```bash
# 刪除快取重新授權
rm .spotify_cache
```

## 變更記錄

### v2.1 (2026-04) - 速限顯示功能
- **速限查詢系統**: 國道速限即時查詢
- **雙向速限顯示**: 「N:XX / S:XX」格式
- **超速閃爍警示**: 超速 10+ km/h 閃爍
- **GPS 備援機制**: MQTT 外部 GPS 注入
- **效能優化**: 速限查詢每 5 秒一次 + CSV 快取

### v2.0 (2026-04) - 架構重構版
- **架構重構**: 從 12,000 行單一檔案重構為模組化結構
- **可維護性**: UI 元件拆分至 `ui/` 目錄，核心功能拆分至 `core/`
- **協作友善**: 新人不再需要面對 12K 行怪物
- **新增「時間校正」功能
- **修正更新功能**: 可選擇分支
- **修正重啟功能**: 正確偵測入口點
- **修正關機功能**: 正確關閉程式

### v1.5 (2025-12)
- 新增下拉控制面板（WiFi/亮度/更新/電源/設定）
- 新增軟體亮度控制（100%/75%/50%）
- 新增自動更新功能（git pull + 重啟）
- 新增電源選單（程式重啟/系統重啟/關機）
- 新增 MQTT 設定 QR Code
- 新增 `auto_start.sh` 自動啟動腳本
- 新增 `setup_sudoers.sh` 免密碼權限設定
- 渦輪正壓時紅色顯示（熱血模式）
- CANable 自動偵測
- NTP 時間自動同步

### v1.4 (2025-11)
- 新增 MQTT 導航資訊整合
- 新增 WiFi 管理器
- 新增里程統計（ODO/Trip1/Trip2）
- 新增車門狀態顯示
- 新增四宮格儀表詳細視圖
- 新增跑馬燈文字效果
- 改善可縮放視窗（開發環境）

### v1.3 (2025-11)
- 新增方向燈指示系統 (85 BPM, 漸層動畫)
- 新增 Spotify QR Code 授權流程
- 新增非同步專輯封面載入
- 修復 Qt 物件生命週期問題

### v1.2 (2025-10)
- 新增 Spotify 音樂播放器整合
- 新增 Demo 模式
- 改善多執行緒架構

### v1.1 (2025-09)
- 新增類比錶盤顯示
- 優化 CAN Bus 訊號處理

### v1.0 (2025-08)
- 初始版本
- 基本 CAN Bus 和 OBD-II 功能
- PyQt6 儀表板介面

## 授權與免責聲明

本專案僅供學習和研究用途。使用者需自行承擔使用風險。

- 請遵守相關車輛診斷和 CAN Bus 通訊的法律規範
- 不當操作 CAN Bus 可能導致車輛故障或安全問題
- Spotify API 使用需遵守 [Spotify Developer Terms](https://developer.spotify.com/terms)

## 相關文件

### 設定指南
- [Spotify 設定指南](docs/setup/SPOTIFY_SETUP.md)
- [QR Code 授權指南](docs/features/QR_AUTH_GUIDE.md)
- [Raspberry Pi 設定](docs/setup/RASPBERRY_PI_SETUP.md)
- [全螢幕模式設定](docs/setup/RPI_FULLSCREEN_NOTES.md)

### 功能說明
- [方向燈實作說明](docs/features/TURN_SIGNAL_IMPLEMENTATION.md)
- [里程卡片實作](docs/features/TRIP_CARD_IMPLEMENTATION.md)

### 開發文件
- [速限查詢技術細節](docs/features/SPEED_LIMIT_TECHNICAL.md)
