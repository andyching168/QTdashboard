# Luxgen M7 數位儀表板系統

## 功能說明

這是一個針對 Luxgen 7 MPV 的數位儀表板系統，整合了 CAN Bus 監聽、OBD-II 診斷功能、Spotify 音樂播放器整合，以及車輛方向燈指示，並透過 PyQt6 提供現代化的儀表板顯示介面。

### 核心功能

#### 1. 車輛數據顯示
- **轉速**: 透過 OBD-II 讀取 (PID 0x0C)，使用 EMA 平滑演算法，20Hz 查詢頻率
- **水箱溫度**: 透過 OBD-II 讀取 (PID 0x05)
- **速度**: 讀取 CAN Bus 上的 `SPEED_FL` 訊號 (ID 0x38A / 906)
- **油量**: 讀取 CAN Bus 上的 `FUEL` 訊號 (ID 0x335 / 821)
- **檔位**: 解析 CAN Bus 上的 `ENGINE_RPM1` 訊號中的變速箱模式 (ID 0x340 / 832)

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
- **播放進度顯示**: 即時更新播放進度條和時間
- **非同步專輯封面載入**: 背景執行緒載入圖片，不阻塞 UI
- **自動重新連線**: 偵測斷線並自動重新建立連線

## 系統需求

### 硬體需求
- **顯示螢幕**: 1920x480 解析度 (針對此規格優化)
- **CAN Bus 轉接器**: 支援 slcan 協定的 CAN-USB 轉接器
- **車輛介面**: 連接到 Luxgen M7 的 OBD-II 接口
- **運算平台**: 
  - Raspberry Pi 4 (推薦)
  - 或任何支援 PyQt6 的 Linux/macOS 系統

### 軟體需求
- Python 3.8 或更高版本
- PyQt6 6.10.0+
- 完整相依套件列表見 `requirements.txt`

## 安裝步驟

### 1. 複製專案

```bash
git clone <repository_url>
cd QTdashboard
```

### 2. 安裝 Python 相依套件

```bash
pip install -r requirements.txt
```

**requirements.txt 包含**:
- `PyQt6>=6.10.0` - GUI 框架
- `python-can>=4.6.0` - CAN Bus 通訊
- `cantools>=41.0.0` - DBC 檔案解析
- `pyserial>=3.5` - Serial Port 通訊
- `spotipy>=2.25.0` - Spotify API 客戶端
- `Pillow>=12.0.0` - 圖片處理
- `qrcode[pil]>=8.2` - QR Code 生成
- `requests>=2.32.0` - HTTP 請求
- `rich>=14.2.0` - 終端機美化輸出

### 3. Spotify 設定 (選用)

如需使用 Spotify 功能，請參考 [Spotify 設定指南](SPOTIFY_SETUP.md) 或 [QR Code 授權指南](QR_AUTH_GUIDE.md)。

1. 複製設定檔範本：
```bash
cp spotify_config.json.example spotify_config.json
```

2. 在 [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) 建立應用程式

3. 編輯 `spotify_config.json`，填入 Client ID 和 Client Secret

4. 執行程式後點擊「綁定 Spotify」按鈕，掃描 QR Code 完成授權

## 使用方法

### 方式 1: 完整 CAN Bus 模式 (實車環境)

```bash
python datagrab.py
```

程式會自動：
1. 偵測並列出可用的 Serial 裝置
2. 選擇 CAN Bus 介面
3. 初始化 CAN Bus 和 DBC 解碼器
4. 啟動背景執行緒接收 CAN 訊息和查詢 OBD-II
5. 初始化 Spotify 整合 (如果已設定)
6. 開啟儀表板前端視窗

### 方式 2: Demo 模式 (測試/展示用)

```bash
python demo_mode.py
```

Demo 模式提供：
- 模擬車輛數據 (怠速、加速、巡航、減速循環)
- Spotify 整合測試
- 鍵盤互動控制
- 無需連接實車硬體

### 儀表板介面說明

儀表板針對 **1920x480** 解析度螢幕優化，版面配置：

#### 頂部狀態欄 (50px 高度)
- **左側方向燈**: 佔據左側 1/4 螢幕寬度 (480px)
  - 漸層條從螢幕邊緣延伸至 1/4 位置
  - 箭頭圖標 (⬅) 疊加在條的最左端
  - 85 BPM 閃爍 (0.353 秒亮/滅)
  - 熄滅時從中央向邊緣漸暗
  
