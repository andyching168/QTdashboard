"""
速限查詢模組
根據 GPS 座標和行駛方向，查詢國道速限
"""
import csv
import math
import os
from typing import Optional, Tuple, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SpeedLimitLoader:
    """速限資料載入器"""
    
    def __init__(self):
        self._signs: List[dict] = []
        self._speed_rules: List[dict] = []  # 快取速限規則
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
            
            self._loaded = True
            print(f"[SpeedLimit] 載入 {len(self._signs)} 筆速限資料")
            
            # 載入速限規則到記憶體
            self._load_speed_rules()
            
        except Exception as e:
            print(f"[SpeedLimit] 載入失敗: {e}")
    
    def _load_speed_rules(self):
        """將速限規則載入記憶體"""
        import re
        limits_path = os.path.join(PROJECT_ROOT, 'assets', 'docs', '國道速限資訊整理.csv')
        
        try:
            with open(limits_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    desc = row['路段']
                    limit = int(row['速限 (公里/小時)'])
                    route = row['路線']
                    
                    # 解析路線
                    hw_match = re.search(r'國(\d+)', route)
                    if not hw_match:
                        continue
                    hw_num = hw_match.group(1)
                    
                    # 解析里程標記
                    km_matches = re.findall(r'(\d+)K', desc)
                    has_range = len(km_matches) >= 2
                    start_km = int(km_matches[0]) if km_matches else None
                    end_km = int(km_matches[1]) if len(km_matches) >= 2 else None
                    
                    # 判斷方向類型
                    is_northsouth = '北上' in desc or '南下' in desc or '北向' in desc or '南向' in desc
                    is_eastwest = '東行' in desc or '西行' in desc
                    
                    self._speed_rules.append({
                        'route': route,
                        'hw_num': hw_num,
                        'limit': limit,
                        'desc': desc,
                        'has_range': has_range,
                        'start_km': start_km,
                        'end_km': end_km,
                        'is_northsouth': is_northsouth,
                        'is_eastwest': is_eastwest,
                    })
            
            print(f"[SpeedLimit] 載入 {len(self._speed_rules)} 筆速限規則")
            
        except Exception as e:
            print(f"[SpeedLimit] 載入速限規則失敗: {e}")
    
    def _parse_km(self, sign_id: str) -> Optional[float]:
        """解析里程牌號為公里數"""
        import re
        match = re.match(r'(\d+)K\+(.+)', sign_id)
        if match:
            km = int(match.group(1))
            offset = int(match.group(2))
            return km + offset / 1000
        return None
    
    def _simple_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """簡單距離估算（度到公里的近似轉換）"""
        return ((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5 * 111
    
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
            (速限值, 方向, 雙向速限dict) 或 (None, None, None) 如果找不到
            當 bearing=None 且路段有分方向時，速限值為 None，雙向速限dict 格式如 {"N": 100, "S": 90}
        """
        if not self._loaded or not self._signs:
            return None, None, None
        
        # 第一階段：用簡單距離快速篩選 top-20 候選
        candidates = []
        for sign in self._signs:
            simple_dist = self._simple_distance(lat, lon, sign['lat'], sign['lon'])
            if len(candidates) < 20:
                candidates.append((simple_dist, sign))
                candidates.sort(key=lambda x: x[0])
            elif simple_dist < candidates[-1][0]:
                candidates[-1] = (simple_dist, sign)
                candidates.sort(key=lambda x: x[0])
        
        # 第二階段：用精確 Haversine 在 top-20 中找最近
        best_sign = None
        best_distance = float('inf')
        
        for simple_dist, sign in candidates:
            precise_dist = self._calculate_distance(lat, lon, sign['lat'], sign['lon'])
            if precise_dist < best_distance:
                best_distance = precise_dist
                best_sign = sign
        
        if best_sign and best_distance < 0.5:  # 500m 內
            # 根據 highway 決定行駛方向（用於顯示，不影響速限）
            if bearing is not None:
                travel_direction = self._bearing_to_direction(bearing, best_sign['highway'])
                speed_limit = self._get_speed_limit_for_km(best_sign['km'], best_sign['highway'])
                if speed_limit is not None:
                    return speed_limit, travel_direction, None
                else:
                    return None, travel_direction, None
            else:
                dual_limits = self._get_dual_speed_limits(best_sign['km'], best_sign['highway'])
                if dual_limits and len(dual_limits) > 1:
                    return None, 'DUAL', dual_limits
                elif dual_limits:
                    if 'N' in dual_limits:
                        return dual_limits['N'], '北上', None
                    elif 'S' in dual_limits:
                        return dual_limits['S'], '南下', None
                    elif 'E' in dual_limits:
                        return dual_limits['E'], '東行', None
                    elif 'W' in dual_limits:
                        return dual_limits['W'], '西行', None
                else:
                    return None, best_sign['direction'], None
        
        return None, None, None
    
    def _get_dual_speed_limits(self, km: float, highway: str) -> Optional[dict]:
        """查詢雙向速限，回傳格式如 {"N": 100, "S": 90} 或 {"E": 100, "W": 90}"""
        import re
        
        try:
            highway_match = re.search(r'國道(\d+)[甲乙丙丁]?', highway)
            if not highway_match:
                return None
            
            hw_num = highway_match.group(1)
            route_targets = [f'國{hw_num}']
            if '甲' in highway or '乙' in highway:
                route_targets.append(f'國{hw_num}甲')
            
            is_eastwest = self._is_eastwest_highway(highway)
            
            if is_eastwest:
                east_limit = None
                west_limit = None
            else:
                north_limit = None
                south_limit = None
            
            for rule in self._speed_rules:
                if rule['route'] not in route_targets:
                    continue
                
                if rule['has_range']:
                    continue
                
                if is_eastwest:
                    if rule['is_northsouth']:
                        continue
                    if '以東' in rule['desc']:
                        if km >= rule['start_km'] and east_limit is None:
                            east_limit = rule['limit']
                    if '以西' in rule['desc']:
                        if km <= rule['start_km'] and west_limit is None:
                            west_limit = rule['limit']
                else:
                    if rule['is_eastwest']:
                        continue
                    if '以北' in rule['desc']:
                        if km >= rule['start_km'] and north_limit is None:
                            north_limit = rule['limit']
                    if '以南' in rule['desc']:
                        if km >= rule['start_km'] and south_limit is None:
                            south_limit = rule['limit']
            
            if is_eastwest:
                if east_limit is not None or west_limit is not None:
                    result = {}
                    if east_limit is not None:
                        result['E'] = east_limit
                    if west_limit is not None:
                        result['W'] = west_limit
                    return result if result else None
            else:
                if north_limit is not None or south_limit is not None:
                    result = {}
                    if north_limit is not None:
                        result['N'] = north_limit
                    if south_limit is not None:
                        result['S'] = south_limit
                    return result if result else None
            
            return None
            
        except Exception as e:
            print(f"[SpeedLimit] 查詢雙向速限失敗: {e}")
            return None
    
    def _get_speed_limit_for_km(self, km: float, highway: str) -> Optional[int]:
        """根據里程和國道查詢速限"""
        import re
        
        highway_prefixes = ['國道1', '國道2', '國道3', '國道4', '國道5', '國道6', '國道8', '國道10', '國道3甲', '省道']
        is_highway = any(prefix in highway for prefix in highway_prefixes)
        
        if not is_highway:
            return None
        
        try:
            highway_match = re.search(r'國道(\d+)[甲乙丙丁]?', highway)
            if not highway_match:
                return None
            
            hw_num = highway_match.group(1)
            route_targets = [f'國{hw_num}']
            if '甲' in highway or '乙' in highway:
                route_targets.append(f'國{hw_num}甲')
            
            applicable_limits = []
            
            for rule in self._speed_rules:
                if rule['route'] not in route_targets:
                    continue
                
                if '全線' in rule['desc']:
                    applicable_limits.append((rule['limit'], '全線', 0, None))
                    continue
                
                if rule['has_range']:
                    start_km = rule['start_km']
                    end_km = rule['end_km']
                    if start_km < km < end_km:
                        distance = min(abs(km - start_km), abs(km - end_km))
                        applicable_limits.append((rule['limit'], '範圍', distance, None))
                    continue
                
                if '全線' in rule['desc']:
                    applicable_limits.append((rule['limit'], '全線', 0))
                    continue
                
                if rule['has_range']:
                    start_km = rule['start_km']
                    end_km = rule['end_km']
                    if start_km < km < end_km:
                        distance = min(abs(km - start_km), abs(km - end_km))
                        applicable_limits.append((rule['limit'], '範圍', distance))
                    continue
                
                if '以北' in rule['desc']:
                    if km >= rule['start_km']:
                        distance = km - rule['start_km']
                        applicable_limits.append((rule['limit'], '里程', distance))
                elif '以南' in rule['desc']:
                    if km >= rule['start_km']:
                        distance = km - rule['start_km']
                        applicable_limits.append((rule['limit'], '里程', distance))
            
            if not applicable_limits:
                return None
            
            for limit, match_type, distance in applicable_limits:
                if match_type == '全線':
                    return limit
            
            for limit, match_type, distance in applicable_limits:
                if match_type == '範圍':
                    return limit
            
            best = min(applicable_limits, key=lambda x: x[2])
            return best[0]
            
        except Exception as e:
            print(f"[SpeedLimit] 查詢速限失敗: {e}")
            return None


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
