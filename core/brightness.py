"""
Brightness settings and Taiwan fixed sunrise/sunset helpers.
"""

import json
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple


TAIWAN_TZ = timezone(timedelta(hours=8))
TAIPEI_LAT = 25.0330
TAIPEI_LON = 121.5654
MIN_BRIGHTNESS_PERCENT = 10
MAX_BRIGHTNESS_PERCENT = 100


@dataclass(frozen=True)
class BrightnessSettings:
    default_percent: int = 100
    night_enabled: bool = False
    night_percent: int = 50


def get_config_dir() -> Path:
    """Return the dashboard config directory."""
    config_dir = Path(os.path.expanduser("~")) / ".config" / "qtdashboard"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_brightness_config_path() -> Path:
    """Return the brightness settings path."""
    return get_config_dir() / "brightness.json"


def clamp_brightness_percent(value) -> int:
    """Clamp a brightness value to a visible 10-100 percent range."""
    try:
        percent = int(value)
    except (TypeError, ValueError):
        percent = MAX_BRIGHTNESS_PERCENT
    return max(MIN_BRIGHTNESS_PERCENT, min(MAX_BRIGHTNESS_PERCENT, percent))


def load_brightness_settings(config_path: Optional[Path] = None) -> BrightnessSettings:
    """Load brightness settings, returning defaults when the file is absent or invalid."""
    path = Path(config_path) if config_path else get_brightness_config_path()
    if not path.exists():
        return BrightnessSettings()

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception as exc:
        print(f"[Brightness] 載入亮度設定失敗: {exc}")
        return BrightnessSettings()

    return BrightnessSettings(
        default_percent=clamp_brightness_percent(data.get("default_percent", 100)),
        night_enabled=bool(data.get("night_enabled", False)),
        night_percent=clamp_brightness_percent(data.get("night_percent", 50)),
    )


def save_brightness_settings(settings: BrightnessSettings, config_path: Optional[Path] = None) -> None:
    """Save brightness settings to disk."""
    path = Path(config_path) if config_path else get_brightness_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "default_percent": clamp_brightness_percent(settings.default_percent),
        "night_enabled": bool(settings.night_enabled),
        "night_percent": clamp_brightness_percent(settings.night_percent),
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)


def _solar_event_utc(day: date, latitude: float, longitude: float, is_sunrise: bool) -> Optional[datetime]:
    """Calculate sunrise or sunset UTC time using NOAA's compact solar approximation."""
    zenith = 90.833
    day_of_year = day.timetuple().tm_yday
    lng_hour = longitude / 15.0
    approx_time = day_of_year + ((6 if is_sunrise else 18) - lng_hour) / 24.0

    mean_anomaly = (0.9856 * approx_time) - 3.289
    true_long = (
        mean_anomaly
        + (1.916 * math.sin(math.radians(mean_anomaly)))
        + (0.020 * math.sin(math.radians(2 * mean_anomaly)))
        + 282.634
    ) % 360.0

    right_ascension = math.degrees(math.atan(0.91764 * math.tan(math.radians(true_long)))) % 360.0
    long_quadrant = math.floor(true_long / 90.0) * 90.0
    ra_quadrant = math.floor(right_ascension / 90.0) * 90.0
    right_ascension = (right_ascension + long_quadrant - ra_quadrant) / 15.0

    sin_dec = 0.39782 * math.sin(math.radians(true_long))
    cos_dec = math.cos(math.asin(sin_dec))
    cos_hour = (
        math.cos(math.radians(zenith))
        - (sin_dec * math.sin(math.radians(latitude)))
    ) / (cos_dec * math.cos(math.radians(latitude)))

    if cos_hour > 1 or cos_hour < -1:
        return None

    if is_sunrise:
        hour_angle = 360.0 - math.degrees(math.acos(cos_hour))
    else:
        hour_angle = math.degrees(math.acos(cos_hour))
    hour_angle /= 15.0

    local_mean_time = hour_angle + right_ascension - (0.06571 * approx_time) - 6.622
    utc_hour = (local_mean_time - lng_hour) % 24.0
    whole_hours = int(utc_hour)
    minutes_float = (utc_hour - whole_hours) * 60.0
    whole_minutes = int(minutes_float)
    seconds = int(round((minutes_float - whole_minutes) * 60.0))

    event_time = datetime.combine(day, time(0, tzinfo=timezone.utc))
    event_time += timedelta(hours=whole_hours, minutes=whole_minutes, seconds=seconds)
    return event_time


def get_taiwan_sunrise_sunset(day: date) -> Tuple[datetime, datetime]:
    """Return Taipei-based sunrise and sunset datetimes in Taiwan local time."""
    sunrise_utc = _solar_event_utc(day, TAIPEI_LAT, TAIPEI_LON, True)
    sunset_utc = _solar_event_utc(day, TAIPEI_LAT, TAIPEI_LON, False)
    if sunrise_utc is None or sunset_utc is None:
        raise ValueError("Unable to calculate sunrise/sunset for Taiwan fixed coordinates")

    def _to_requested_local_date(value: datetime) -> datetime:
        local_value = value.astimezone(TAIWAN_TZ)
        day_delta = (local_value.date() - day).days
        if day_delta:
            local_value -= timedelta(days=day_delta)
        return local_value

    return _to_requested_local_date(sunrise_utc), _to_requested_local_date(sunset_utc)


def is_taiwan_night(now: Optional[datetime] = None) -> bool:
    """Return True when the given Taiwan-local time is after sunset or before sunrise."""
    if now is None:
        now = datetime.now(TAIWAN_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=TAIWAN_TZ)
    else:
        now = now.astimezone(TAIWAN_TZ)

    sunrise, sunset = get_taiwan_sunrise_sunset(now.date())
    return now < sunrise or now >= sunset


def effective_brightness_percent(settings: BrightnessSettings, now: Optional[datetime] = None) -> int:
    """Resolve the brightness percent for current day/night state."""
    if settings.night_enabled and is_taiwan_night(now):
        return clamp_brightness_percent(settings.night_percent)
    return clamp_brightness_percent(settings.default_percent)