- **中央時間顯示**: 顯示當前系統時間 (HH:MM:SS)

- **右側方向燈**: 佔據右側 1/4 螢幕寬度 (480px)
  - 漸層條從 1/4 位置延伸至螢幕邊緣
  - 箭頭圖標 (▶) 疊加在條的最右端
  - 雙閃時左右同步亮滅

#### 主要儀表區域
- **左側水溫表**: 類比式錶盤，顯示引擎水溫 (C-H)
- **中央轉速表**: 類比式錶盤，顯示引擎轉速 (0-8 x1000rpm)
  - 紅區從 6500rpm 開始 (紅色標示)
- **數位速度顯示**: 中央大型數字顯示車速 (km/h)
- **檔位顯示**: 顯示當前檔位 (P/R/N/D/S/L)
- **右側油量表**: 類比式錶盤，顯示油箱油量 (E-F)

#### Spotify 音樂卡片 (右下角)
- **未綁定狀態**: 顯示「綁定 Spotify」按鈕
- **已綁定狀態**: 顯示播放資訊
  - 專輯封面 (180x180px)
  - 歌曲名稱
  - 演出者
  - 播放進度條
  - 當前時間/總時長

### 鍵盤控制 (測試用)

在前端視窗中可使用鍵盤模擬車輛數據：
- **W/S**: 增加/減少速度和轉速
- **Q/E**: 減少/增加水溫
- **A/D**: 減少/增加油量
- **1-6**: 切換檔位 (P/R/N/D/S/L)
- **Left Arrow**: 開啟左轉燈
- **Right Arrow**: 開啟右轉燈
- **Down Arrow**: 關閉所有方向燈
- **Up Arrow**: 開啟雙閃燈

## 專案結構

### 核心檔案

#### 主程式
- **`datagrab.py`**: 主程式入口，負責 CAN Bus 和 OBD-II 資料擷取，整合前端顯示和 Spotify
- **`main.py`**: PyQt6 儀表板前端介面，包含所有 UI 元件和動畫
- **`demo_mode.py`**: Demo 模式執行器，模擬車輛數據用於測試

#### CAN Bus 相關
- **`luxgen_m7_2009.dbc`**: Luxgen M7 的 CAN Bus 資料庫定義檔 (DBC 格式)
- **`can_simulator.py`**: 完整 CAN Bus 模擬器，支援虛擬 CAN 介面
- **`simple_simulator.py`**: 簡易 SLCAN 協定模擬器，透過虛擬 Serial Port
- **`test_can_turn_signals.py`**: 方向燈 CAN 訊號測試工具 (85 BPM)

#### Spotify 整合
- **`spotify_integration.py`**: Spotify 整合主模組，連接 datagrab.py 和 Spotify API
- **`spotify_auth.py`**: Spotify OAuth 認證管理器
- **`spotify_qr_auth.py`**: QR Code 授權對話框 (PyQt6)
- **`spotify_listener.py`**: Spotify 播放狀態監聽器 (背景執行緒)
- **`spotify_config.json`**: Spotify API 設定檔 (需自行建立)
- **`spotify_config.json.example`**: 設定檔範本

#### 測試工具
- **`test_receiver.py`**: CAN Bus 接收測試
- **`test_hex_parser.py`**: CAN 訊息解析測試
- **`test_spotify.sh`**: Spotify 功能測試腳本
- **`test_spotify_bind.sh`**: Spotify 綁定流程測試
- **`run_test.sh`**: 快速測試腳本

#### 文件
- **`README.md`**: 專案說明 (本檔案)
- **`SPOTIFY_SETUP.md`**: Spotify 詳細設定指南
- **`QR_AUTH_GUIDE.md`**: QR Code 授權使用指南
- **`SPOTIFY_INTEGRATION_REPORT.md`**: Spotify 整合技術報告
- **`TURN_SIGNAL_IMPLEMENTATION.md`**: 方向燈實作說明
- **`RASPBERRY_PI_SETUP.md`**: Raspberry Pi 環境設定指南
- **`RPI_FULLSCREEN_NOTES.md`**: Raspberry Pi 全螢幕模式設定
- **`備註.txt`**: 車輛數據來源說明 (中文)

#### 其他
- **`requirements.txt`**: Python 套件相依清單
- **`.spotify_cache`**: Spotify Token 快取檔 (自動生成)
- **`qtdashboard.log`**: 執行日誌檔 (自動生成)

