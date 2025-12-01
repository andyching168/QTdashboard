# Luxgen M7 數位儀表板系統

## 功能說明

這是一個針對 Luxgen 7 MPV 的數位儀表板系統，整合了 CAN Bus 監聽、OBD-II 診斷功能、Spotify 音樂播放器、MQTT 導航資訊、WiFi 管理，以及車輛方向燈指示，並透過 PyQt6 提供現代化的儀表板顯示介面。

### 核心功能

#### 1. 車輛數據顯示
- **轉速**: 透過 OBD-II 讀取 (PID 0x0C)，使用 EMA 平滑演算法，20Hz 查詢頻率
- **水箱溫度**: 透過 OBD-II 讀取 (PID 0x05)
- **速度**: 讀取 CAN Bus 上的 `SPEED_FL` 訊號 (ID 0x38A / 906)
- **油量**: 讀取 CAN Bus 上的 `FUEL` 訊號 (ID 0x335 / 821)
- **檔位**: 解析 CAN Bus 上的 `ENGINE_RPM1` 訊號中的變速箱模式 (ID 0x340 / 832)
- **渦輪增壓**: 顯示進氣歧管壓力 (bar)，正壓時紅色顯示（熱血模式 🔥）
- **電瓶電壓**: 即時監控電瓶狀態

#### 2. 方向燈指示系統
- **85 BPM 閃爍頻率**: 符合原廠規格 (週期 0.706 秒)
- **漸層動畫效果**: 
  - 亮起時：瞬間全亮
  - 熄滅時：從中央向邊緣漸暗消失
- **頂部狀態欄**: 50px 高度，左右兩側各佔 1/4 螢幕寬度 (480px)
- **CAN Bus 整合**: 接收左轉、右轉、雙閃訊號
- **執行緒安全**: 透過 Qt Signal/Slot 機制確保多執行緒環境下的安全性

#### 3. Spotify 音樂整合
- **QR Code 授權**: 掃描 QR Code 即可完成 Spotify 帳號綁定
- **即時播放資訊**: 顯示歌曲名稱、演出者、專輯封面
- **跑馬燈效果**: 過長的歌曲名稱自動滾動顯示
- **播放進度顯示**: 即時更新播放進度條和時間
- **非同步專輯封面載入**: 背景執行緒載入圖片，不阻塞 UI
- **自動重新連線**: 偵測斷線並自動重新建立連線

#### 4. MQTT 導航整合
- **即時導航資訊**: 接收來自手機的 Google Maps 導航資料
- **方向圖標顯示**: 顯示下一個轉彎的方向圖標 (Base64 PNG)
- **轉彎距離**: 顯示距離下一個轉彎的距離
- **預計到達時間**: 顯示 ETA 和總剩餘時間
- **QR Code 設定**: 透過手機掃描 QR Code 設定 MQTT Broker

#### 5. 里程統計
- **總里程 (ODO)**: 持久化儲存，自動累積
- **單次里程 (Trip1/Trip2)**: 兩組可獨立重置的里程計
- **資料持久化**: 里程資料自動儲存至 `mileage_data.json`

#### 6. 下拉控制面板
從螢幕頂部下滑開啟控制面板，提供快速設定：

| 按鈕 | 功能 |
|------|------|
| 📶 WiFi | 開啟 WiFi 管理器，掃描並連接無線網路 |
| 🔵 藍牙 | 藍牙設定（待實現）|
| ☀ 亮度 | 軟體亮度調節：100% → 75% → 50% 循環 |
| 🔄 更新 | 自動更新：執行 git pull 並重新啟動 |
| ⏻ 電源 | 電源選項：程式重啟 / 系統重啟 / 關機 |
| ⚙ 設定 | 開啟 MQTT 設定 QR Code |

#### 7. 軟體亮度控制
- **三段亮度**: 100% (全亮) → 75% → 50%
- **軟體實現**: 透過半透明黑色覆蓋層降低亮度
- **不影響操作**: 覆蓋層設定為滑鼠事件穿透

#### 8. 自動更新功能
- **Git 整合**: 從 GitHub 拉取最新程式碼
- **自動重啟**: 更新後自動重新啟動程式
- **網路檢查**: 僅在有網路連線時可用

#### 9. 車門狀態顯示
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

如需使用 Spotify 功能，請參考 [Spotify 設定指南](SPOTIFY_SETUP.md) 或 [QR Code 授權指南](QR_AUTH_GUIDE.md)。

