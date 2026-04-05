# 方向燈實作說明

## 設計規格

### 視覺設計
- **位置**: 畫面最上方的窄狀態欄（50px 高）
- **佈局**: 左轉燈 ← [時間] → 右轉燈
- **動畫效果**: 漸層從一側刷過到另一側
  - 左轉燈: 從右向左刷過
  - 右轉燈: 從左向右刷過

### 技術規格
- **閃爍頻率**: 85 BPM（符合原廠維修手冊）
  - 週期: 60/85 ≈ 0.706 秒
  - 亮/滅時間: 各約 0.353 秒
- **動畫幀率**: 60 FPS（16ms 更新間隔）
- **渲染方式**: CSS qlineargradient 動態生成

## CAN Bus 訊號接口

### 訊號格式

方向燈使用**亮滅狀態訊號**，而非切換訊號：

```python
# 左轉燈亮
dashboard.set_turn_signal("left_on")

# 左轉燈滅
dashboard.set_turn_signal("left_off")

# 右轉燈亮
dashboard.set_turn_signal("right_on")

# 右轉燈滅
dashboard.set_turn_signal("right_off")

# 雙閃亮
dashboard.set_turn_signal("both_on")

# 雙閃滅
dashboard.set_turn_signal("both_off")

# 全部關閉
dashboard.set_turn_signal("off")
```

### 典型使用場景

```python
# 場景 1: 接收來自 CAN bus 的方向燈狀態
def on_can_message(msg_id, data):
    if msg_id == TURN_SIGNAL_STATUS_ID:
        left_on = data[0] & 0x01
        right_on = data[0] & 0x02
        
        if left_on:
            dashboard.set_turn_signal("left_on")
        else:
            dashboard.set_turn_signal("left_off")
        
        if right_on:
            dashboard.set_turn_signal("right_on")
        else:
            dashboard.set_turn_signal("right_off")

# 場景 2: 使用 CAN bus 模擬器（85 BPM 閃爍）
can_simulator = CANBusSimulator(dashboard)
can_simulator.start()

# 啟動左轉燈（會自動以 85 BPM 閃爍）
can_simulator.set_left_turn(True)

# 關閉左轉燈
can_simulator.set_left_turn(False)
```

## 測試方法

### 方法 1: CAN Bus 模擬器測試（推薦）

```bash
python test_can_turn_signals.py
```

**功能:**
- 自動模擬 85 BPM 的方向燈閃爍
- 自動測試序列
- 鍵盤控制 (Z/X/C)

### 方法 2: 直接測試

```bash
python main.py
```

**鍵盤控制:**
- `Z`: 切換左轉燈
- `X`: 切換右轉燈
- `C`: 切換雙閃

## 實作細節

### 狀態管理

```python
# Dashboard 類別中的狀態變數
self.left_turn_on = False   # 左轉燈當前是否為亮
self.right_turn_on = False  # 右轉燈當前是否為亮

# 漸層動畫位置 (0.0 到 1.0)
self.left_gradient_pos = 0.0
self.right_gradient_pos = 0.0
```

### 動畫更新循環

```python
# 60 FPS 更新（約 16ms 一次）
self.animation_timer = QTimer()
self.animation_timer.timeout.connect(self.update_gradient_animation)
self.animation_timer.start(16)
```

### 漸層樣式生成

左轉燈（從右向左）:
```python
qlineargradient(x1:1, y1:0, x2:0, y2:0,
    stop:0 暗色,
    stop:pos-0.3 暗色,
    stop:pos 亮橙色,      # 漸層核心
    stop:pos+0.1 中橙色,  # 漸層中間
    stop:pos+0.3 淡橙色,  # 漸層尾部
    stop:1 暗色)
```

右轉燈（從左向右）:
```python
qlineargradient(x1:0, y1:0, x2:1, y2:0, ...)
```

## 視覺效果

### 關閉狀態
```
┌────────┐          ┌────────┐
│   ◀   │          │   ▶   │
└────────┘          └────────┘
  暗灰色              暗灰色
```

### 開啟狀態（漸層動畫）
```
┌────────┐          ┌────────┐
│ ▓▒░◀  │          │  ▶░▒▓ │
└────────┘          └────────┘
 刷過效果             刷過效果
```

## 整合到實際 CAN Bus

### 步驟 1: 識別 CAN 訊號

查找方向燈相關的 CAN 訊息：
- 訊息 ID
- 資料格式
- 位元定義

### 步驟 2: 解析 CAN 訊息

```python
def parse_turn_signal_can(data):
    """解析方向燈 CAN 訊息"""
    # 假設格式: Byte 0, Bit 0 = 左轉燈, Bit 1 = 右轉燈
    left_on = bool(data[0] & 0x01)
    right_on = bool(data[0] & 0x02)
    return left_on, right_on
```

### 步驟 3: 更新儀表板

```python
def on_can_frame(frame):
    if frame.arbitration_id == TURN_SIGNAL_ID:
        left_on, right_on = parse_turn_signal_can(frame.data)
        
        # 更新左轉燈
        if left_on:
            dashboard.set_turn_signal("left_on")
        else:
            dashboard.set_turn_signal("left_off")
        
        # 更新右轉燈
        if right_on:
            dashboard.set_turn_signal("right_on")
        else:
            dashboard.set_turn_signal("right_off")
```

## 優化建議

### 效能優化
1. **CSS 快取**: 預生成常用的漸層樣式
2. **更新節流**: 只在狀態改變時更新樣式
3. **GPU 加速**: 使用 Qt 的硬體加速渲染

### 視覺優化
1. **緩動函數**: 使用 ease-in-out 讓動畫更平滑
2. **發光效果**: 添加 box-shadow 模擬燈光
3. **顏色調整**: 根據實際車輛的方向燈顏色調整

### 功能擴充
1. **聲音回饋**: 添加方向燈的 "噠噠" 聲
2. **故障檢測**: 檢測閃爍頻率異常
3. **自動關閉**: 轉彎後自動關閉方向燈

## 故障排除

### 問題 1: 漸層動畫不流暢
**原因**: CPU 負載過高
**解決**: 降低更新頻率或使用更簡單的視覺效果

### 問題 2: CAN 訊號延遲
**原因**: CAN bus 頻寬不足或訊息優先級低
**解決**: 提高方向燈訊息的優先級

### 問題 3: 閃爍頻率不準確
**原因**: 系統時鐘不穩定
**解決**: 使用硬體計時器或調整 sleep 補償

## 參考資料

- 原廠維修手冊: 方向燈規格 85 BPM
- Qt 文件: QLinearGradient
- CAN bus 協議: ISO 11898
