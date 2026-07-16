"""速限規則與實際標誌座標的回歸測試。"""
import pytest

from navigation.speed_limit import SpeedLimitLoader


@pytest.fixture(scope="module")
def loader():
    return SpeedLimitLoader()


@pytest.mark.parametrize(
    ("highway", "km", "expected_limit"),
    [
        ("國道1號", 50.0, 100),
        ("國道2號", 0.5, 80),
        ("國道2號", 5.0, 100),
        ("國道3號", 20.0, 90),
        ("國道5號", 10.0, 80),
        ("國道5號", 20.0, 90),
    ],
)
def test_query_uses_geographic_rule_for_actual_sign(loader, highway, km, expected_limit):
    """每一組都直接使用 CSV 中最接近目標里程的實際標誌座標。"""
    sign = min(
        (item for item in loader._signs if item["highway"] == highway),
        key=lambda item: abs(item["km"] - km),
    )

    limit, _direction, dual_limits = loader.query(sign["lat"], sign["lon"], bearing=0)

    assert sign["km"] == km
    assert limit == expected_limit
    assert dual_limits is None


@pytest.mark.parametrize(
    ("highway", "km", "expected_limit"),
    [
        ("國道1號", 154.449, 100),
        ("國道1號", 154.451, 110),
        ("國道3號", 34.999, 90),
        ("國道3號", 35.0, 100),
        ("國道3號", 35.001, 100),
        ("國道4號", 0.0, 100),
    ],
)
def test_rule_boundaries_and_full_route(loader, highway, km, expected_limit):
    assert loader._get_speed_limit_for_km(km, highway) == expected_limit


def test_unknown_road_has_no_speed_limit(loader):
    assert loader._get_speed_limit_for_km(10.0, "省道台2己") is None
