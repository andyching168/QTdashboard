# 方向燈功能實作文件

## 概述
本文件說明 Luxgen M7 儀表板系統中方向燈 (Turn Signal) 功能的實作細節。

## DBC 訊號定義

### 訊息: BODY_ECU_STATUS
- **CAN ID**: 0x420 (十進位 1056)
- **長度**: 8 bytes
- **來源**: Body ECU (車身電子控制單元)

### 相關訊號

#### LEFT_SIGNAL_STATUS
- **起始位元**: 10
- **長度**: 1 bit
- **值域**: 0 (關閉) / 1 (亮起)
- **說明**: 左轉方向燈狀態

#### RIGHT_SIGNAL_STATUS
- **起始位元**: 9
- **長度**: 1 bit
- **值域**: 0 (關閉) / 1 (亮起)
- **說明**: 右轉方向燈狀態

#### 特殊狀態
根據 DBC 註解：
```
"R,L shows at same time means hazard"
```
當左轉和右轉訊號同時為 1 時，表示雙閃警示燈 (Hazard Light)。

## 實作架構

### 1. 訊號解析 (datagrab.py)

在 `unified_receiver()` 函數中新增對 `BODY_ECU_STATUS` 訊息的處理：

```python
# 5. 處理方向燈 BODY_ECU_STATUS (ID 0x420 / 1056)
elif msg.arbitration_id == 0x420:
    try:
        decoded = db.decode_message(msg.arbitration_id, msg.data)
        
        # 讀取方向燈狀態 (bit signals)
        left_signal = decoded.get('LEFT_SIGNAL_STATUS', 0)
        right_signal = decoded.get('RIGHT_SIGNAL_STATUS', 0)
        
        # 轉換為 int (如果是 NamedSignalValue)
        if hasattr(left_signal, 'value'):
            left_signal = int(left_signal.value)
        else:
            left_signal = int(left_signal)
        
        if hasattr(right_signal, 'value'):
            right_signal = int(right_signal.value)
        else:
            right_signal = int(right_signal)
        
        # 判斷方向燈狀態並發送
        if left_signal == 1 and right_signal == 1:
            signals.update_turn_signal.emit("both_on")
        elif left_signal == 1 and right_signal == 0:
            signals.update_turn_signal.emit("left_on")
        elif left_signal == 0 and right_signal == 1:
            signals.update_turn_signal.emit("right_on")
        else:
            signals.update_turn_signal.emit("off")
        
    except Exception as e:
        logger.error(f"處理方向燈訊息錯誤: {e}")
```

### 2. 訊號傳遞

**WorkerSignals 類別新增**:
```python
update_turn_signal = pyqtSignal(str)  # 發送方向燈狀態
```

**主程式連接**:
```python
signals.update_turn_signal.connect(dashboard.set_turn_signal)
```

### 3. 前端顯示 (main.py)

Dashboard 類別已具備完整的方向燈顯示功能：

#### 視覺元素
- **左側漸層條**: 從最左延伸至 1/4 螢幕寬 (480px)
- **右側漸層條**: 從 3/4 螢幕處延伸至最右 (480px)
- **方向燈圖標**: ⬅ (左) / ➡ (右)，疊在漸層條上方

#### 動畫效果
- **亮起**: 訊號為 1 時，整條漸層瞬間亮起為亮綠色 (rgba(177, 255, 0, 0.7))
- **熄滅**: 訊號為 0 時，漸層從中心向外漸暗 (fade speed = 0.05)
- **更新頻率**: 約 60 FPS (16ms)

#### 狀態對應

| CAN 訊號 | 內部狀態 | 視覺效果 |
|---------|---------|---------|
| LEFT=0, RIGHT=0 | off | 兩側都暗 |
| LEFT=1, RIGHT=0 | left_on | 左側亮綠色 |
| LEFT=0, RIGHT=1 | right_on | 右側亮綠色 |
| LEFT=1, RIGHT=1 | both_on | 兩側都亮綠色 |

## API 介面

### 公開方法

```python
def set_turn_signal(self, state: str) -> None:
    """
    設置方向燈狀態
    
    Args:
        state: 方向燈狀態
            - "left_on": 左轉燈亮
            - "left_off": 左轉燈滅
            - "right_on": 右轉燈亮
            - "right_off": 右轉燈滅
            - "both_on": 雙閃亮
            - "both_off": 雙閃滅
            - "off": 全部關閉
    
    執行緒安全: 透過 Signal 發送，由主執行緒執行
    """
```

### 鍵盤測試快捷鍵 (main.py)

在 Dashboard 的 `keyPressEvent` 中：
- **Z 鍵**: 切換左轉燈
- **X 鍵**: 切換右轉燈
- **C 鍵**: 切換雙閃

## 測試程式

### 1. 邏輯測試
```bash
python test_turn_signal_logic.py
```
測試方向燈訊號邏輯和 DBC 解析。

### 2. 整合測試
```bash
python test_turn_signal_integration.py
```
自動序列測試 Dashboard 的方向燈功能。

### 3. 簡化測試 (無 Spotify 依賴)
```bash
python test_turn_signal_simple.py        # 自動測試
python test_turn_signal_simple.py manual # 手動測試
```

## 實車測試

### 連接方式
1. 連接 CAN Bus 介面 (SLCAN)
2. 啟動主程式：`python datagrab.py`
3. 操作方向燈撥桿，觀察儀表板反應

### 預期行為
- 撥動左轉撥桿 → 左側漸層條亮起
- 撥動右轉撥桿 → 右側漸層條亮起
- 按下雙閃開關 → 兩側漸層條同時亮起
- 歸位 → 對應側漸層條熄滅

### 訊號更新率
- **BODY_ECU_STATUS** 的 CAN 訊息更新率約 10-20 Hz
- GUI 動畫更新率為 60 FPS，提供流暢的視覺效果

## 已知限制

1. **訊號延遲**: CAN Bus 到 GUI 有約 50-100ms 延遲
2. **無閃爍控制**: 當前實作直接反映 CAN 訊號狀態，不額外控制閃爍頻率
3. **顏色固定**: 使用亮綠色 (符合 Luxgen M7 原廠設計)

## 未來改進方向

1. ✅ **基本功能** - 已完成
2. ⬜ **音效整合** - 方向燈滴答聲
3. ⬜ **故障偵測** - 偵測方向燈故障 (例如持續亮超過 30 秒)
4. ⬜ **智慧提醒** - 高速長時間開啟方向燈時提醒

## 版本歷史

### v1.0.0 (2025-11-24)
- ✅ 完整實作左/右方向燈和雙閃功能
- ✅ 漸層動畫效果
- ✅ CAN Bus 訊號整合
- ✅ 測試程式套件

## 參考資料

- DBC 檔案: `luxgen_m7_2009.dbc`
- 主程式: `main.py`
- 資料抓取: `datagrab.py`
- 測試程式: `test_turn_signal_*.py`
