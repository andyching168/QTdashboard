"""全時分層智慧速度校正回歸測試。"""
import json
from collections import deque


def _reset_model(monkeypatch, datagrab):
    monkeypatch.setattr(datagrab, "_smart_bands", datagrab._empty_smart_bands())
    monkeypatch.setattr(datagrab, "_smart_history", deque(maxlen=80))
    monkeypatch.setattr(datagrab, "_smart_last_sample_at", 0.0)
    monkeypatch.setattr(datagrab, "_smart_last_persist_at", 10_000.0)
    monkeypatch.setattr(datagrab, "_smart_dirty", False)
    monkeypatch.setattr(datagrab, "_speed_correction_value", 1.01)


def _quality(now, **changes):
    value = {
        "fix_quality": 1,
        "satellites": 10,
        "hdop": 0.9,
        "rmc_valid": True,
        "rmc_timestamp": now,
        "timestamp": now,
    }
    value.update(changes)
    return value


def test_band_boundaries_and_status_snapshot(monkeypatch):
    from vehicle import datagrab

    _reset_model(monkeypatch, datagrab)
    assert datagrab._band_start(19.9) is None
    assert datagrab._band_start(20.0) == 20
    assert datagrab._band_start(89.9) == 80
    assert datagrab._band_start(130.0) == 130
    assert datagrab._band_start(220.0) == 130
    statuses = datagrab.get_smart_calibration_status()
    assert statuses[0]["label"] == "20–30"
    assert statuses[-1]["label"] == "130+"


def test_quality_and_synchronization_filters(monkeypatch):
    from vehicle import datagrab

    _reset_model(monkeypatch, datagrab)
    now = 100.0
    assert not datagrab.submit_smart_calibration_sample(80, now, 78, now, _quality(now, satellites=5), now)
    assert not datagrab.submit_smart_calibration_sample(80, now, 78, now, _quality(now, hdop=1.6), now)
    assert not datagrab.submit_smart_calibration_sample(80, now, 78, now, _quality(now, rmc_valid=False), now)
    assert not datagrab.submit_smart_calibration_sample(80, now, 78, now - 1.0, _quality(now), now)
    assert not datagrab.submit_smart_calibration_sample(80, now, 60, now, _quality(now), now)
    assert all(item["samples"] == 0 for item in datagrab.get_smart_calibration_status())


def test_stable_samples_mature_band_and_learn_ratio(monkeypatch):
    from vehicle import datagrab

    _reset_model(monkeypatch, datagrab)
    accepted = 0
    for index in range(160):
        now = 100.0 + index * 0.25
        accepted += datagrab.submit_smart_calibration_sample(100.0, now, 98.0, now, _quality(now), now)
    band = next(item for item in datagrab.get_smart_calibration_status() if item["start"] == 90)
    assert accepted >= datagrab.SMART_MIN_SAMPLES
    assert band["mature"] is True
    assert abs(band["coefficient"] - 0.98) < 0.001


def test_unstable_speed_does_not_learn(monkeypatch):
    from vehicle import datagrab

    _reset_model(monkeypatch, datagrab)
    for index in range(80):
        now = 100.0 + index * 0.25
        obd = 80.0 + (index % 8)
        datagrab.submit_smart_calibration_sample(obd, now, obd - 1.0, now, _quality(now), now)
    assert all(item["samples"] == 0 for item in datagrab.get_smart_calibration_status())


def test_mature_bands_are_interpolated(monkeypatch):
    from vehicle import datagrab

    _reset_model(monkeypatch, datagrab)
    datagrab._smart_bands[80].update(coefficient=0.98, samples=30)
    datagrab._smart_bands[100].update(coefficient=1.02, samples=30)
    coefficient, mature = datagrab.get_smart_speed_correction(95.0)
    assert mature is True
    assert abs(coefficient - 1.0) < 0.0001
    assert datagrab.get_smart_speed_correction(50.0) == (0.98, True)


