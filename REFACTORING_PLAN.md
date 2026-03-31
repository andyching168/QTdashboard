# QTdashboard 代碼重構計劃

## 概述

本文件描述 QTdashboard 專案的重構目標、已完成項目和待完成項目。

---

## 重構目標

1. **目錄結構優化** - 建立清晰的模組化目錄結構
2. **代碼拆分** - 將巨大的 `main.py` 拆分為獨立的模組
3. **路徑一致性** - 統一使用絕對路徑，避免相對路徑問題
4. **提高可維護性** - 降低新人上手難度

---

## 待完成項目

### 高優先級

- [ ] **Dashboard 類拆分**
  - 將 `Dashboard` (約 3,700 行) 拆分為多個獨立類
  - 涉及信號/槽重建，工作量大
  - 風險：中等

- [ ] **循環依賴解除**
  - `datagrab.py ↔ main.py` 之間的循環依賴
  - 建議：透過中介介面或事件匯流排解耦

- [ ] **巨量函數拆分**
  - `keyPressEvent` (25 層嵌套) 需要重構為策略模式

### 中優先級

- [ ] **測試框架建立**
  - 目前無單元測試
  - 建議：建立基本的 pytest 框架

- [ ] **Configuration 統一管理**
  - 各模組分散讀取配置文件
  - 建議：建立統一的 ConfigManager

### 低優先級

- [ ] **文檔完善**
  - API 文檔
  - 架構圖

---

## 已完成項目

### v2.0 重構（當前分支）

| 項目 | 狀態 | 說明 |
|------|--------|------|
| 目錄結構重組 | ✅ 完成 | 建立 assets/, spotify/, vehicle/, hardware/, navigation/, wifi/, core/, deploy/ |
| UI 模組提取 | ✅ 完成 | 提取 11 個 UI 模組到 ui/ 目錄 |
| 工具類別提取 | ✅ 完成 | PerformanceMonitor, JankDetector, OdometerStorage 移至 core/ |
| 路徑問題修復 | ✅ 完成 | 所有配置檔使用絕對路徑 |
| macOS 兼容性 | ✅ 完成 | 多媒體可選，補足缺失 imports |

### main.py 演變

| 階段 | 行數 | 變更 |
|------|------|------|
| 重構前 | 12,059 | - |
| 第一階段後 | 10,394 | 提取 UI 通用元件 |
| 第二階段後 | 4,684 | 提取所有 UI 類別 |
| 第三階段後 | 4,306 | 提取工具類別到 core/ |
| 第四階段後 | 3,974 | 提取 ScalableWindow, NumericKeypad |

---

## 代碼屎山指數

| 階段 | 分數 |
|------|------|
| 重構前 | 6.5/10 |
| 重構後 | 4.5/10 |

---

## 目錄結構

```
QTdashboard/
├── main.py                    # 入口 (3,974 行)
├── core/                      # 核心工具
│   ├── utils.py              # 效能監控、存儲等
│   ├── max_value_logger.py
│   ├── shutdown_monitor.py
│   └── startup_progress.py
├── ui/                        # UI 組件
│   ├── common.py             # GaugeStyle, RadarOverlay
│   ├── door_card.py
│   ├── gauge_card.py
│   ├── music_card.py
│   ├── navigation_card.py
│   ├── control_panel.py
│   ├── mqtt_settings.py
│   ├── trip_card.py
│   ├── analog_gauge.py
│   ├── threads.py
│   ├── splash_screen.py
│   ├── scalable_window.py
│   └── numeric_keypad.py
├── assets/                    # 媒體資源
│   ├── video/
│   └── sprites/
├── spotify/                  # Spotify 模組
├── vehicle/                   # CAN Bus 模組
├── hardware/                  # GPIO 模組
├── navigation/                # GPS 模組
├── wifi/                       # WiFi 模組
├── deploy/                    # 部署腳本
└── archive/                  # 廢棄檔案
```

---

## 分支使用建議

```bash
# 開發流程
git checkout main                           # 在 main 開發穩定功能
git checkout -b feature/xxx               # 建立功能分支
git checkout refactor/modularize-main      # 重構分支，測試新架構

# 部署流程
git checkout main                           # 切到 main
bash backup_and_setup.sh                    # 備份配置
git checkout refactor/modularize-main       # 測試重構分支
bash setup_after_checkout.sh               # 恢復配置
# 測試穩定後合併
git checkout main && git merge refactor/modularize-main
```

---

## 配置檔案位置

| 檔案 | 路徑 |
|------|------|
| Spotify 設定 | `spotify/spotify_config.json` |
| Spotify 快取 | `spotify/.spotify_cache` |
| MQTT 設定 | `mqtt_config.json` |
| 里程資料 | `~/.config/qtdashboard/odometer_data.json` |
| 車速校正 | `~/.config/qtdashboard/speed_calibration.json` |

---

## 已知限制

1. **Dashboard 仍是 God Object** - 約 3,700 行，所有狀態管理集中
2. **循環依賴未解除** - datagrab.py 和 main.py 之間
3. **無單元測試** - 重構風險較高

---

## 聯絡

如有問題，請開 Issue 或聯絡 maintainer。
