# 速限查詢系統技術文件

## 概述

速限查詢系統根據 GPS 座標和行駛方向，即時查詢國道速限資訊。

## 資料來源

### 速限標誌位置
- **檔案**: `assets/docs/國道交通標誌位.csv` (Big5 編碼)
- **內容**: 25,616 筆速限標誌位置資料
- **欄位**:
  - `坐標Y-WGS84`: 緯度
  - `坐標X-WGS84`: 經度
  - `牌面內容`: 里程牌號 (如 `014K+100`)
  - `國道編號`: 國道名稱
  - `方向與備註`: 方向 (北上/南下/東行/西行)

### 速限規則
- **檔案**: `assets/docs/國道速限資訊整理.csv` (UTF-8 編碼)
- **內容**: 20 筆速限規則
- **範例**:
  ```
  國3,中和交流道(35K)以北,90
  國3,中和交流道(35K)至土城交流道(43K),100
  國3,土城交流道(43K)以南,110
  ```

## 核心演算法

### 1. 距離計算

使用兩階段距離計算優化效能：

```python
# 第一階段：簡單距離估算（快速預篩選）
def _simple_distance(self, lat1, lon1, lat2, lon2):
    return ((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5 * 111

# 第二階段：Haversine 精確計算（top-20 候選確認）
def _calculate_distance(self, lat1, lon1, lat2, lon2):
    R = 6371  # 地球半徑
    # ... Haversine 公式
```

**效能提升**: ~15ms → ~7ms (2x 加速)

### 2. 行駛方向判斷

根據國道類型采用不同的方向邏輯：

```python
def _bearing_to_direction(self, bearing, highway):
    if self._is_eastwest_highway(highway):
        # 東西向國道 (2, 3甲, 4, 6, 8, 10)
        if 45 <= bearing < 135:
            return '東行'
        elif 225 <= bearing < 315:
            return '西行'
        else:
            return None  # 無法明確判斷
    else:
        # 南北向國道 (1, 3, 5)
        diff = abs(bearing - 180)
        if diff < 90:
            return '南下'
        elif diff > 90:
            return '北上'
        else:
            return '北上' if bearing < 180 else '南下'
```

### 3. 速限匹配優先級

1. **全線** (最高優先)
2. **範圍** (xxx至yyy)
3. **邊界方向規則** (xxx以北/以南)

```python
# 範例：國3 35K 位置
"35K以北" -> 北上=90
"35K至43K" -> 100 (範圍)
"43K以南" -> 南下=110

# 在 35K 邊界點，方向規則優先於範圍
```

## 速限顯示邏輯

### 回傳格式

```python
(速限值, 行駛方向, 雙向速限dict)
```

範例：
- `(90, '北上', None)` - 單一速限
- `(None, 'DUAL', {'N': 90, 'S': 110})` - 雙向速限顯示

### 雙向速限

當 bearing=None 且南北速限不同時，回傳 DUAL 格式：
```
N:90 / S:110
```

此模式閃爍功能會停用。

## GPS 狀態整合

### GPS 狀態燈號

| 狀態 | 條件 | 顏色 | 速限顯示 |
|------|------|------|----------|
| 內部 GPS | is_gps_fixed=True | 綠 | 顯示 |
| MQTT GPS (新鮮) | is_gps_fixed=True, is_external_gps_fresh=True | 黃 | 顯示 |
| MQTT GPS (過時) | is_gps_fixed=False | 灰 | **隱藏** |
| 無裝置 | gps_device_found=False | 紅 | 隱藏 |

### 外部 GPS 注入

當內部 GPS 未定位時，接收 MQTT 導航 payload 的 GPS 資料：

```python
# threads.py
def inject_external_gps(self, lat, lon, speed, bearing, timestamp):
    # 30 秒內：視為 fresh，is_gps_fixed=True
    # 30 秒 - 5 分鐘：stale，is_gps_fixed=False
    # 超過 5 分鐘：忽略
```

## 查詢頻率控制

速限查詢由獨立計時器控制，每 5 秒查詢一次：

```python
self.speed_limit_query_timer = QTimer()
self.speed_limit_query_timer.timeout.connect(self._update_speed_limit)
self.speed_limit_query_timer.start(5000)  # 5 秒

# GPS 狀態改變時控制計時器
if is_fixed:
    speed_limit_query_timer.start()   # 開始查詢
else:
    speed_limit_query_timer.stop()    # 停止查詢
```

## 效能優化總結

| 優化項目 | 優化前 | 優化後 |
|----------|--------|--------|
| CSV 讀取 | 每次查詢讀取 | 開機一次性載入記憶體 |
| 距離計算 | 25,616 次 Haversine | 25,616 次簡單估算 + 20 次 Haversine |
| 查詢頻率 | 每秒數次 | 每 5 秒一次 |
| CPU 佔用 | 高 | ~0.14% |

## 資料檔案格式

### 國道速限資訊整理.csv

```csv
路線,路段,速限 (公里/小時),備註
國1,大安溪橋(154K+450)以北,100,南向0K+500以北速限60 北向371K+620以南速限60
國1,大安溪橋(154K+450)至楠梓交流道(356K),110,
國3,中和交流道(35K)以北,90,
國3,中和交流道(35K)至土城交流道(43K),100,
國3,土城交流道(43K)以南,110,
```

### 支援的國道

| 國道 | 類型 | 方向 |
|------|------|------|
| 國道1 | 南北向 | 北上/南下 |
| 國道2 | 東西向 | 東行/西行 |
| 國道3 | 南北向 | 北上/南下 |
| 國道3甲 | 東西向 | 東行/西行 |
| 國道4 | 東西向 | 東行/西行 |
| 國道5 | 南北向 | 北上/南下 |
| 國道6 | 東西向 | 東行/西行 |
| 國道8 | 東西向 | 東行/西行 |
| 國道10 | 東西向 | 東行/西行 |

## 已知限制

1. **省道速限**: 目前未支援省道的速限查詢
2. **國道1 北部**: 速限資料僅有南部區間 (大安溪橋以北)
3. **方向判斷**: 當 bearing 無法明確判斷方向時 (如 bearing=90 on 南北向國道)，回傳 None
