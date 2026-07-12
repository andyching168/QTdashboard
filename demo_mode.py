#!/usr/bin/env python3
"""Luxgen M7 dashboard demo mode with a separate test console."""

import argparse
import logging
import os

os.environ["DASHBOARD_ENTRY"] = "demo"

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtWidgets import QApplication

from main import run_dashboard
from ui.demo_control_window import DemoControlWindow
from vehicle.demo_controller import DemoController, SimulationMode


class ControlEventFilter(QObject):
    """Keep only the shortcut that shows or hides the test console."""

    def __init__(self, controller: DemoController) -> None:
        super().__init__()
        self.controller = controller
        self.console = None

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() != QEvent.Type.KeyPress:
            return False
        if event.key() == Qt.Key.Key_F11 and self.console is not None:
            self.console.setVisible(not self.console.isVisible())
            if self.console.isVisible():
                self.console.raise_()
                self.console.activateWindow()
            return True
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Luxgen M7 儀表板演示模式")
    parser.add_argument("--perf", action="store_true", help="啟用效能監控")
    parser.add_argument("--test-shutdown", type=float, nargs="?", const=5.0, default=None, metavar="DELAY", help="幾秒後觸發電壓歸零")
    parser.add_argument("--control-data", action="store_true", help="以手動控制模式啟動")
    parser.add_argument("--spotify", action="store_true", help="保留的相容旗標")
    parser.add_argument("--mock-gps", action="store_true", help="以 Mock GPS 定位狀態啟動")
    args = parser.parse_args()

    if args.perf:
        os.environ["PERF_MONITOR"] = "1"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    controller = DemoController(SimulationMode.MANUAL if args.control_data else SimulationMode.AUTO)
    if args.mock_gps:
        controller.update_values(gps_fixed=True, gps_internal=True, gps_fresh=True)

    def setup_demo_data(dashboard):
        dashboard.connect_worker_signals(controller)
        controller.parking_brake_changed.connect(dashboard.set_parking_brake)
        controller.cruise_changed.connect(dashboard.set_cruise)
        controller.radar_changed.connect(dashboard.signal_update_radar)

        def update_gps(fixed, internal, fresh, speed, latitude, longitude):
            dashboard._update_gps_status(fixed)
            dashboard._update_gps_source(is_internal=internal, is_fresh=fresh)
            dashboard._update_gps_device(True)
            dashboard._update_gps_speed(speed)
            if fixed:
                dashboard._update_gps_position(latitude, longitude)
                dashboard.gps_lat, dashboard.gps_lon = latitude, longitude

        controller.gps_changed.connect(update_gps)
        controller.shutdown_requested.connect(dashboard.trigger_voltage_zero_test)

        timer = QTimer(dashboard)
        timer.timeout.connect(controller.tick)
        timer.start(100)

        event_filter = ControlEventFilter(controller)
        app = QApplication.instance()
        app.installEventFilter(event_filter)

        console = DemoControlWindow(controller)
        event_filter.console = console
        dashboard._demo_control_window = console
        dashboard._demo_event_filter = event_filter
        console.show()
        controller.emit_state()

        shutdown_timer = None
        if args.test_shutdown is not None:
            shutdown_timer = QTimer(dashboard)
            shutdown_timer.setSingleShot(True)
            shutdown_timer.timeout.connect(lambda: controller.apply_scenario("低電壓"))
            shutdown_timer.start(max(0, int(args.test_shutdown * 1000)))

        def cleanup():
            timer.stop()
            if shutdown_timer is not None:
                shutdown_timer.stop()
            app.removeEventFilter(event_filter)
            console.shutdown()

        return cleanup

    title = "Luxgen M7 儀表板 - 演示模式"
    if args.control_data:
        title += "（手動控制）"
    run_dashboard(window_title=title, setup_data_source=setup_demo_data, skip_gps=args.mock_gps)


if __name__ == "__main__":
    main()