## 技術細節

### 架構設計

#### 多執行緒架構
```
主執行緒 (PyQt6 GUI)
├── CAN Bus 接收執行緒
├── OBD-II 查詢執行緒
├── Spotify 監聽執行緒
└── 動畫更新執行緒 (60 FPS)
```

所有背景執行緒透過 **Qt Signal/Slot** 機制與 UI 溝通，確保執行緒安全。

### CAN Bus 訊號處理

#### 統一接收機制
程式使用 `unified_receiver` 執行緒處理所有 CAN 訊息：

- **即時解碼**: 使用 DBC 檔案自動解碼 CAN 訊號
- **訊號過濾**: 針對特定 CAN ID 進行過濾和解析
- **錯誤處理**: 自動跳過損壞的訊框，保持系統穩定
- **鎖機制**: 使用 `send_lock` 保護 CAN Bus 寫入操作

#### 支援的 CAN 訊號
| 訊號名稱 | CAN ID | 描述 |
|---------|--------|------|
| `ENGINE_RPM1` | 0x340 (832) | 變速箱模式 (檔位解析) |
| `SPEED_FL` | 0x38A (906) | 車速 (前左輪) |
| `FUEL` | 0x335 (821) | 油量百分比 |
| 方向燈訊號 | (自定義) | 左轉/右轉/雙閃狀態 |

#### 支援的 OBD-II PID
| PID | 描述 | 查詢頻率 |
|-----|------|---------|
| 0x0C | 引擎轉速 (RPM) | 20Hz (每 0.05 秒) |
| 0x05 | 冷卻液溫度 (°C) | 20Hz (每 0.05 秒) |

**註**: 轉速改用 OBD-II 的原因是 Luxgen M7 的 CAN Bus 轉速訊號在 D/R 檔位使用特殊的 Base+Delta 編碼，實測極不穩定，故採用標準 OBD-II PID 0x0C 以確保準確性。

### OBD-II 診斷

- **主要查詢項目**: 
  - **轉速 (PID 0x0C)**: 使用 EMA (Exponential Moving Average) 平滑演算法，alpha=0.15
  - **水箱溫度 (PID 0x05)**: 正規化為 0-100% 顯示範圍
- **查詢頻率**: 20Hz (每 0.05 秒)，提供流暢的指針更新
- **非阻塞設計**: 獨立執行緒執行查詢
- **錯誤恢復**: 自動重試失敗的查詢
- **雙 ECU 支援**: 接收 ECU (0x7E8) 和 TCM (0x7E9) 的回應

### 方向燈系統

#### 動畫實作
```python
# 60 FPS 動畫迴圈
QTimer(16ms) → update_gradient_animation()
  ├── 檢查 left_turn_on / right_turn_on 狀態
  ├── 亮起時：瞬間設置 gradient_pos = 1.0
  └── 熄滅時：每幀減少 0.06，產生漸暗效果
```

#### CSS 動態生成
```python
# 根據 gradient_pos 動態生成漸層樣式
if pos >= 1.0:
    # 完全亮起：純色填滿
    background: #28a745 (左) / #28a745 (右)
else:
    # 漸暗中：產生漸層效果
    background: qlineargradient(
        stop:0 rgba(40,167,69, alpha),
        stop:1 rgba(40,167,69, 0)
    )
```

#### CAN Bus 介面
```python
# 外部呼叫 (執行緒安全)
dashboard.set_turn_signal("left_on")   # 開啟左轉燈
dashboard.set_turn_signal("left_off")  # 關閉左轉燈
dashboard.set_turn_signal("both_on")   # 開啟雙閃
dashboard.set_turn_signal("off")       # 關閉所有方向燈
```

### Spotify 整合

#### 認證流程
1. 讀取 `spotify_config.json` 取得 Client ID/Secret
2. 產生 OAuth 授權 URL
3. 顯示 QR Code 對話框
4. 啟動本地 HTTP 伺服器 (Port 8888)
5. 使用者掃描 QR Code → Spotify 授權頁面
6. 授權成功 → Redirect 回本地伺服器
7. 交換 Authorization Code → Access Token
8. 儲存 Token 至 `.spotify_cache`

#### 播放監聽
```python
SpotifyListener (背景執行緒)
  ├── 每 1 秒查詢 Spotify API
  ├── 解析 currently_playing 資料
  ├── 非同步載入專輯封面 (Pillow)
  └── 透過 Signal 更新 UI
```

