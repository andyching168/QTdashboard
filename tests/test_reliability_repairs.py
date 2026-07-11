"""車用可靠度修復的純軟體回歸測試。"""
import importlib
import json
import sys
import time
from types import SimpleNamespace


class DistanceRecorder:
    def __init__(self):
        self.distance = 0.0

    def add_distance(self, value):
        self.distance += value


def _physics_dashboard(last_speed=0.0):
    return SimpleNamespace(
        last_physics_time=time.time() - 0.1,
        calc_speed_source=last_speed,
        trip_card=DistanceRecorder(),
        odo_card=DistanceRecorder(),
        trip_info_card=DistanceRecorder(),
    )


def test_physics_tick_integrates_fresh_obd_speed(monkeypatch):
    from main import Dashboard
    import vehicle.datagrab as datagrab

    monkeypatch.setattr(datagrab, "get_obd_speed_snapshot", lambda: (60.0, time.time()))
    dashboard = _physics_dashboard()

    Dashboard._physics_tick(dashboard)

    assert dashboard.trip_card.distance > 0
    assert dashboard.odo_card.distance == dashboard.trip_card.distance
    assert dashboard.trip_info_card.distance == dashboard.trip_card.distance


def test_physics_tick_stops_on_stale_obd_speed(monkeypatch):
    from main import Dashboard
    import vehicle.datagrab as datagrab

    monkeypatch.setattr(datagrab, "get_obd_speed_snapshot", lambda: (60.0, time.time() - 2.0))
    dashboard = _physics_dashboard(last_speed=60.0)
    dashboard._prev_physics_speed = 60.0

    Dashboard._physics_tick(dashboard)

    assert dashboard.trip_card.distance == 0
    assert dashboard._prev_physics_speed == 0.0


def test_speed_modes_calculate_expected_obd_display_speed(monkeypatch):
    from vehicle import datagrab

    monkeypatch.setattr(datagrab, "_speed_correction_value", 1.01)

    assert datagrab.calculate_obd_display_speed(100.0, "calibrated") == 101.0
    assert datagrab.calculate_obd_display_speed(100.0, "fixed") == 105.8
    assert datagrab.calculate_obd_display_speed(100.0, "gps") == 101.0


def test_speed_settings_roundtrip_and_legacy_fallback(tmp_path, monkeypatch):
    from vehicle import datagrab

    config_path = tmp_path / "speed_calibration.json"
    monkeypatch.setattr(datagrab, "_speed_correction_value", 1.07)
    monkeypatch.setattr(datagrab, "speed_sync_mode", "gps")
    monkeypatch.setattr(datagrab, "gps_speed_mode", True)

    datagrab.persist_speed_settings(str(config_path))
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["speed_correction"] == 1.07
    assert payload["speed_sync_mode"] == "gps"

    config_path.write_text('{"speed_correction": 0.98}', encoding="utf-8")
    assert datagrab._load_speed_settings(config_path=str(config_path)) == (0.98, "calibrated")
    assert datagrab.gps_speed_mode is False


def test_invalid_speed_settings_fall_back_to_defaults(tmp_path, monkeypatch):
    from vehicle import datagrab

    config_path = tmp_path / "speed_calibration.json"
    config_path.write_text('{"speed_correction": 1.02, "speed_sync_mode": "bad"}', encoding="utf-8")
    monkeypatch.setattr(datagrab, "speed_sync_mode", "gps")
    monkeypatch.setattr(datagrab, "gps_speed_mode", True)

    assert datagrab._load_speed_settings(config_path=str(config_path)) == (1.02, "calibrated")
    assert datagrab.gps_speed_mode is False

    config_path.write_text("{broken", encoding="utf-8")
    assert datagrab._load_speed_settings(config_path=str(config_path)) == (1.01, "calibrated")


