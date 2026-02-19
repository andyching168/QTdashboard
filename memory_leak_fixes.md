# 記憶體洩漏修正方案

## 問題診斷

你遇到的問題：程式在高溫時卡頓，即使溫度降下來依然卡頓，但重啟程式就恢復正常。

**這是典型的記憶體/資源累積問題，而非純粹溫度問題。**

## 發現的問題

### 1. Python GC 閾值設定過高 (main.py:19)
```python
# 目前設定
gc.set_threshold(50000, 500, 100)  # 太高！

# 建議改為
gc.set_threshold(2000, 50, 20)  # 更頻繁地回收垃圾
```

**影響**：閾值太高會導致垃圾回收延遲，記憶體持續累積。在樹莓派高溫 throttle 時，GC 更晚觸發，卡頓更嚴重。

### 2. QTimer 閃爍定時器洩漏 (main.py:1402-1414)

**問題代碼**：
```python
def _update_flash(self, index, is_danger, danger_color):
    timer = self._flash_timers[index]
    
    if not is_danger:
        if timer:
            timer.stop()
            self._flash_timers[index] = None  # ❌ 沒有 deleteLater()
            # ...
```

**修正**：
```python
def _update_flash(self, index, is_danger, danger_color):
    timer = self._flash_timers[index]
    
    if not is_danger:
        if timer:
            timer.stop()
            timer.deleteLater()  # ✅ 正確清理
            self._flash_timers[index] = None
            # ...
```

### 3. MarqueeLabel 定時器未清理

**問題**：當 widget 被銷毀時，QTimer 可能還在運行。

**修正**：添加清理邏輯
```python
def __del__(self):
    """確保定時器被停止"""
    if hasattr(self, '_timer') and self._timer:
        self._timer.stop()
        self._timer.deleteLater()

def closeEvent(self, event):
    """視窗關閉時清理"""
    if hasattr(self, '_timer') and self._timer:
        self._timer.stop()
    super().closeEvent(event)
```

### 4. datagrab.py 的 deque 可能無限增長

**檢查**：`slow_calls = deque(maxlen=100)` (main.py:90) - 這個有設定上限，沒問題。

但 `fuel_samples = []` (datagrab.py:517) 需要檢查：
```python
# datagrab.py:779
fuel_samples.append(fuel_raw)
if len(fuel_samples) > fuel_sample_size:
    fuel_samples.pop(0)  # ✅ 有限制，沒問題
```

### 5. 週期性強制 GC (新增機制)

在 Dashboard 的 `_physics_tick` 中添加定期強制回收：

```python
def _physics_tick(self):
    # 原有邏輯...
    
    # 每 5 分鐘強制 GC 一次
    current_time = time.time()
    if not hasattr(self, '_last_gc_time'):
        self._last_gc_time = current_time
    
    if current_time - self._last_gc_time >= 300:  # 5分鐘
        gc.collect()
        self._last_gc_time = current_time
        logger.debug("強制垃圾回收完成")
```

## 快速修正步驟

### Step 1: 調整 GC 閾值
編輯 `main.py` 第 19 行：
```python
gc.set_threshold(2000, 50, 20)  # 從 (50000, 500, 100) 改為此值
```

### Step 2: 修正 QuadGaugeCard 的 flash timer
在 `main.py` 約 1390-1393 行添加 `deleteLater()`：
```python
if timer:
    timer.stop()
    timer.deleteLater()  # 添加這行
    self._flash_timers[index] = None
```

### Step 3: 修正 MarqueeLabel
在 `main.py` 約 4128-4132 行修改 `__del__` 方法：
```python
def __del__(self):
    """清理定時器和實例引用"""
    if hasattr(self, '_timer') and self._timer:
        if self._timer.isActive():
            self._timer.stop()
        self._timer.deleteLater()
```

### Step 4: 添加定期 GC（可選但建議）

在 Dashboard 類別的 `_physics_tick` 方法最後添加：
```python
# 每 5 分鐘強制 GC
if not hasattr(self, '_last_gc_time'):
    self._last_gc_time = time.time()
elif time.time() - self._last_gc_time >= 300:
    collected = gc.collect()
    self._last_gc_time = time.time()
    if collected > 0:
        logger.debug(f"強制 GC 回收了 {collected} 個物件")
```

## 測試方法

1. **模擬高溫環境**：
   ```bash
   # 限制 CPU 頻率模擬高溫 throttle
   sudo cpufreq-set -u 1.0GHz
   ```

2. **監控記憶體使用**：
   ```bash
   watch -n 1 'ps aux | grep python'
   ```

3. **長時間運行測試**：讓程式運行 1-2 小時，觀察記憶體是否持續增長。

4. **查看 GC 統計**：
   在程式中添加日誌：
   ```python
   import gc
   logger.info(f"GC 統計: {gc.get_stats()}")
   logger.info(f"GC 計數: {gc.get_count()}")
   ```

## 預期效果

- ✅ 記憶體不再持續增長
- ✅ 高溫時卡頓減少（GC 更頻繁但單次時間更短）
- ✅ 長時間運行後不需要重啟

## 進階偵錯（如果問題仍存在）

使用 `tracemalloc` 追蹤記憶體：
```python
import tracemalloc

# 在程式開頭
tracemalloc.start()

# 定期輸出記憶體快照
def print_memory_snapshot():
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')
    
    print("[ Top 10 記憶體使用 ]")
    for stat in top_stats[:10]:
        print(stat)

# 在 Dashboard 的定時器中每 10 分鐘呼叫一次
```

## 其他建議

1. **減少日誌輸出**：過多的日誌會佔用記憶體和 I/O
2. **檢查 Spotify 圖片快取**：如果專輯封面未限制快取大小，會持續增長
3. **使用 `slots`**：在高頻創建的類別使用 `__slots__` 減少記憶體