#### 執行緒安全更新
```python
# 背景執行緒呼叫
dashboard.update_spotify_track(title, artist)
dashboard.update_spotify_progress(current, total)
dashboard.update_spotify_art(pil_image)

# → Qt Signal 傳遞 →

# 主執行緒執行
@pyqtSlot
_slot_update_spotify_track() → 更新 UI
```

### 前端更新機制

#### 數據正規化
- **轉速**: 
  - 來源：OBD-II PID 0x0C
  - 計算：`(Byte3 × 256 + Byte4) / 4` RPM
  - 平滑：EMA 演算法 (alpha=0.15)
  - 顯示：`rpm / 1000` 轉換為千轉單位 (0-8)
- **水溫**: 
  - 來源：OBD-II PID 0x05
  - 計算：`Byte3 - 40` °C
  - 正規化：`((temp - 40) / 80) × 100%` (40°C=0%, 120°C=100%)
- **速度**: 
  - 來源：CAN Bus ID 0x38A
  - 直接顯示 km/h (0-255)
- **油量**: 
  - 來源：CAN Bus ID 0x335
  - 百分比 (0-100%)
- **檔位**: 
  - 來源：CAN Bus ID 0x340 Byte0 (變速箱模式)
  - 映射：0x00→P/N, 0x01→D, 0x07→R

#### 動畫系統
- **類比錶盤**: 使用 QPainter 繪製，支援自訂刻度和紅區
- **漸層動畫**: 60 FPS 更新，流暢漸變效果
- **專輯封面**: 淡入淡出效果 (未實作，待優化)

## 測試與開發

### 快速測試 (推薦)

#### Demo 模式 - 一鍵啟動
```bash
python demo_mode.py
```

Demo 模式提供：
- ✅ 模擬車輛數據 (怠速 → 加速 → 巡航 → 減速循環)
- ✅ 完整 UI 功能展示
- ✅ Spotify 整合測試 (需先設定)
- ✅ 鍵盤互動控制
- ✅ 無需任何硬體

#### 方向燈測試工具
```bash
python test_can_turn_signals.py
```

功能：
- 自動測試左轉、右轉、雙閃循環
- 85 BPM 精確閃爍頻率
- 驗證漸層動畫效果
- CAN Bus 訊號模擬

### 進階測試 (CAN Bus 模擬)

#### 方法 1: 虛擬 CAN Bus (Linux 推薦)

##### 設定虛擬 CAN 介面
```bash
# 載入 vcan 核心模組
sudo modprobe vcan

# 建立虛擬 CAN 介面
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

# 驗證介面
ip link show vcan0
```

##### 執行模擬器
```bash
# 終端機 1: 啟動 CAN 模擬器
python can_simulator.py --channel vcan0 --rate 10

# 終端機 2: 執行主程式
python datagrab.py
# 選擇 vcan0 作為 CAN 介面
```

##### 監控 CAN 訊息 (除錯用)
```bash
# 安裝 can-utils
sudo apt install can-utils  # Debian/Ubuntu
brew install can-utils       # macOS (需要 Homebrew)

# 即時監控
candump vcan0

# 發送測試訊息
cansend vcan0 340#1122334455667788
```

#### 方法 2: 虛擬 Serial Port (跨平台)

##### 安裝 socat
```bash
# macOS
brew install socat

# Linux (Debian/Ubuntu)
sudo apt install socat

# Linux (RHEL/CentOS)
sudo yum install socat
```

##### 建立虛擬 Serial Port 對
```bash
# 執行後保持終端機開啟
socat -d -d pty,raw,echo=0 pty,raw,echo=0

# 輸出範例:
# 2025/11/24 10:30:00 socat[12345] N PTY is /dev/ttys002
# 2025/11/24 10:30:00 socat[12345] N PTY is /dev/ttys003
```

##### 執行測試
```bash
# 終端機 1: 執行 simple_simulator.py (使用第一個 port)
python simple_simulator.py /dev/ttys002

# 終端機 2: 執行主程式 (使用第二個 port)
python datagrab.py
# 輸入或選擇: /dev/ttys003
```

**提示**: 如果 port 未自動列出，直接輸入完整路徑即可。

### 模擬器說明

#### can_simulator.py - 完整 CAN 模擬器
**功能**:
- 完整車輛行駛狀態機 (怠速 → 加速 → 巡航 → 減速)
- OBD-II PID 0x05 (水溫) 請求/回應
- 使用 DBC 檔案進行訊息編碼
- 支援虛擬 CAN 介面 (vcan0)
- 可調整更新頻率 (`--rate` 參數)

