"""GPS 來源可靠度判斷。"""


def is_speed_limit_gps_reliable(is_fixed: bool, is_using_external_gps: bool) -> bool:
    """速限顯示只允許內建 GPS fix。

    MQTT/外部 GPS 可能是手機、導航或最後位置，精確度與所在車道都不穩定；
    這類來源可用於定位輔助，但不能用來顯示限速。
    """
    return bool(is_fixed) and not bool(is_using_external_gps)