def test_dashboard_uses_processed_speed_but_keeps_raw_physics_source(monkeypatch):
    from main import Dashboard
    from vehicle import datagrab

    now = time.time()
    monkeypatch.setitem(datagrab.data_store, "OBD", {
        "speed": 50.0,
        "speed_smoothed": 49.5,
        "last_update": now,
    })
    card = SimpleNamespace(current_speed=0.0)
    dashboard = SimpleNamespace(
        trip_card=card,
        odo_card=SimpleNamespace(current_speed=0.0),
        trip_info_card=SimpleNamespace(update_from_speed=lambda value: None),
        _maybe_update_speed_correction=lambda value: None,
        _displayed_speed_int=0,
        _speed_hysteresis=0.3,
        current_speed_limit=None,
        _update_speed_display=lambda: None,
    )

    Dashboard._slot_set_speed.__wrapped__(dashboard, 52.0)

    assert dashboard.speed == 52.0
    assert dashboard.trip_card.current_speed == 52.0
    assert dashboard.calc_speed_source == 50.0


def test_gps_display_threshold_uses_smoothed_obd_speed(monkeypatch):
    from main import Dashboard
    from vehicle import datagrab

    monkeypatch.setattr(datagrab, "gps_speed_mode", True)
    dashboard = SimpleNamespace(is_gps_fixed=True, obd_speed_smoothed=19.9)
    assert Dashboard._should_use_gps_speed(dashboard) is False

    dashboard.obd_speed_smoothed = 20.0
    assert Dashboard._should_use_gps_speed(dashboard) is True


def test_speed_mode_switch_persists_and_refreshes_immediately(monkeypatch):
    from main import Dashboard
    from vehicle import datagrab

    calls = []
    monkeypatch.setattr(
        datagrab,
        "set_speed_sync_mode",
        lambda mode, persist=False: calls.append(("persist", mode, persist)),
    )
    monkeypatch.setattr(datagrab, "calculate_obd_display_speed", lambda speed, mode: 105.8)
    monkeypatch.setitem(datagrab.data_store, "OBD", {"speed_smoothed": 100.0})
    dashboard = SimpleNamespace(
        speed_sync_modes=["calibrated", "fixed", "gps"],
        speed_sync_mode="calibrated",
        control_panel=SimpleNamespace(set_speed_sync_state=lambda mode: calls.append(("ui", mode))),
        _displayed_speed_int=100,
        _slot_set_speed=lambda speed: calls.append(("speed", speed)),
        _update_speed_display=lambda: calls.append(("display",)),
    )

    Dashboard.set_speed_sync_mode(dashboard, "fixed")

    assert dashboard.speed_sync_mode == "fixed"
    assert ("persist", "fixed", True) in calls
    assert ("speed", 105.8) in calls
    assert ("display",) in calls


def test_control_panel_prepares_parent_before_exit():
    from ui.control_panel import ControlPanel

    calls = []
    parent = SimpleNamespace(prepare_for_exit=lambda: calls.append("prepared"))
    panel = SimpleNamespace(parent=lambda: parent)

    ControlPanel._prepare_dashboard_exit(panel)

    assert calls == ["prepared"]


def test_system_power_action_prepares_before_running_command(monkeypatch):
    from ui.control_panel import ControlPanel
    import subprocess

    calls = []
    panel = SimpleNamespace(_prepare_dashboard_exit=lambda: calls.append("prepared"))
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: calls.append(tuple(command)))

    ControlPanel._execute_system_power_action(panel, ["sudo", "poweroff"])

    assert calls == ["prepared", ("sudo", "poweroff")]


def test_dashboard_prepare_for_exit_saves_once(monkeypatch):
    import main
    from main import Dashboard

    calls = []

    class FakeStorage:
        def save_now(self):
            calls.append("save")

    monkeypatch.setattr(main, "OdometerStorage", lambda: FakeStorage())
    monkeypatch.setattr(main.os, "sync", lambda: calls.append("sync"))
    dashboard = SimpleNamespace(
        _exit_prepared=False,
        _stop_timer_attr=lambda _name: None,
        _stop_qthread_attr=lambda _name: None,
    )

    Dashboard.prepare_for_exit(dashboard)
    Dashboard.prepare_for_exit(dashboard)

    assert calls == ["save", "sync"]


def test_importing_main_does_not_run_hardware_commands(monkeypatch):
    import subprocess

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    sys.modules.pop("main", None)

    importlib.import_module("main")

    assert calls == []