**使用範例**:
```bash
# 使用虛擬 CAN (Linux)
python can_simulator.py --channel vcan0 --rate 10

# 使用實體 CAN 介面 (需硬體)
python can_simulator.py --channel can0 --bitrate 500000 --rate 10
```

#### simple_simulator.py - 輕量級模擬器
**功能**:
- SLCAN 協定訊息生成
- 透過 Serial Port 發送
- 適合快速測試和除錯
- 輕量、簡單、快速

**使用範例**:
```bash
python simple_simulator.py /dev/ttyUSB0
# 或虛擬 port
python simple_simulator.py /dev/ttys002
```

#### test_can_turn_signals.py - 方向燈專用測試
**功能**:
- 自動循環測試 (左轉 → 右轉 → 雙閃 → 關閉)
- 85 BPM 閃爍頻率驗證
- 每個狀態持續 3 秒
- 直接呼叫 Dashboard API

**使用範例**:
```bash
python test_can_turn_signals.py
# 觀察方向燈動畫效果
```

### Spotify 功能測試

#### 快速測試腳本
```bash
# 測試 Spotify 連線和播放資訊
./test_spotify.sh

# 測試 QR Code 綁定流程
./test_spotify_bind.sh
```

#### 手動測試步驟
```bash
# 1. 驗證設定檔
cat spotify_config.json

# 2. 執行 Demo 模式
python demo_mode.py

# 3. 點擊「綁定 Spotify」按鈕

# 4. 使用手機掃描 QR Code

# 5. 在 Spotify App 中播放音樂

# 6. 確認儀表板顯示播放資訊
```

## Raspberry Pi 部署

完整的 Raspberry Pi 設定指南請參考：
- [RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md) - 環境安裝和設定
- [RPI_FULLSCREEN_NOTES.md](RPI_FULLSCREEN_NOTES.md) - 全螢幕模式設定

### 快速設定

```bash
# 1. 更新系統
sudo apt update && sudo apt upgrade -y

# 2. 安裝相依套件
sudo apt install python3-pyqt6 python3-pip can-utils -y

# 3. 安裝 Python 套件
pip3 install -r requirements.txt

# 4. 設定開機自動執行 (可選)
# 編輯 ~/.config/lxsession/LXDE-pi/autostart
# 加入: @python3 /home/pi/QTdashboard/datagrab.py
```

### 效能優化建議

- **使用 Raspberry Pi 4 (4GB 以上)**
- **啟用硬體加速**: 確保 GPU 記憶體至少 256MB
- **關閉不必要的服務**: 釋放更多 CPU 資源
- **使用輕量級視窗管理器**: 如 Openbox 或 X11 無視窗模式

## 除錯與日誌

### 日誌檔案
程式執行時會自動產生 `qtdashboard.log`，記錄：
- CAN Bus 連線狀態
- Spotify API 請求/回應
- 錯誤和異常訊息
- 執行緒狀態

### 查看即時日誌
```bash
# 即時監控日誌
tail -f qtdashboard.log

# 搜尋錯誤訊息
grep ERROR qtdashboard.log

# 搜尋 Spotify 相關訊息
grep -i spotify qtdashboard.log
```

### 常見問題

#### CAN Bus 相關
**問題**: 找不到 CAN 介面
```bash
# 檢查 CAN 裝置
ls -l /dev/ttyUSB* /dev/ttyACM*

# 檢查虛擬 CAN
ip link show vcan0
```

**問題**: 權限不足
```bash
# 加入使用者到 dialout 群組
sudo usermod -a -G dialout $USER
# 登出後重新登入
```

#### Spotify 相關
**問題**: QR Code 掃描後無反應
- 檢查 `spotify_config.json` 的 Redirect URI 是否為 `http://localhost:8888/callback`
- 確認防火牆未阻擋 Port 8888
- 檢查 `.spotify_cache` 權限

**問題**: 無法顯示專輯封面
```bash
# 確認已安裝 Pillow
pip3 show Pillow

# 測試圖片載入
python3 -c "from PIL import Image; print('OK')"
```

#### 顯示相關
**問題**: 解析度不正確
- 編輯 `main.py` 中的 `self.setFixedSize(1920, 480)`
- 或修改系統顯示設定

