"""
速限查詢模組
根據 GPS 座標和行駛方向，查詢國道速限

架構說明：
- 標誌點載入後建立經緯度網格索引（cell 0.01 度 ≈ 1.1 km），
  查詢只掃 3x3 鄰近 cell 的標誌，不再線性掃描全部資料
- 本模組為純 Python、無 Qt 相依；跨執行緒查詢請經由
  navigation.speed_limit_worker.SpeedLimitWorker
"""
import csv
import math
import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 網格索引 cell 大小（度）。0.01 度緯度 ≈ 1.11 km，在台灣緯度的經度 ≈ 1.0 km，
# 查 3x3 鄰域保證涵蓋 500m 搜尋半徑
_GRID_CELL_DEG = 0.01

_KM_SIGN_RE = re.compile(r'(\d+)K\+(.+)')
_ROUTE_NUM_RE = re.compile(r'國(\d+)([甲乙丙丁]?)')
_HIGHWAY_NUM_RE = re.compile(r'國道(\d+)([甲乙丙丁]?)')
_KM_MARK_RE = re.compile(r'(\d+)K(?:\+(\d+))?')


@dataclass(frozen=True)
class SpeedLimitRule:
    """一條可直接以里程判斷的速限規則。"""

    route: str
    limit: int
    description: str
    lower_km: Optional[float] = None
    upper_km: Optional[float] = None

    def matches(self, km: float) -> bool:
        return (
            (self.lower_km is None or km >= self.lower_km)
            and (self.upper_km is None or km <= self.upper_km)
        )

    @property
    def span(self) -> float:
        """較小的區間優先，讓具體規則覆蓋全線 fallback。"""
        if self.lower_km is None or self.upper_km is None:
            return float("inf")
        return self.upper_km - self.lower_km


