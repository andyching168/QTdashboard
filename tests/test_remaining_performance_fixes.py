import inspect
import json
import os
import weakref
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication


_APP = None


def qapp():
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


def reset_marquee_state(MarqueeLabel):
    timer = MarqueeLabel._shared_timer
    if timer is not None and timer.isActive():
        timer.stop()
    MarqueeLabel._shared_timer = None
    MarqueeLabel._instances = weakref.WeakSet()
    MarqueeLabel._global_pause_counter = 0
    MarqueeLabel._waiting_for_sync = False


def test_marquee_uses_shared_timer_and_cached_metrics():
    qapp()
    from ui.common import MarqueeLabel

    reset_marquee_state(MarqueeLabel)
    label = MarqueeLabel("very long song title " * 8)
    label.resize(40, 24)
    label._activate()

    assert not hasattr(label, "_timer")
    assert MarqueeLabel._shared_timer is not None
    assert MarqueeLabel._shared_timer.isActive()
    assert label._text_width > 0
    assert label._cycle_width == label._text_width + MarqueeLabel._scroll_gap

    cached_width = label._text_width
    label._tick_scroll()
    assert label._text_width == cached_width

    label._deactivate()
    assert not MarqueeLabel._shared_timer.isActive()


def test_door_update_display_uses_pre_scaled_pixmaps():
    from ui.door_card import DoorStatusCard

    source = inspect.getsource(DoorStatusCard.update_display)
    assert ".scaled(" not in source
    assert "setPixmap(self.fl_handle_pixmap)" in source
    assert "setPixmap(self.bk_open_pixmap)" in source


def test_analog_gauge_reuses_static_cache_for_same_geometry():
    qapp()
    from ui.analog_gauge import AnalogGauge
    from ui.common import GaugeStyle

    gauge = AnalogGauge(0, 100, GaugeStyle(), title="FUEL")
    gauge.resize(300, 300)
    gauge._ensure_static_cache(300, 300, 300)
    first_cache = gauge._static_cache

    gauge._ensure_static_cache(300, 300, 300)
    assert gauge._static_cache is first_cache

    gauge.invalidate_static_cache()
    assert gauge._static_cache is None


def test_gear_dirty_check_helper():
    from vehicle.datagrab import should_emit_gear_update

    assert should_emit_gear_update("D", None)
    assert not should_emit_gear_update("D", "D")
    assert should_emit_gear_update("N", "D")


def test_spotify_timeout_is_passed_to_oauth_and_client(monkeypatch, tmp_path):
    from spotify import spotify_auth
    from spotify.spotify_auth import SpotifyAuthManager

    config_path = tmp_path / "spotify_config.json"
    config_path.write_text(
        json.dumps({
            "client_id": "cid",
            "client_secret": "secret",
            "redirect_uri": "http://localhost:8888/callback",
        }),
        encoding="utf-8",
    )
    oauth_kwargs = {}
    spotify_kwargs = {}

    class FakeOAuth:
        def __init__(self, **kwargs):
            oauth_kwargs.update(kwargs)

    class FakeSpotify:
        def __init__(self, **kwargs):
            spotify_kwargs.update(kwargs)

    monkeypatch.setattr(spotify_auth, "DashboardSpotifyOAuth", FakeOAuth)
    monkeypatch.setattr(spotify_auth, "Spotify", FakeSpotify)

    manager = SpotifyAuthManager(
        config_path=str(config_path),
        cache_path=str(tmp_path / ".spotify_cache"),
    )
    oauth = manager._create_oauth_manager()
    client = manager._create_spotify_client(oauth)

    assert isinstance(oauth, FakeOAuth)
    assert isinstance(client, FakeSpotify)
    assert oauth_kwargs["requests_timeout"] == 10
    assert spotify_kwargs["requests_timeout"] == 10


def test_spotify_timeout_falls_back_for_old_spotipy(monkeypatch, tmp_path):
    from spotify import spotify_auth
    from spotify.spotify_auth import SpotifyAuthManager

    config_path = tmp_path / "spotify_config.json"
    config_path.write_text(
        json.dumps({
            "client_id": "cid",
            "client_secret": "secret",
            "redirect_uri": "http://localhost:8888/callback",
        }),
        encoding="utf-8",
    )
    oauth_calls = []
    spotify_calls = []

    class FakeOAuth:
        def __init__(self, **kwargs):
            oauth_calls.append(kwargs)
            if "requests_timeout" in kwargs:
                raise TypeError("unexpected keyword")

    class FakeSpotify:
        def __init__(self, **kwargs):
            spotify_calls.append(kwargs)
            if "requests_timeout" in kwargs:
                raise TypeError("unexpected keyword")

    monkeypatch.setattr(spotify_auth, "DashboardSpotifyOAuth", FakeOAuth)
    monkeypatch.setattr(spotify_auth, "Spotify", FakeSpotify)

    manager = SpotifyAuthManager(
        config_path=str(config_path),
        cache_path=str(tmp_path / ".spotify_cache"),
    )
    oauth = manager._create_oauth_manager()
    client = manager._create_spotify_client(oauth)

    assert isinstance(oauth, FakeOAuth)
    assert isinstance(client, FakeSpotify)
    assert "requests_timeout" in oauth_calls[0]
    assert "requests_timeout" not in oauth_calls[1]
    assert "requests_timeout" in spotify_calls[0]
    assert "requests_timeout" not in spotify_calls[1]


def test_dashboard_turbo_dirty_check_skips_small_changes():
    from main import Dashboard

    emitted = []
    dashboard = SimpleNamespace(
        turbo=1.0,
        signal_update_turbo=SimpleNamespace(emit=emitted.append),
        _in_detail_view=False,
        _detail_gauge_index=0,
    )

    Dashboard.set_turbo(dashboard, 1.004)
    assert emitted == []
    assert dashboard.turbo == 1.0

    Dashboard.set_turbo(dashboard, 1.02)
    assert emitted == [1.02]
    assert dashboard.turbo == 1.02


def test_dashboard_close_event_cleans_major_runtime_resources():
    from main import Dashboard

    source = inspect.getsource(Dashboard.prepare_for_exit)
    for name in (
        "network_monitor",
        "speed_limit_worker",
        "gps_monitor_thread",
        "radar_monitor_thread",
        "spotify_controller",
        "mqtt_controller",
        "jank_detector",
    ):
        assert name in source
