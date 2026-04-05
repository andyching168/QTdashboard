# 方向燈功能 - 快速開始指南 🚦

## 📦 已完成的修改

### 修改的檔案
1. ✅ `datagrab.py` - 新增方向燈 CAN 訊號解析
2. ✅ `main.py` - 已包含完整方向燈顯示功能 (無需修改)

### 新增的檔案
- `test_turn_signal_logic.py` - 邏輯測試程式 ⭐
- `test_turn_signal_integration.py` - 整合測試
- `test_turn_signal_simple.py` - 簡化測試
- `TURN_SIGNAL_IMPLEMENTATION_V2.md` - 技術文件
- `README_TURN_SIGNAL.md` - 使用指南
- `TURN_SIGNAL_SUMMARY.md` - 實作總結
- `QUICKSTART_TURN_SIGNAL.md` - 本檔案

## 🎯 核心改動說明

### 1. WorkerSignals 類別 (datagrab.py)
```python
# 新增這一行
update_turn_signal = pyqtSignal(str)  # 發送方向燈狀態
```

### 2. unified_receiver 函數 (datagrab.py)
在處理 CAN 訊息的地方，新增了對 ID 0x420 的處理：

```python
# 5. 處理方向燈 BODY_ECU_STATUS (ID 0x420 / 1056)
elif msg.arbitration_id == 0x420:
    try:
        decoded = db.decode_message(msg.arbitration_id, msg.data)
        
        # 讀取方向燈狀態 (bit signals)
        left_signal = decoded.get('LEFT_SIGNAL_STATUS', 0)
        right_signal = decoded.get('RIGHT_SIGNAL_STATUS', 0)
        
        # ... (訊號轉換邏輯)
        
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

### 3. 主程式連接 (datagrab.py main 函數)
```python
# 新增這一行
signals.update_turn_signal.connect(dashboard.set_turn_signal)
```

## ✅ 驗證步驟

### 步驟 1: 執行邏輯測試
```bash
python test_turn_signal_logic.py
```

預期看到：
```
🎉 所有測試通過！方向燈功能已準備就緒。
```

### 步驟 2: 啟動主程式測試
```bash
python main.py
```

按鍵測試：
- 按 **Z** → 左轉燈應該亮起 (左側綠色漸層條)
- 按 **X** → 右轉燈應該亮起 (右側綠色漸層條)
- 按 **C** → 雙閃應該亮起 (兩側都亮)
- 再按一次 → 對應的燈應該熄滅

### 步驟 3: 實車測試 (需要 CAN Bus 硬體)
```bash
python datagrab.py
```

操作車輛方向燈撥桿，觀察儀表板反應。

## 📋 訊號對照表

| CAN 訊號 | 狀態值 | Dashboard 顯示 |
|---------|-------|---------------|
| LEFT=0, RIGHT=0 | `"off"` | 兩側都暗 |
| LEFT=1, RIGHT=0 | `"left_on"` | 左側亮綠色漸層 |
| LEFT=0, RIGHT=1 | `"right_on"` | 右側亮綠色漸層 |
| LEFT=1, RIGHT=1 | `"both_on"` | 兩側都亮綠色 |

## 🎨 視覺效果說明

### 正常狀態 (關閉)
```
[暗灰色圖標]                [暗灰色圖標]
     ⬅                          ➡
```

### 左轉燈亮起
```
[亮綠色圖標 + 漸層條══════]      [暗灰色]
     ⬅                          ➡
```

### 右轉燈亮起
```
[暗灰色]      [══════漸層條 + 亮綠色圖標]
     ⬅                          ➡
```

### 雙閃亮起
```
[亮綠色 + 漸層══]    [══漸層 + 亮綠色]
     ⬅                     ➡
```

## 🔍 除錯提示

### 如果方向燈不亮

1. **檢查 CAN Bus 連接**
   ```bash
   candump can0 | grep 420
   ```
   應該看到 ID 0x420 的訊息。

2. **檢查日誌**
   ```bash
   tail -f qtdashboard.log | grep "方向燈"
   ```

3. **檢查訊號解析**
   ```bash
   python test_turn_signal_logic.py
   ```

### 常見問題

**Q: 為什麼只有一側的燈亮？**  
A: 這是正常的！左轉只亮左側，右轉只亮右側。只有雙閃（警示燈）時兩側才會同時亮。

**Q: 燈的顏色為什麼是綠色？**  
A: 這是根據 Luxgen M7 原廠設計使用的顏色。如需修改，可在 `main.py` 的 `update_turn_signal_style()` 函數中調整。

**Q: 方向燈會閃爍嗎？**  
A: 當前實作直接反映 CAN Bus 的訊號狀態。如果 CAN Bus 訊號本身就是閃爍的（通常是 85 BPM），UI 也會跟著閃爍。

## 📚 延伸閱讀

- 完整技術文件: `TURN_SIGNAL_IMPLEMENTATION_V2.md`
- 使用指南: `README_TURN_SIGNAL.md`
- 實作總結: `TURN_SIGNAL_SUMMARY.md`

## 🎉 完成！

方向燈功能已經完整實作並測試完成。現在你可以：

1. ✅ 在主程式中看到方向燈顯示
2. ✅ 使用鍵盤快捷鍵測試
3. ✅ 從 CAN Bus 自動接收方向燈訊號
4. ✅ 支援左轉、右轉、雙閃三種模式

**開始使用**: `python main.py` 然後按 Z/X/C 鍵測試！

---

📅 2025-11-24  
🚗 Luxgen M7 2009  
✨ Status: Ready to Use