```bash
cp spotify_config.json.example spotify_config.json
# 編輯 spotify_config.json，填入 Client ID 和 Client Secret
```

### 4. Raspberry Pi 免密碼權限設定

在 Raspberry Pi 上執行一次，允許電源控制和 NTP 同步無需密碼：

```bash
sudo bash setup_sudoers.sh
```

## 使用方法

### 方式 1: 自動啟動腳本 (推薦)

```bash
./auto_start.sh
```

腳本會自動：
1. 偵測 Python 環境 (conda / venv)
2. 檢查網路連線並進行 NTP 時間同步
3. 偵測 CANable 裝置
   - 有 CANable → 執行 `datagrab.py` (實車模式)
   - 無 CANable → 執行 `demo_mode.py` (演示模式)
4. 處理 Spotify 認證

### 方式 2: 完整 CAN Bus 模式 (實車環境)

```bash
python datagrab.py
```

程式會自動偵測並選擇標有 "canable" 的 COM Port。

### 方式 3: Demo 模式 (測試/展示用)

```bash
python demo_mode.py
```

Demo 模式提供：
- 模擬車輛數據 (怠速 → 加速 → 巡航 → 減速循環)
- Spotify 整合測試
- 鍵盤互動控制
- 無需連接實車硬體

## 儀表板介面

儀表板針對 **1920x480** 解析度螢幕優化。

### 開發環境
- 可縮放視窗，拖曳邊框可按比例縮放
- 預設大小 960x240 (50% 縮放)
- 8.8 吋螢幕約等於視窗寬度 800 像素

### 版面配置

```
┌─────────────────────────────────────────────────────────────┐
│ ◄ 左轉燈 │          時間 HH:MM:SS          │ 右轉燈 ► │ 狀態欄
├─────────┬───────────────────────────────────┬───────────────┤
│  四宮格  │                                   │   第一列卡片   │
│  儀表    │       速度 + 檔位 + 轉速          │  (左右滑動)   │
│─────────│                                   ├───────────────┤
│  油量    │                                   │   第二列卡片   │
│         │                                   │  (上下切換列) │
└─────────┴───────────────────────────────────┴───────────────┘
```

### 左側區域

| 區塊 | 功能 |
|------|------|
| 四宮格儀表 | ENGINE RPM / COOLANT / TURBO / BATTERY |
| 油量表 | 油量百分比顯示 |

### 右側卡片系統

#### 第一列 (娛樂/導航)
| 卡片 | 功能 |
|------|------|
| Spotify | 音樂播放資訊 |
| 導航 | MQTT 導航資訊 |
| 車門狀態 | 圖形化顯示各門開關狀態 |

#### 第二列 (車輛資訊)
| 卡片 | 功能 |
|------|------|
| Trip計 | Trip1 + Trip2 ,可一鍵重置 |
|里程表ODO|可自行輸入目前里程數|

### 操作方式

#### 鍵盤控制
| 按鍵 | 功能 |
|------|------|
| W/S | 增加/減少速度和轉速 |
| Q/E | 降低/升高水溫 |
| A/D | 減少/增加油量 |
| 1-6 | 切換檔位 (P/R/N/D/S/L) |
| 7/8/9/0/- | 開關車門 (前左/前右/後左/後右/尾門) |
| ↑/↓ | 切換列（第一列 ⇄ 第二列）|
| ←/→ | 切換當前列的卡片 |
| F1 | 翻左卡片/進入焦點模式 |
| Shift+F1 | 相當於長按,觸發焦點事件 |
| F2 | 翻右卡片 |
| Shift+F2 | 相當於長按,觸發焦點事件 |

#### 觸控/滑鼠
| 操作 | 功能 |
|------|------|
| 頂部下滑 | 開啟控制面板 |
| 右側區域上下滑動 | 切換列 |
| 右側區域左右滑動 | 切換卡片 |
| 滾動滑輪 | 切換卡片 |
| Shift + 滾輪 | 切換列 |
| 點擊四宮格儀表 | 進入該儀表詳細視圖 |
| 詳細視圖左滑 | 返回四宮格 |

## 專案結構

### 核心檔案

#### 主程式
| 檔案 | 說明 |
|------|------|
| `main.py` | PyQt6 儀表板前端介面 |
| `datagrab.py` | CAN Bus 和 OBD-II 資料擷取 |
| `demo_mode.py` | 演示模式 |
| `auto_start.sh` | 自動啟動腳本 |

