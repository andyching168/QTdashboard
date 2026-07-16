import inspect
import json
import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication


_APP = None


def qapp():
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


def test_internal_and_external_gps_positions_are_isolated():
    from main import Dashboard

    dashboard = SimpleNamespace(
        is_using_external_gps=False,
        internal_gps_lat=None,
        internal_gps_lon=None,
        external_gps_lat=None,
        external_gps_lon=None,
        gps_lat=None,
        gps_lon=None,
    )
    dashboard._sync_active_gps_position = lambda: Dashboard._sync_active_gps_position(dashboard)
    Dashboard._update_gps_position(dashboard, 25.0, 121.0)
    assert (dashboard.gps_lat, dashboard.gps_lon) == (25.0, 121.0)

    dashboard.is_using_external_gps = True
    Dashboard._update_gps_position(dashboard, 22.0, 120.0)
    assert (dashboard.internal_gps_lat, dashboard.internal_gps_lon) == (25.0, 121.0)
    assert (dashboard.gps_lat, dashboard.gps_lon) == (22.0, 120.0)

    dashboard.is_using_external_gps = False
    Dashboard._sync_active_gps_position(dashboard)
    assert (dashboard.gps_lat, dashboard.gps_lon) == (25.0, 121.0)


def test_stale_mqtt_gps_cannot_overwrite_active_position():
    from main import Dashboard

    nav = SimpleNamespace(calls=0, show_no_nav_ui=lambda: setattr(nav, "calls", nav.calls + 1))
    monitor = SimpleNamespace(
        is_using_external_gps=lambda: False,
        inject_external_gps=lambda *args: (_ for _ in ()).throw(AssertionError("must not inject")),
    )
    dashboard = SimpleNamespace(
        _perf_logging_enabled=lambda: False,
        current_bearing=None,
        gps_monitor_thread=monitor,
        is_gps_fixed=True,
        gps_lat=25.0,
        gps_lon=121.0,
        internal_gps_lat=25.0,
        internal_gps_lon=121.0,
        external_gps_lat=None,
        external_gps_lon=None,
        _last_external_gps_key=None,
        _last_navigation_ui_key=None,
        nav_card=nav,
    )
    Dashboard._slot_update_navigation(dashboard, {
        "latitude": 22.0,
        "longitude": 120.0,
        "timestamp": "2000-01-01T00:00:00Z",
    })
    assert (dashboard.gps_lat, dashboard.gps_lon) == (25.0, 121.0)
    assert dashboard.external_gps_lat is None
    assert nav.calls == 1


def test_speed_limit_query_uses_internal_position_only():
    from main import Dashboard

    requests = []
    dashboard = SimpleNamespace(
        _is_speed_limit_gps_reliable=lambda: True,
        _clear_speed_limit_display=lambda: None,
        internal_gps_lat=25.1,
        internal_gps_lon=121.1,
        gps_lat=22.0,
        gps_lon=120.0,
        current_bearing=90,
        speed_limit_worker=SimpleNamespace(request=lambda *args: requests.append(args)),
    )
    Dashboard._update_speed_limit(dashboard)
    assert requests == [(25.1, 121.1, 90)]


def test_spotify_force_update_only_wakes_listener():
    from spotify.spotify_listener import SpotifyListener

    listener = SpotifyListener(SimpleNamespace(), update_interval=10)
    listener._update_playback_state = lambda: (_ for _ in ()).throw(
        AssertionError("network call ran on caller thread")
    )
    listener.force_update_now()
    assert listener._wake_event.is_set()


def test_spotify_controller_retains_latest_integration():
    from spotify.spotify_controller import SpotifyController

    stopped = []
    old = SimpleNamespace(stop=lambda: stopped.append("old"))
    new = SimpleNamespace(stop=lambda: stopped.append("new"))
    dashboard = SimpleNamespace(
        _set_spotify_progress_active=lambda active: None,
        _is_music_card_visible=lambda: True,
    )
    controller = SpotifyController(dashboard, "config", "cache")
    controller.integration = old
    controller._operation_generation = 2
    controller._on_init_result(new, "reconnect", 2)
    assert controller.integration is new
    assert controller.connected


def test_mqtt_reinitialization_stops_previous_client(monkeypatch, tmp_path):
    from core.mqtt_telemetry import MqttTelemetryController
    import paho.mqtt.client as mqtt

    clients = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.stopped = False
            clients.append(self)

        def reconnect_delay_set(self, **kwargs): pass
        def username_pw_set(self, *args): pass
        def connect_async(self, *args, **kwargs): pass
        def loop_start(self): pass
        def disconnect(self): pass
        def loop_stop(self): self.stopped = True

    monkeypatch.setattr(mqtt, "Client", FakeClient)
    config = tmp_path / "mqtt.json"
    config.write_text(json.dumps({"broker": "localhost", "port": 1883}), encoding="utf-8")
    controller = MqttTelemetryController(SimpleNamespace(), str(config))
    controller.init_client()
    controller.init_client()
    assert len(clients) == 2
    assert clients[0].stopped
    assert controller.client is clients[1]
    controller.stop()


