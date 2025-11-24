# Luxgen M7 數位儀表板系統

## 功能說明

這是一個針對 Luxgen 7 MPV 的數位儀表板系統，整合了 CAN Bus 監聽和 OBD-II 診斷功能，並透過 PyQt6 提供現代化的儀表板顯示介面。

### 數據來源 (根據備註.txt)

- **水箱溫度**: 透過 OBD-II 讀取 (PID 0x05)
- **轉速**: 讀取 CAN Bus 上的 `ENGINE_RPM1` 訊號 (ID 0x340 / 832)
- **油量**: 讀取 CAN Bus 上的 `FUEL` 訊號 (ID 0x335 / 821)
- **速度**: 讀取 CAN Bus 上的 `SPEED_FL` 訊號 (ID 0x38A / 906)

## 安裝步驟

### 1. 安裝相依套件

```bash
pip install -r requirements.txt
```

### 2. 硬體準備

- CAN Bus 轉接器 (支援 slcan 協定)
- 連接到車輛的 OBD-II 接口

## 使用方法

### 執行主程式

```bash
python datagrab.py
```

程式會自動：
1. 偵測並列出可用的 Serial 裝置
2. 選擇 CAN Bus 介面
3. 初始化 CAN Bus 和 DBC 解碼器
4. 啟動背景執行緒接收 CAN 訊息和查詢 OBD-II
5. 開啟儀表板前端視窗

### 前端介面

儀表板針對 **1920x480** 解析度螢幕優化，包含：

- **左側水溫表**: 顯示引擎水溫 (C-H)
- **中央轉速表**: 顯示引擎轉速 (0-8 x1000rpm)，紅區從 6500rpm 開始
- **數位速度顯示**: 中央大型數字顯示車速 (km/h)
- **檔位顯示**: 顯示當前檔位 (P/R/N/D/S/L)
- **右側油量表**: 顯示油箱油量 (E-F)

### 鍵盤模擬 (測試用)

在前端視窗中可使用鍵盤模擬數據：
- **W/S**: 增加/減少速度和轉速
- **Q/E**: 減少/增加水溫
- **A/D**: 減少/增加油量
- **1-6**: 切換檔位 (P/R/N/D/S/L)

## 檔案說明

- `datagrab.py`: 主程式，負責 CAN Bus 和 OBD-II 資料擷取，並整合前端顯示
- `main.py`: PyQt6 儀表板前端介面
- `luxgen_m7_2009.dbc`: Luxgen M7 的 CAN Bus 資料庫定義檔
- `備註.txt`: 數據來源說明
- `requirements.txt`: Python 套件相依清單

## 技術細節

### CAN Bus 訊號處理

程式使用統一的接收執行緒 (`unified_receiver`) 處理所有 CAN 訊息：

- **即時解碼**: 使用 DBC 檔案自動解碼 CAN 訊號
- **多執行緒架構**: 分離的接收和查詢執行緒，避免阻塞
- **錯誤處理**: 自動跳過損壞的訊框，保持系統穩定

### OBD-II 查詢

- 定期查詢水箱溫度 (PID 0x05)
- 使用鎖機制保護 CAN Bus 寫入操作
- 自動調整查詢頻率避免緩衝區溢位

### 前端更新機制

所有數據接收後立即更新到前端介面：
- 轉速轉換為千轉單位 (rpm / 1000)
- 水溫正規化到 0-100 範圍
- 油量和速度直接顯示原始值

## 測試模式 (無需實車)

### 方法 1: 使用虛擬 CAN Bus (推薦 - Linux/macOS)

#### Linux 設定
```bash
# 建立虛擬 CAN 介面
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

# 執行模擬器
python can_simulator.py --channel vcan0 --rate 10

# 在另一個終端執行主程式
python datagrab.py
# 選擇 vcan0 作為介面
```

#### macOS 設定
```bash
# 使用虛擬 bus (不需要實際硬體)
python can_simulator.py --virtual --rate 10

# 在另一個終端執行主程式
python datagrab.py
```

### 方法 2: 使用虛擬 Serial Port

#### 建立虛擬 Serial Port 對
```bash
# macOS/Linux: 安裝 socat
brew install socat  # macOS
# 或
sudo apt install socat  # Linux

# 建立虛擬 port 對
socat -d -d pty,raw,echo=0 pty,raw,echo=0
# 會顯示兩個 port 路徑，例如:
# 2024/11/24 10:00:00 socat[12345] N PTY is /dev/ttys002
# 2024/11/24 10:00:00 socat[12345] N PTY is /dev/ttys003
```

#### 執行簡易模擬器
```bash
# 使用第一個 port 執行模擬器
python simple_simulator.py /dev/ttys013

# 在另一個終端執行主程式
python datagrab.py
# 會自動列出虛擬 port，選擇 /dev/ttys014
# 或直接輸入: /dev/ttys014
```

**提示**: 如果沒看到虛擬 port，可以直接輸入完整路徑 `/dev/ttysXXX`

### 模擬器功能

**can_simulator.py** - 完整 CAN 模擬器
- 模擬真實車輛行駛狀態 (怠速、加速、巡航、減速)
- 支援 OBD-II 請求回應
- 使用 DBC 檔案編碼訊息
- 可配置更新頻率

**simple_simulator.py** - 簡易模擬器
- 使用 SLCAN 協定
- 透過虛擬 serial port 發送數據
- 更輕量，適合快速測試

## 注意事項

1. **CAN Bus 介面**: 預設使用 slcan 協定，請根據實際硬體調整
2. **DBC 檔案**: 確保 `luxgen_m7_2009.dbc` 在同一目錄下
3. **解析度**: 前端介面針對 1920x480 螢幕優化，可在程式碼中調整
4. **執行緒安全**: 使用 `send_lock` 保護 CAN Bus 寫入操作
5. **測試環境**: 可使用模擬器進行開發測試，無需連接實車

## 授權

請遵守相關車輛診斷和 CAN Bus 通訊的法律規範。