**問題**: 全螢幕模式問題
- 參考 [RPI_FULLSCREEN_NOTES.md](RPI_FULLSCREEN_NOTES.md)
- 確認使用 `self.showFullScreen()` 而非 `self.show()`

## 開發指南

### 新增 CAN 訊號

1. 編輯 `luxgen_m7_2009.dbc`，加入新訊號定義
2. 在 `datagrab.py` 的 `unified_receiver()` 中加入解析邏輯
3. 在 `main.py` 加入對應的 Signal 和 UI 更新方法

### 自訂 UI 元件

所有 UI 元件都在 `main.py` 中：
- `AnalogGauge`: 類比錶盤
- `MusicCard`: Spotify 音樂卡片
- `Dashboard`: 主儀表板類別

修改樣式請編輯 `setStyleSheet()` 中的 CSS。

### 擴充 Spotify 功能

Spotify 相關模組：
- `spotify_integration.py`: 整合邏輯
- `spotify_listener.py`: 播放狀態監聽
- `spotify_auth.py`: OAuth 認證

新增功能時請遵循執行緒安全原則，使用 Qt Signal/Slot 更新 UI。

## 效能與最佳化

### 目前效能指標
- **GUI 更新頻率**: 10 Hz (每 100ms)
- **動畫幀率**: 60 FPS (每 16ms)
- **Spotify 輪詢**: 1 Hz (每 1 秒)
- **CAN Bus 接收**: 即時 (無延遲)

### 已實作的最佳化
- ✅ 執行緒隔離 (CAN/Spotify/GUI 分離)
- ✅ 非同步專輯封面載入
- ✅ Qt Signal/Slot 事件驅動架構
- ✅ CSS 快取 (避免重複計算)
- ✅ QPainter 硬體加速

### 待優化項目
- ⏳ 專輯封面快取機制
- ⏳ 圖片淡入淡出動畫
- ⏳ 降低 Spotify API 呼叫頻率 (智慧輪詢)
- ⏳ CAN 訊息批次處理

## 注意事項

### 安全性
- **Spotify Token**: `.spotify_cache` 包含敏感資訊，請勿公開
- **CAN Bus 寫入**: 修改 CAN 訊息可能影響車輛運作，請謹慎操作
- **車輛診斷**: 請遵守當地法律規範

### 相容性
- **CAN 介面**: 預設使用 slcan 協定，硬體介面請根據實際情況調整
- **DBC 檔案**: 針對 Luxgen M7 2009 年款，其他車款需修改
- **解析度**: 針對 1920x480 優化，其他解析度需調整 UI 尺寸

### 限制
- **Spotify Free 用戶**: 無法使用 API 控制播放，僅能查看播放資訊
- **CAN Bus 速率**: 預設 500kbps，需與車輛匹配
- **單一 Spotify 帳號**: 同時只支援一個帳號登入

## 授權與免責聲明

本專案僅供學習和研究用途。使用者需自行承擔使用風險。

- 請遵守相關車輛診斷和 CAN Bus 通訊的法律規範
- 不當操作 CAN Bus 可能導致車輛故障或安全問題
- Spotify API 使用需遵守 [Spotify Developer Terms](https://developer.spotify.com/terms)

## 貢獻與支援

### 回報問題
請透過 GitHub Issues 回報 Bug 或提出功能建議。

### 相關文件
- [Spotify 整合報告](SPOTIFY_INTEGRATION_REPORT.md)
- [方向燈實作說明](TURN_SIGNAL_IMPLEMENTATION.md)
- [QR Code 授權指南](QR_AUTH_GUIDE.md)

## 變更記錄

### v1.3 (2025-11)
- ✨ 新增方向燈指示系統 (85 BPM, 漸層動畫)
- ✨ 新增 Spotify QR Code 授權流程
- ✨ 新增非同步專輯封面載入
- 🐛 修復 Qt 物件生命週期問題
- 📝 完善文件和測試工具

### v1.2 (2025-10)
- ✨ 新增 Spotify 音樂播放器整合
- ✨ 新增 Demo 模式
- 🔧 改善多執行緒架構

### v1.1 (2025-09)
- ✨ 新增類比錶盤顯示
- 🔧 優化 CAN Bus 訊號處理
- 📝 新增 DBC 檔案

### v1.0 (2025-08)
- 🎉 初始版本
- ✨ 基本 CAN Bus 和 OBD-II 功能
- ✨ PyQt6 儀表板介面