def test_unlearned_model_uses_legacy_fallback(monkeypatch):
    from vehicle import datagrab

    _reset_model(monkeypatch, datagrab)
    assert datagrab.get_smart_speed_correction(90.0) == (1.01, False)
    assert datagrab.calculate_obd_display_speed(100.0, "calibrated") == 101.0
    assert datagrab.calculate_obd_display_speed(100.0, "fixed") == 105.8


def test_smart_settings_roundtrip_and_reset(tmp_path, monkeypatch):
    from vehicle import datagrab

    _reset_model(monkeypatch, datagrab)
    path = tmp_path / "speed_calibration.json"
    datagrab._smart_bands[80].update(coefficient=0.985, samples=42, updated_at=123.0)
    datagrab.persist_speed_settings(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["smart_calibration"]["version"] == 1
    assert payload["smart_calibration"]["bands"]["80"]["samples"] == 42

    datagrab._smart_bands = datagrab._empty_smart_bands()
    datagrab._load_speed_settings(config_path=str(path))
    loaded = next(item for item in datagrab.get_smart_calibration_status() if item["start"] == 80)
    assert loaded["coefficient"] == 0.985
    assert loaded["samples"] == 42

    monkeypatch.setattr(datagrab, "SPEED_CALIBRATION_FILE", str(path))
    monkeypatch.setattr(datagrab, "speed_sync_mode", "gps")
    monkeypatch.setattr(datagrab, "gps_speed_mode", True)
    datagrab.reset_smart_calibration()
    assert all(item["samples"] == 0 for item in datagrab.get_smart_calibration_status())
    assert datagrab.get_speed_sync_mode() == "gps"


def test_gps_monitor_emits_gga_and_rmc_quality(monkeypatch):
    from ui import threads

    worker = threads.GPSMonitorThread()
    worker._current_port = "/dev/fake-neo8m"
    lines = iter([
        b"$GPGGA,120000,2500.000,N,12100.000,E,1,10,0.8,10.0,M,0.0,M,,*00\r\n",
        b"$GNRMC,120000,A,2500.000,N,12100.000,E,50.00,0.0,010126,,,A*00\r\n",
    ])

    class FakeSerial:
        is_open = True
        def readline(self):
            try:
                return next(lines)
            except StopIteration:
                worker.running = False
                return b""
        def close(self):
            self.is_open = False
        def reset_input_buffer(self):
            pass

    qualities = []
    worker.gps_quality_changed.connect(qualities.append)
    monkeypatch.setattr(threads.serial, "Serial", lambda *args, **kwargs: FakeSerial())
    assert worker._read_loop()
    assert qualities[-1]["fix_quality"] == 1
    assert qualities[-1]["satellites"] == 10
    assert qualities[-1]["hdop"] == 0.8
    assert qualities[-1]["rmc_valid"] is True
    assert qualities[-1]["rmc_timestamp"] > 0


def test_calibration_chart_scales_and_renders_nodes():
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWidgets import QApplication
    from ui.control_panel import SmartCalibrationChart

    app = QApplication.instance() or QApplication([])
    statuses = (
        {"label": "80–90", "coefficient": 0.98, "samples": 30, "mature": True},
        {"label": "90–100", "coefficient": 1.00, "samples": 12, "mature": False},
        {"label": "100–110", "coefficient": None, "samples": 0, "mature": False},
    )
    chart = SmartCalibrationChart(statuses, 1.01)
    chart.resize(700, 180)
    low, high = chart._range()
    assert low < 0.98 < 1.01 < high
    pixmap = QPixmap(chart.size())
    chart.render(pixmap)
    assert len(chart._points) == 2
    chart.close()
    assert app is not None


def test_empty_calibration_chart_has_no_false_curve():
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWidgets import QApplication
    from ui.control_panel import SmartCalibrationChart

    app = QApplication.instance() or QApplication([])
    statuses = ({"label": "20–30", "coefficient": None, "samples": 0, "mature": False},)
    chart = SmartCalibrationChart(statuses, 1.01)
    chart.resize(500, 180)
    pixmap = QPixmap(chart.size())
    chart.render(pixmap)
    assert chart._points == []
    chart.close()
    assert app is not None