class SpeedLimitLoader:
    """速限資料載入器"""

    def __init__(self):
        self._signs: List[dict] = []
        self._speed_rules: List[SpeedLimitRule] = []  # 快取速限規則
        self._grid: dict = {}  # (cell_lat, cell_lon) -> [sign, ...]
        self._loaded = False
        self._load_speed_limits()

    def _load_speed_limits(self):
        """載入速限資料"""
        csv_path = os.path.join(PROJECT_ROOT, 'assets', 'docs', '國道交通標誌位.csv')

        try:
            with open(csv_path, 'r', encoding='big5') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        lat = float(row['坐標Y-WGS84'])
                        lon = float(row['坐標X-WGS84'])
                        sign_id = row['牌面內容'].strip()
                        direction = row['方向與備註'].strip()
                        highway = row['國道編號'].strip()

                        # 解析里程 (從牌面內容如 "014K+100")
                        km = self._parse_km(sign_id)
                        if km is None:
                            continue

                        self._signs.append({
                            'lat': lat,
                            'lon': lon,
                            'km': km,
                            'highway': highway,
                            'direction': direction,
                            'sign_id': sign_id,
                        })
                    except (ValueError, KeyError):
                        continue

            self._build_grid_index()
            self._loaded = True
            print(f"[SpeedLimit] 載入 {len(self._signs)} 筆速限資料（網格索引 {len(self._grid)} cells）")

            # 載入速限規則到記憶體
            self._load_speed_rules()

        except Exception as e:
            print(f"[SpeedLimit] 載入失敗: {e}")

    def _build_grid_index(self):
        """建立標誌點的經緯度網格索引"""
        self._grid = {}
        for sign in self._signs:
            key = (int(sign['lat'] / _GRID_CELL_DEG), int(sign['lon'] / _GRID_CELL_DEG))
            self._grid.setdefault(key, []).append(sign)

    def _candidates_near(self, lat: float, lon: float) -> List[dict]:
        """取出查詢點 3x3 鄰近 cell 內的所有標誌"""
        cell_lat = int(lat / _GRID_CELL_DEG)
        cell_lon = int(lon / _GRID_CELL_DEG)
        candidates = []
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                candidates.extend(self._grid.get((cell_lat + di, cell_lon + dj), ()))
        return candidates

    def _load_speed_rules(self):
        """將速限規則載入記憶體"""
        limits_path = os.path.join(PROJECT_ROOT, 'assets', 'docs', '國道速限資訊整理.csv')

        try:
            with open(limits_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    desc = row['路段']
                    limit = int(row['速限 (公里/小時)'])
                    route = row['路線']

                    normalized_route = self._normalize_route(route)
                    rule = self._parse_speed_rule(normalized_route, limit, desc)
                    if rule is not None:
                        self._speed_rules.append(rule)

            print(f"[SpeedLimit] 載入 {len(self._speed_rules)} 筆速限規則")

        except Exception as e:
            print(f"[SpeedLimit] 載入速限規則失敗: {e}")

    @staticmethod
    def _km_from_match(match: Tuple[str, str]) -> float:
        km, offset = match
        return int(km) + (int(offset) / 1000 if offset else 0)

    def _normalize_route(self, route: str) -> Optional[str]:
        match = _ROUTE_NUM_RE.search(route)
        if not match:
            return None
        return f"國{match.group(1)}{match.group(2)}"

    def _parse_speed_rule(self, route: Optional[str], limit: int, desc: str) -> Optional[SpeedLimitRule]:
        """把 CSV 的地理描述正規化成封閉公里區間。

        「以北／以西」是較小里程，「以南／以東」是較大里程；它們描述
        地理位置，並非行駛方向，因此不應被轉換成 N/S/E/W 雙向速限。
        """
        if not route:
            return None

        markers = [self._km_from_match(match) for match in _KM_MARK_RE.findall(desc)]
        if '全線' in desc:
            return SpeedLimitRule(route, limit, desc)
        if len(markers) >= 2:
            lower, upper = sorted(markers[:2])
            return SpeedLimitRule(route, limit, desc, lower, upper)
        if len(markers) != 1:
            print(f"[SpeedLimit] 無法解析速限規則: {route} {desc}")
            return None

        marker = markers[0]
        if '以北' in desc or '以西' in desc:
            return SpeedLimitRule(route, limit, desc, upper_km=marker)
        if '以南' in desc or '以東' in desc:
            return SpeedLimitRule(route, limit, desc, lower_km=marker)

        print(f"[SpeedLimit] 未知速限規則類型: {route} {desc}")
        return None

    def _parse_km(self, sign_id: str) -> Optional[float]:
        """解析里程牌號為公里數"""
        match = _KM_SIGN_RE.match(sign_id)
        if match:
            km = int(match.group(1))
            offset = int(match.group(2))
            return km + offset / 1000
        return None

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """計算兩點間 Haversine 距離（公里）"""
        R = 6371  # 地球半徑（公里）

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = math.sin(delta_lat / 2) ** 2 + \
            math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def _is_eastwest_highway(self, highway: str) -> bool:
        """判斷是否為東西向國道"""
        ew_highways = ['國道2', '國道3甲', '國道4', '國道6', '國道8', '國道10']
        return any(hw in highway for hw in ew_highways)

    def _bearing_to_direction(self, bearing: float, highway: str) -> Optional[str]:
        """將羅盤方向轉換為行駛方向"""
        if self._is_eastwest_highway(highway):
            if 45 <= bearing < 135:
                return '東行'
            elif 225 <= bearing < 315:
                return '西行'
            else:
                return None  # 無法明確判斷方向
        else:
            diff = abs(bearing - 180)
            if diff < 90:
                return '南下'
            elif diff > 90:
                return '北上'
            else:
                return '北上' if bearing < 180 else '南下'

    def query(self, lat: float, lon: float, bearing: Optional[float] = None) -> Tuple[Optional[int], Optional[str], Optional[dict]]:
        """
        查詢速限

        Args:
            lat: 緯度
            lon: 經度
            bearing: 行駛方向角 (0-360)，可為 None

        Returns:
            (速限值, 行駛方向, None) 或 (None, None, None) 如果找不到。
            CSV 的「以北／以南／以東／以西」是地理區間，不是雙向車道規則。
        """
        if not self._loaded or not self._signs:
            return None, None, None

        # 網格索引取出鄰近標誌（通常數十筆），直接以 Haversine 找最近
        best_sign = None
        best_distance = float('inf')
        for sign in self._candidates_near(lat, lon):
            dist = self._calculate_distance(lat, lon, sign['lat'], sign['lon'])
            if dist < best_distance:
                best_distance = dist
                best_sign = sign

        if best_sign and best_distance < 0.5:  # 500m 內
            travel_direction = (
                self._bearing_to_direction(bearing, best_sign['highway'])
                if bearing is not None else best_sign['direction']
            )
            speed_limit = self._get_speed_limit_for_km(best_sign['km'], best_sign['highway'])
            return speed_limit, travel_direction, None

        return None, None, None

    def _route_targets(self, highway: str) -> Optional[List[str]]:
        """將標誌的國道編號轉為速限規則的路線代碼（如 國道1 -> ['國1']）"""
        highway_match = _HIGHWAY_NUM_RE.search(highway)
        if not highway_match:
            return None

        return [f"國{highway_match.group(1)}{highway_match.group(2)}"]

    def _get_speed_limit_for_km(self, km: float, highway: str) -> Optional[int]:
        """根據里程和國道查詢速限。"""
        route_targets = self._route_targets(highway)
        if not route_targets:
            return None

        applicable = [
            rule for rule in self._speed_rules
            if rule.route in route_targets and rule.matches(km)
        ]
        if not applicable:
            return None

        return min(applicable, key=lambda rule: rule.span).limit


# 單例
_speed_limit_loader: Optional[SpeedLimitLoader] = None


def get_speed_limit_loader() -> SpeedLimitLoader:
    global _speed_limit_loader
    if _speed_limit_loader is None:
        _speed_limit_loader = SpeedLimitLoader()
    return _speed_limit_loader


def query_speed_limit(lat: float, lon: float, bearing: Optional[float] = None) -> Tuple[Optional[int], Optional[str], Optional[dict]]:
    """快速查詢速限，回傳 (速限, 方向, 雙向速限dict)"""
    loader = get_speed_limit_loader()
    return loader.query(lat, lon, bearing)
