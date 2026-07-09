"""車用可靠度修復的純軟體回歸測試。"""
import importlib
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
