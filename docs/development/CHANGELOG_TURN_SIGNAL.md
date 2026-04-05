# 方向燈實作 - 程式碼變更清單

## 檔案修改摘要

### 修改的檔案
1. `datagrab.py` - 3 處修改
2. `main.py` - 無需修改（已具備功能）

### 新增的檔案
- 測試程式 × 3
- 文件 × 5

---

## 📝 詳細變更

### 1. datagrab.py - 變更 #1: 新增訊號定義

**位置**: `WorkerSignals` 類別內

**原始碼**:
```python
class WorkerSignals(QObject):
    update_rpm = pyqtSignal(float)
    update_speed = pyqtSignal(float)
    signal_update_temp = pyqtSignal(float)
    update_fuel = pyqtSignal(float)
    update_gear = pyqtSignal(str)
    # update_nav_icon = pyqtSignal(str)
```

**新增**:
```python
class WorkerSignals(QObject):
    update_rpm = pyqtSignal(float)
    update_speed = pyqtSignal(float)
    signal_update_temp = pyqtSignal(float)
    update_fuel = pyqtSignal(float)
    update_gear = pyqtSignal(str)
    update_turn_signal = pyqtSignal(str)  # ← 新增這一行
    # update_nav_icon = pyqtSignal(str)
```

**說明**: 新增方向燈訊號，用於從背景執行緒傳遞方向燈狀態到 GUI。

---

### 2. datagrab.py - 變更 #2: 新增訊號處理邏輯

**位置**: `unified_receiver()` 函數內，在處理速度訊號 (ID 0x38A) 之後

**插入位置**: 第 186 行左右 (在 `# 5. 偵測潛在的 RPM 訊號` 註解之前)

**新增程式碼**:
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
                    # 根據 DBC 註解：R,L shows at same time means hazard (雙閃)
                    if left_signal == 1 and right_signal == 1:
                        signals.update_turn_signal.emit("both_on")
                    elif left_signal == 1 and right_signal == 0:
                        signals.update_turn_signal.emit("left_on")
                    elif left_signal == 0 and right_signal == 1:
                        signals.update_turn_signal.emit("right_on")
                    else:
                        signals.update_turn_signal.emit("off")
                    
                    logger.debug(f"方向燈: L={left_signal} R={right_signal}")
                    
                except cantools.database.errors.DecodeError as e:
                    logger.error(f"DBC 解碼錯誤 (BODY_ECU_STATUS): {e}")
                except Exception as e:
                    logger.error(f"處理方向燈訊息錯誤: {e}")
```

**說明**: 
- 監聽 CAN ID 0x420 (BODY_ECU_STATUS)
- 解析 LEFT_SIGNAL_STATUS 和 RIGHT_SIGNAL_STATUS
- 根據訊號組合判斷狀態（左轉/右轉/雙閃/關閉）
- 透過 Qt Signal 發送到 GUI

---

### 3. datagrab.py - 變更 #3: 連接訊號到 Dashboard

**位置**: `main()` 函數內，在連接其他訊號的地方

**原始碼**:
```python
        # ★★★ 關鍵連接步驟 ★★★
        signals.update_rpm.connect(dashboard.set_rpm)
        signals.update_speed.connect(dashboard.set_speed)
        signals.update_temp.connect(dashboard.set_temperature)
        signals.update_fuel.connect(dashboard.set_fuel)
        signals.update_gear.connect(dashboard.set_gear)
```

**新增**:
```python
        # ★★★ 關鍵連接步驟 ★★★
        signals.update_rpm.connect(dashboard.set_rpm)
        signals.update_speed.connect(dashboard.set_speed)
        signals.update_temp.connect(dashboard.set_temperature)
        signals.update_fuel.connect(dashboard.set_fuel)
        signals.update_gear.connect(dashboard.set_gear)
        signals.update_turn_signal.connect(dashboard.set_turn_signal)  # ← 新增這一行