def test_wifi_close_stops_status_timer():
    qapp()
    from wifi.wifi_manager import WiFiManagerWidget

    widget = WiFiManagerWidget(test_mode=True)
    assert widget.status_timer.isActive()
    widget.close()
    assert not widget.status_timer.isActive()


def test_control_panel_wifi_refresh_contains_no_subprocess():
    from ui.control_panel import ControlPanel

    assert "subprocess.run" not in inspect.getsource(ControlPanel.update_wifi_status)


def test_wifi_status_card_toggles_between_signal_and_ip():
    qapp()
    from ui.control_panel import ControlPanel

    panel = ControlPanel()
    panel.status_timer.stop()
    panel.apply_wifi_status({
        "ssid": "CarHotspot",
        "signal": 82,
        "interface": "wlan0",
        "ip_address": "192.168.8.23",
    })
    assert panel.wifi_status_label.text() == "CarHotspot"
    assert panel.wifi_detail_label.text() == "信號極佳"
    assert panel.wifi_signal_label.text() == "82%"

    panel.toggle_wifi_view()
    assert panel.wifi_status_label.text() == "192.168.8.23"
    assert panel.wifi_detail_label.text() == "IP 位址 · wlan0"
    assert panel.wifi_signal_label.text() == ""

    panel.apply_wifi_status({
        "ssid": "CarHotspot",
        "signal": 70,
        "interface": "wlan0",
        "ip_address": "192.168.8.24",
    })
    assert panel.wifi_status_label.text() == "192.168.8.24"

    panel.toggle_wifi_view()
    assert panel.wifi_status_label.text() == "CarHotspot"
    assert panel.wifi_signal_label.text() == "70%"
    panel.close()


def test_gps_thread_stops_while_waiting_for_device(monkeypatch):
    qapp()
    from ui import threads

    monkeypatch.setattr(threads.glob, "glob", lambda pattern: [])
    worker = threads.GPSMonitorThread()
    worker.start()
    time.sleep(0.05)
    assert worker.stop(1000)


def test_gps_empty_serial_line_exits_cleanly(monkeypatch):
    from ui import threads

    worker = threads.GPSMonitorThread()
    worker._current_port = "/dev/fake-gps"

    class EmptySerial:
        is_open = True

        def readline(self):
            worker.running = False
            return b""

        def close(self):
            self.is_open = False

    monkeypatch.setattr(threads.serial, "Serial", lambda *args, **kwargs: EmptySerial())
    assert worker._read_loop()


def test_gps_serial_exception_reports_failure(monkeypatch):
    from ui import threads

    worker = threads.GPSMonitorThread()
    worker._current_port = "/dev/disconnected-gps"

    def disconnected(*args, **kwargs):
        raise threads.serial.SerialException("device disconnected")

    monkeypatch.setattr(threads.serial, "Serial", disconnected)
    assert not worker._read_loop()


def test_linux_can_path_never_probes_slcan(monkeypatch):
    from vehicle import datagrab

    monkeypatch.setattr(datagrab.platform, "system", lambda: "Linux")
    monkeypatch.setattr(datagrab, "detect_socketcan_interfaces", lambda: [])
    monkeypatch.setattr(
        datagrab,
        "select_serial_port",
        lambda: (_ for _ in ()).throw(AssertionError("SLCAN probed on Linux")),
    )
    bus, interface = datagrab.init_can_bus(max_retries=1)
    assert bus is None and interface is None


def test_can_manager_recovers_from_missing_initial_bus(monkeypatch):
    from vehicle import datagrab

    fake_bus = SimpleNamespace(shutdown=lambda: None)
    monkeypatch.setattr(datagrab, "stop_threads", False)
    monkeypatch.setattr(datagrab, "init_can_bus", lambda **kwargs: (fake_bus, "SocketCAN (can0)"))
    manager = datagrab.BusManager(None)
    assert manager.reconnect()
    deadline = time.time() + 1
    while manager.get() is None and time.time() < deadline:
        time.sleep(0.01)
    assert manager.get() is fake_bus
    manager.shutdown()
    assert manager._reconnect_thread is None or not manager._reconnect_thread.is_alive()


def test_can_initialization_and_reconnect_share_filters(monkeypatch):
    from vehicle import datagrab
    from vehicle.can_config import CAN_FILTERS

    calls = []
    fake_bus = SimpleNamespace(shutdown=lambda: None)

    def make_bus(**kwargs):
        calls.append(kwargs)
        return fake_bus

    monkeypatch.setattr(datagrab.platform, "system", lambda: "Linux")
    monkeypatch.setattr(datagrab, "detect_socketcan_interfaces", lambda: [("can1", "UP"), ("can0", "UP")])
    monkeypatch.setattr(datagrab.can.interface, "Bus", make_bus)

    first, _ = datagrab.init_can_bus(max_retries=1)
    second, _ = datagrab.init_can_bus(max_retries=1)
    assert first is fake_bus and second is fake_bus
    assert [call["channel"] for call in calls] == ["can0", "can0"]
    assert all(call["can_filters"] is CAN_FILTERS for call in calls)
