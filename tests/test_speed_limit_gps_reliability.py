from core.gps_reliability import is_speed_limit_gps_reliable


def test_speed_limit_allows_internal_fixed_gps():
    assert is_speed_limit_gps_reliable(
        is_fixed=True,
        is_using_external_gps=False,
    )


def test_speed_limit_rejects_external_mqtt_gps_even_when_fresh_and_fixed():
    assert not is_speed_limit_gps_reliable(
        is_fixed=True,
        is_using_external_gps=True,
    )


def test_speed_limit_rejects_unfixed_internal_gps():
    assert not is_speed_limit_gps_reliable(
        is_fixed=False,
        is_using_external_gps=False,
    )