```

**說明**: 將方向燈訊號連接到 Dashboard 的處理函數。

---

## 📊 變更統計

| 檔案 | 新增行數 | 修改行數 | 刪除行數 |
|------|---------|---------|---------|
| `datagrab.py` | +40 | +2 | 0 |
| `main.py` | 0 | 0 | 0 |
| **總計** | **+40** | **+2** | **0** |

---

## 🎯 關鍵程式碼片段

### CAN 訊號判斷邏輯
```python
if left_signal == 1 and right_signal == 1:
    signals.update_turn_signal.emit("both_on")    # 雙閃
elif left_signal == 1 and right_signal == 0:
    signals.update_turn_signal.emit("left_on")    # 左轉
elif left_signal == 0 and right_signal == 1:
    signals.update_turn_signal.emit("right_on")   # 右轉
else:
    signals.update_turn_signal.emit("off")        # 關閉
```

### Dashboard 處理邏輯 (main.py 中已存在)
```python
@pyqtSlot(str)
def _slot_update_turn_signal(self, state):
    if state == "left_on":
        self.left_turn_on = True
        self.right_turn_on = False
    elif state == "left_off":
        self.left_turn_on = False
    elif state == "right_on":
        self.right_turn_on = True
        self.left_turn_on = False
    elif state == "right_off":
        self.right_turn_on = False
    elif state == "both_on":
        self.left_turn_on = True
        self.right_turn_on = True
    elif state == "both_off" or state == "off":
        self.left_turn_on = False
        self.right_turn_on = False
```

---

## 🔍 DBC 訊號規格

### BODY_ECU_STATUS (ID 0x420)
```dbc
BO_ 1056 BODY_ECU_STATUS: 8 XXX
   SG_ DOOR_RL_STATUS : 18|1@0+ (1,0) [0|255] "" XXX
   SG_ DOOR_FL_STATUS : 13|1@0+ (1,0) [0|1] "" XXX
   SG_ DOOR_FR_STATUS : 12|1@0+ (1,0) [0|1] "" XXX
   SG_ DOOR_RR_STATUS : 19|1@0+ (1,0) [0|1] "" XXX
   SG_ DOOR_BACK_DOOR_STATUS : 22|1@0+ (1,0) [0|1] "" XXX
   SG_ LEFT_SIGNAL_STATUS : 10|1@0+ (1,0) [0|1] "" XXX      ← 左轉燈
   SG_ RIGHT_SIGNAL_STATUS : 9|1@0+ (1,0) [0|1] "" XXX      ← 右轉燈
```

**註解**:
```
CM_ SG_ 1056 RIGHT_SIGNAL_STATUS "R,L shows at same time means hazard";
```

---

## ✅ 驗證檢查清單

- [x] `WorkerSignals` 類別新增 `update_turn_signal` 訊號
- [x] `unified_receiver()` 函數新增 ID 0x420 處理邏輯
- [x] `main()` 函數連接訊號到 Dashboard
- [x] 邏輯測試通過
- [x] 文件完整

---

## 📦 相關檔案

### 核心程式
- `datagrab.py` - ✏️ 已修改
- `main.py` - ✅ 無需修改

### 測試程式
- `test_turn_signal_logic.py` - 邏輯測試 ⭐
- `test_turn_signal_integration.py` - 整合測試
- `test_turn_signal_simple.py` - 簡化測試

### 文件
- `TURN_SIGNAL_IMPLEMENTATION_V2.md` - 技術文件
- `README_TURN_SIGNAL.md` - 使用指南
- `TURN_SIGNAL_SUMMARY.md` - 實作總結
- `QUICKSTART_TURN_SIGNAL.md` - 快速開始
- `CHANGELOG_TURN_SIGNAL.md` - 本檔案

---

## 🎓 學習重點

1. **執行緒安全通訊**: 使用 Qt Signal/Slot 機制
2. **CAN Bus 訊號解析**: DBC 檔案定義與 cantools 使用
3. **狀態機設計**: 根據兩個 bit 訊號組合判斷狀態
4. **錯誤處理**: try-except 保護避免單一訊息錯誤導致系統崩潰

---

**變更日期**: 2025-11-24  
**版本**: 1.0.0  
**狀態**: ✅ 完成並測試通過
