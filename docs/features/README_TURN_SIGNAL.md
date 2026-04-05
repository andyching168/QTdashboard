# 方向燈功能實作完成 ✅

## 🎯 功能摘要

已成功將 **LEFT_SIGNAL_STATUS** 和 **RIGHT_SIGNAL_STATUS** 整合到 Luxgen M7 儀表板系統中。

## 📋 實作清單

- [x] 解析 DBC 中的方向燈訊號 (BODY_ECU_STATUS, ID 0x420)
- [x] 在 `datagrab.py` 中加入訊號處理邏輯
- [x] 連接方向燈訊號到 Dashboard UI
- [x] 實作漸層動畫效果 (亮起/熄滅)
- [x] 支援左轉、右轉、雙閃三種模式
- [x] 建立完整測試套件
- [x] 撰寫技術文件

## 🚀 快速測試

### 1. 邏輯測試 (無需 GUI)
```bash
python test_turn_signal_logic.py
```

預期輸出：
```
✓ 所有測試通過！方向燈功能已準備就緒。
```

### 2. 鍵盤模擬測試
```bash
python main.py
```

然後按：
- **Z** 鍵 → 切換左轉燈
- **X** 鍵 → 切換右轉燈  
- **C** 鍵 → 切換雙閃

### 3. 實車測試
```bash
python datagrab.py
```

操作車輛方向燈撥桿，觀察儀表板反應。

## 📊 訊號規格

| 訊號名稱 | CAN ID | 位元位置 | 說明 |
|---------|--------|---------|------|
| LEFT_SIGNAL_STATUS | 0x420 | bit 10 | 左轉燈狀態 (0=關, 1=開) |
| RIGHT_SIGNAL_STATUS | 0x420 | bit 9 | 右轉燈狀態 (0=關, 1=開) |

**特殊模式**:
- 當兩個訊號都為 1 時 = 雙閃 (Hazard Light)

## 🎨 視覺效果

```
┌─────────────────────────────────────────────────────┐
│  ⬅ [═══════════════]   時間   [═══════════════] ➡  │ ← 狀態欄
├─────────────────────────────────────────────────────┤
│                                                     │
│     [儀表]     [速度]     [儀表]                   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

- **亮起**: 瞬間全亮 (亮綠色)
- **熄滅**: 從中心向外漸暗 (約 1 秒)
- **更新率**: 60 FPS

## 📁 相關檔案

### 核心程式
- `main.py` - Dashboard UI (已包含方向燈顯示邏輯)
- `datagrab.py` - CAN Bus 訊號處理 (新增方向燈解析)
- `luxgen_m7_2009.dbc` - CAN 訊號定義檔

### 測試程式
- `test_turn_signal_logic.py` - 邏輯測試 (無需 GUI) ⭐ 推薦
- `test_turn_signal_integration.py` - 整合測試
- `test_turn_signal_simple.py` - 簡化測試 (獨立 GUI)

### 文件
- `TURN_SIGNAL_IMPLEMENTATION_V2.md` - 完整技術文件
- `README_TURN_SIGNAL.md` - 本檔案

## 🔧 技術細節

### CAN Bus 層
```python
# datagrab.py 中的處理邏輯
elif msg.arbitration_id == 0x420:  # BODY_ECU_STATUS
    decoded = db.decode_message(msg.arbitration_id, msg.data)
    left_signal = decoded.get('LEFT_SIGNAL_STATUS', 0)
    right_signal = decoded.get('RIGHT_SIGNAL_STATUS', 0)
    
    if left_signal == 1 and right_signal == 1:
        signals.update_turn_signal.emit("both_on")
    elif left_signal == 1:
        signals.update_turn_signal.emit("left_on")
    elif right_signal == 1:
        signals.update_turn_signal.emit("right_on")
    else:
        signals.update_turn_signal.emit("off")
```

### UI 層
```python
# main.py 中的 API
dashboard.set_turn_signal("left_on")   # 左轉燈亮
dashboard.set_turn_signal("right_on")  # 右轉燈亮
dashboard.set_turn_signal("both_on")   # 雙閃亮
dashboard.set_turn_signal("off")       # 全關
```

## ✅ 測試結果

```
============================================================
測試結果: 4 通過, 0 失敗
============================================================
邏輯測試: ✓ 通過
DBC 解析: ✓ 通過
============================================================

🎉 所有測試通過！方向燈功能已準備就緒。
```

## 📝 使用範例

### 從 CAN Bus 自動更新 (推薦)
```python
# datagrab.py 會自動處理，無需手動介入
python datagrab.py
```

### 手動控制 (用於測試)
```python
from main import Dashboard
from PyQt6.QtWidgets import QApplication

app = QApplication([])
dashboard = Dashboard()
dashboard.show()

# 模擬方向燈切換
dashboard.set_turn_signal("left_on")   # 左轉
dashboard.set_turn_signal("right_on")  # 右轉
dashboard.set_turn_signal("both_on")   # 雙閃
dashboard.set_turn_signal("off")       # 關閉

app.exec()
```

## 🐛 除錯

如果方向燈不亮，檢查：

1. **CAN Bus 連接**
   ```bash
   # 確認有收到 0x420 訊息
   candump can0 | grep 420
   ```

2. **DBC 解析**
   ```bash
   python test_turn_signal_logic.py
   ```

3. **日誌檢查**
   ```bash
   tail -f qtdashboard.log | grep "方向燈"
   ```

## 🎓 學習資源

- [CAN Bus 基礎](https://en.wikipedia.org/wiki/CAN_bus)
- [DBC 檔案格式](https://github.com/eerimoq/cantools)
- [PyQt6 訊號與槽](https://doc.qt.io/qtforpython-6/overviews/signalsandslots.html)

## 👏 貢獻

本功能由 GitHub Copilot 協助實作，基於 Luxgen M7 2009 的 CAN Bus 訊號規格。

## 📄 授權

與主專案相同。

---

**最後更新**: 2025-11-24  
**版本**: 1.0.0  
**狀態**: ✅ 生產就緒