#### CAN Bus 相關
| 檔案 | 說明 |
|------|------|
| `luxgen_m7_2009.dbc` | CAN Bus 資料庫定義檔 |
| `can_simulator.py` | 完整 CAN Bus 模擬器 |
| `simple_simulator.py` | 簡易 SLCAN 模擬器 |

#### Spotify 整合
| 檔案 | 說明 |
|------|------|
| `spotify_integration.py` | Spotify 整合主模組 |
| `spotify_auth.py` | OAuth 認證管理器 |
| `spotify_qr_auth.py` | QR Code 授權對話框 |
| `spotify_listener.py` | 播放狀態監聯器 |

#### 系統功能
| 檔案 | 說明 |
|------|------|
| `wifi_manager.py` | WiFi 管理器 |
| `setup_sudoers.sh` | 免密碼權限設定腳本 |

#### 設定檔
| 檔案 | 說明 |
|------|------|
| `spotify_config.json` | Spotify API 設定 |
| `mqtt_config.json` | MQTT Broker 設定 |
| `mileage_data.json` | 里程資料 (自動生成) |

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
sudo bash setup_sudoers.sh

# 5. 測試執行
./auto_start.sh
```

### 開機自動啟動

編輯 `~/.config/lxsession/LXDE-pi/autostart`，加入：

```
@bash /home/pi/QTdashboard/auto_start.sh
```

### 全螢幕設定

詳見 [RPI_FULLSCREEN_NOTES.md](RPI_FULLSCREEN_NOTES.md)

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

## 除錯與日誌

### 查看即時日誌

```bash
tail -f qtdashboard.log
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

### v1.5 (2025-12)
- ✨ 新增下拉控制面板（WiFi/亮度/更新/電源/設定）
- ✨ 新增軟體亮度控制（100%/75%/50%）
- ✨ 新增自動更新功能（git pull + 重啟）
- ✨ 新增電源選單（程式重啟/系統重啟/關機）
- ✨ 新增 MQTT 設定 QR Code
- ✨ 新增 `auto_start.sh` 自動啟動腳本
- ✨ 新增 `setup_sudoers.sh` 免密碼權限設定
- ✨ 渦輪正壓時紅色顯示（熱血模式）
- ✨ CANable 自動偵測
- ✨ NTP 時間自動同步
- 🔧 控制面板/設定視窗自動縮放

### v1.4 (2025-11)
- ✨ 新增 MQTT 導航資訊整合
- ✨ 新增 WiFi 管理器
- ✨ 新增里程統計（ODO/Trip1/Trip2）
- ✨ 新增車門狀態顯示
- ✨ 新增四宮格儀表詳細視圖
- ✨ 新增跑馬燈文字效果
- 🔧 改善可縮放視窗（開發環境）

### v1.3 (2025-11)
- ✨ 新增方向燈指示系統 (85 BPM, 漸層動畫)
- ✨ 新增 Spotify QR Code 授權流程
- ✨ 新增非同步專輯封面載入
- 🐛 修復 Qt 物件生命週期問題

### v1.2 (2025-10)
- ✨ 新增 Spotify 音樂播放器整合
- ✨ 新增 Demo 模式
- 🔧 改善多執行緒架構

### v1.1 (2025-09)
- ✨ 新增類比錶盤顯示
- 🔧 優化 CAN Bus 訊號處理

### v1.0 (2025-08)
- 🎉 初始版本
- ✨ 基本 CAN Bus 和 OBD-II 功能
- ✨ PyQt6 儀表板介面

## 授權與免責聲明

本專案僅供學習和研究用途。使用者需自行承擔使用風險。

- 請遵守相關車輛診斷和 CAN Bus 通訊的法律規範
- 不當操作 CAN Bus 可能導致車輛故障或安全問題
- Spotify API 使用需遵守 [Spotify Developer Terms](https://developer.spotify.com/terms)

## 相關文件

- [Spotify 設定指南](SPOTIFY_SETUP.md)
- [QR Code 授權指南](QR_AUTH_GUIDE.md)
- [Raspberry Pi 設定](RASPBERRY_PI_SETUP.md)
- [全螢幕模式設定](RPI_FULLSCREEN_NOTES.md)
- [方向燈實作說明](TURN_SIGNAL_IMPLEMENTATION.md)
- [里程卡片實作](TRIP_CARD_IMPLEMENTATION.md)
