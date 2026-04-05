#!/usr/bin/env python3
"""
速限查詢功能測試
"""
from navigation.speed_limit import query_speed_limit, get_speed_limit_loader


def test_speed_limit():
    """測試速限查詢功能"""
    loader = get_speed_limit_loader()
    print(f"Loaded {len(loader._signs)} speed limit signs\n")
    
    # 測試案例
    tests = [
        # (lat, lon, bearing, expected_desc)
        (24.985379, 121.474948, None, "國道3號 37K 附近"),
        (25.0330, 121.5654, None, "台北市區 (非國道)"),
        (25.016681, 121.472560, None, "未知位置"),
        # 國道1號
        (25.0795, 121.5570, None, "國道1號"),
    ]
    
    print("=== 速限查詢測試 ===\n")
    
    for lat, lon, bearing, desc in tests:
        limit = query_speed_limit(lat, lon, bearing)
        result = f"{limit} km/h" if limit else "None (不顯示)"
        print(f"{desc}: {result}")
        
        if bearing is not None:
            limit_bearing = query_speed_limit(lat, lon, bearing)
            result_bearing = f"{limit_bearing} km/h" if limit_bearing else "None"
            print(f"  (with bearing={bearing}): {result_bearing}")
        print()
    
    print("=== 完成 ===")


if __name__ == "__main__":
    test_speed_limit()
