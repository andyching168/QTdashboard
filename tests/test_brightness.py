from datetime import datetime

from core.brightness import (
    BrightnessSettings,
    TAIWAN_TZ,
    clamp_brightness_percent,
    effective_brightness_percent,
    get_taiwan_sunrise_sunset,
    is_taiwan_night,
    load_brightness_settings,
    save_brightness_settings,
)


def test_brightness_defaults_when_config_missing(tmp_path):
    settings = load_brightness_settings(tmp_path / "missing.json")

    assert settings == BrightnessSettings()


def test_brightness_settings_roundtrip_and_clamp(tmp_path):
    config_path = tmp_path / "brightness.json"
    save_brightness_settings(
        BrightnessSettings(default_percent=150, night_enabled=True, night_percent=1),
        config_path,
    )

    settings = load_brightness_settings(config_path)

    assert settings.default_percent == 100
    assert settings.night_enabled is True
    assert settings.night_percent == 10


def test_clamp_brightness_percent():
    assert clamp_brightness_percent("bad") == 100
    assert clamp_brightness_percent(5) == 10
    assert clamp_brightness_percent(75) == 75
    assert clamp_brightness_percent(120) == 100


def test_taiwan_fixed_sunrise_sunset_order():
    sunrise, sunset = get_taiwan_sunrise_sunset(datetime(2026, 7, 5, tzinfo=TAIWAN_TZ).date())

    assert sunrise.tzinfo == TAIWAN_TZ
    assert sunset.tzinfo == TAIWAN_TZ
    assert sunrise < sunset


def test_taiwan_day_night_detection():
    noon = datetime(2026, 7, 5, 12, 0, tzinfo=TAIWAN_TZ)
    night = datetime(2026, 7, 5, 23, 0, tzinfo=TAIWAN_TZ)

    assert is_taiwan_night(noon) is False
    assert is_taiwan_night(night) is True


def test_effective_brightness_uses_night_setting_only_when_enabled():
    noon = datetime(2026, 7, 5, 12, 0, tzinfo=TAIWAN_TZ)
    night = datetime(2026, 7, 5, 23, 0, tzinfo=TAIWAN_TZ)
    settings = BrightnessSettings(default_percent=80, night_enabled=True, night_percent=35)

    assert effective_brightness_percent(settings, noon) == 80
    assert effective_brightness_percent(settings, night) == 35
    assert effective_brightness_percent(
        BrightnessSettings(default_percent=80, night_enabled=False, night_percent=35),
        night,
    ) == 80
