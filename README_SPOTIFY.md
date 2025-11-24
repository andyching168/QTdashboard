# Luxgen M7 數位儀表板 - Spotify Connect 整合專案

![Python](https://img.shields.io/badge/Python-3.14-blue)
![PyQt6](https://img.shields.io/badge/PyQt6-6.10-green)
![Spotify](https://img.shields.io/badge/Spotify-API-1DB954)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi-red)

> 參考 [FreekBes/spotify_web_controller](https://github.com/FreekBes/spotify_web_controller) 實作的車機 Spotify Connect 整合

專為 Luxgen M7 2009 打造的數位儀表板系統，整合 CAN Bus 車輛資訊與 Spotify 即時播放資訊，提供現代化的駕駛體驗。

## ✨ 主要功能

### 🚗 車輛資訊顯示
- **速度表**：0-180 km/h 類比表頭
- **轉速表**：0-7000 RPM，紅區 6000+ 
- **水溫表**：40-120°C，紅區 >100°C
- **油量表**：0-100%，低油量警告
- **檔位顯示**：P/R/N/D/S/L

### 🎵 Spotify Connect 整合
- **即時播放資訊**：歌曲名稱、藝人、專輯
- **專輯封面顯示**：自動下載並顯示
- **播放進度同步**：即時更新進度條
- **自動切歌偵測**：無縫切換歌曲資訊
- **支援免費帳號**：僅讀取播放資訊（Premium 可控制）

### 📱 觸控手勢支援
- **左右滑動**：在油量表與音樂卡片間切換
- **視覺指示器**：圓點顯示當前卡片位置
- **觸控最佳化**：支援 8.8 吋觸控螢幕

## 🎬 快速開始

### 前置需求

```bash
# 系統需求
- Python 3.14
- PyQt6 6.10+
- Conda/Miniconda

# 硬體需求（可選）
- CAN Bus 轉 USB 轉接器（SLCAN 協議）
- Raspberry Pi 4（建議）+ 8.8 吋觸控螢幕
```

### 安裝步驟

1. **Clone 專案**
```bash
git clone https://github.com/andyching168/QTdashboard.git
cd QTdashboard
```

2. **建立 Conda 環境**
```bash
conda create -n QTdashboard python=3.14 -y
conda activate QTdashboard
```

3. **安裝相依套件**
```bash
pip install -r requirements.txt
```

4. **設定 Spotify API**（選用）

參考 [SPOTIFY_SETUP.md](SPOTIFY_SETUP.md) 詳細說明：

```bash
# 複製配置範本
cp spotify_config.json.example spotify_config.json

# 編輯並填入您的 Spotify API 憑證
nano spotify_config.json
```

前往 [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) 建立應用程式並取得：
- Client ID
- Client Secret
- Redirect URI: `http://localhost:8888/callback`

### 執行模式

#### 演示模式（無需硬體）

```bash
# 基本演示（模擬音樂）
python demo_mode.py

# 啟用 Spotify Connect
python demo_mode.py --spotify
```

#### 完整系統（需要 CAN Bus）

```bash
# 基本模式
python datagrab.py

# 啟用 Spotify（未來實作）
python datagrab.py --enable-spotify
```

## 📖 詳細文件

- [🎵 Spotify 整合設定指南](SPOTIFY_SETUP.md)
- [🍓 Raspberry Pi 部署說明](RASPBERRY_PI_SETUP.md)
- [📝 專案開發筆記](備註.txt)

## 🎨 介面預覽

### 主儀表板
```
┌──────────────────────────────────────────────────────────┐
│  [速度表 0-180]    [轉速表 0-7000]    [右側卡片區域]     │
│                                                           │
│  [水溫表 40-120]   [檔位 P/R/N/D/S/L]  • ○ (卡片指示器) │
└──────────────────────────────────────────────────────────┘
```

### 音樂卡片
```
┌─────────────────┐
│  Now Playing    │
│                 │
│   ┌─────────┐   │
│   │ 🖼️封面  │   │
│   └─────────┘   │
│                 │
│  Drive My Car   │
│  The Beatles    │
│                 │
│  ▬▬▬▬▬▬▬▬▬▬▬   │
│  1:23    3:02   │
└─────────────────┘
```

## 🔧 技術架構

### 系統架構
```
CAN Bus ──> datagrab.py ──> Dashboard (PyQt6)
                               ↑
Spotify API ──> spotify_listener.py
```

### 核心模組

| 模組 | 功能 | 狀態 |
|------|------|------|
| `main.py` | PyQt6 儀表板 UI | ✅ 完成 |
| `datagrab.py` | CAN Bus 資料擷取 | ✅ 完成 |
| `spotify_auth.py` | OAuth 2.0 認證 | ✅ 完成 |
| `spotify_listener.py` | 播放狀態監聽 | ✅ 完成 |
| `spotify_integration.py` | 整合介面 | ✅ 完成 |
| `demo_mode.py` | 演示模式 | ✅ 完成 |

### Spotify API 使用

參考 [FreekBes/spotify_web_controller](https://github.com/FreekBes/spotify_web_controller) 的實作：

- **認證方式**：OAuth 2.0 Authorization Code Flow
- **輪詢頻率**：1 秒查詢一次 `/me/player/currently-playing`
- **Token 管理**：自動快取與更新
- **API 端點**：
  - `GET /me/player/currently-playing` - 當前播放資訊
  - `GET /me/player` - 完整播放狀態

## 🎯 使用場景

### 場景 1：在家測試（演示模式 + Spotify）
```bash
# 1. 在電腦上開啟 Spotify 並播放音樂
# 2. 執行演示模式
python demo_mode.py --spotify

# 3. 觀察即時同步的播放資訊
```

### 場景 2：車內使用（完整系統）
```bash
# 樹莓派開機自動啟動
# 同時顯示：
# - CAN Bus 車輛資訊（速度、轉速、油量、水溫）
# - Spotify 播放資訊（透過手機熱點）
```

### 場景 3：開發測試（模擬 CAN）
```bash
# 終端 1: 啟動 CAN 模擬器
python can_simulator.py --virtual

# 終端 2: 啟動儀表板 + Spotify
python datagrab.py --enable-spotify
```

## 🛠️ 開發工具

### 測試腳本

```bash
# CAN Bus 模擬器
python can_simulator.py --virtual

# 序列埠模擬器
python simple_simulator.py /dev/cu.usbserial-1234

# 接收測試
python test_receiver.py

# Spotify 認證測試
python spotify_auth.py

# Spotify 監聽測試
python spotify_listener.py
```

### VS Code 整合

專案已配置：
- `.vscode/settings.json` - Python 環境設定
- `.vscode/launch.json` - 除錯配置

## 📊 系統需求

### 最低需求
- CPU: ARM Cortex-A53 (Raspberry Pi 3)
- RAM: 1 GB
- Storage: 8 GB microSD
- Display: 800x480 (7 吋)

### 建議配置
- CPU: ARM Cortex-A72 (Raspberry Pi 4)
- RAM: 2 GB+
- Storage: 16 GB microSD (Class 10)
- Display: 1920x480 (8.8 吋觸控)

## 🚀 未來計畫

- [ ] **Spotify 播放控制**（需 Premium）
  - 播放/暫停
  - 上一首/下一首
  - 音量調整
  
- [ ] **播放清單顯示**
  - 當前佇列
  - 播放歷史
  
- [ ] **主題自訂**
  - 夜間模式
  - 色彩配置
  
- [ ] **更多資料來源**
  - OBD-II 診斷資訊
  - GPS 導航資訊
  - 胎壓監測

## 📝 授權

本專案採用 GPL-3.0 授權。

Spotify 整合參考了 [FreekBes/spotify_web_controller](https://github.com/FreekBes/spotify_web_controller)（GPL-3.0 授權）。

## 🤝 貢獻

歡迎提交 Issue 或 Pull Request！

## 📧 聯絡方式

- GitHub: [@andyching168](https://github.com/andyching168)
- 專案 Issues: [QTdashboard/issues](https://github.com/andyching168/QTdashboard/issues)

## 🙏 致謝

- [FreekBes/spotify_web_controller](https://github.com/FreekBes/spotify_web_controller) - Spotify Web API 實作參考
- [Spotify Web API](https://developer.spotify.com/documentation/web-api) - 官方文件
- [Spotipy](https://spotipy.readthedocs.io/) - Python Spotify 客戶端
- PyQt6 社群 - 優秀的 GUI 框架

---

**⭐ 如果這個專案對您有幫助，請給我們一個 Star！**
