#!/usr/bin/env python3
"""
演示模式：無需 CAN Bus 硬體
- 預設自動模擬怠速/加速/巡航/減速
- --control-data 可改為鍵盤直接調整數據，停用自動場景
- PERF_MONITOR=1 或 --perf 可開啟效能監控
"""

import argparse
import logging
import os
import random
import sys
import time
from PyQt6.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal

from main import run_dashboard


class VehicleSignals(QObject):
    """Dashboard 所需的數據訊號"""

    update_rpm = pyqtSignal(float)
    update_speed = pyqtSignal(float)
    update_temp = pyqtSignal(float)
    update_fuel = pyqtSignal(float)
    update_gear = pyqtSignal(str)
    update_turbo = pyqtSignal(float)
    update_battery = pyqtSignal(float)


class VehicleSimulator:
    """車輛狀態模擬器"""

    def __init__(self, test_shutdown_mode: bool = False, shutdown_delay: float = 5.0) -> None:
        self.speed = 0.0
        self.rpm = 0.8  # 千轉
        self.fuel = 65.0
        self.temp = 45.0  # 儀表百分比
        self.gear = "P"
        self.actual_gear = 1
        self.turbo = -0.7
        self.battery = 12.6

        self.mode = "idle"
        self.time = 0.0
        self.target_speed = 0.0

        # 電壓歸零測試
        self.test_shutdown_mode = test_shutdown_mode
        self.shutdown_delay = shutdown_delay
        self.shutdown_triggered = False
        self.startup_time = time.time()

        # 音樂模擬（僅計時，方便和主程式一致）
        self.music_time = 0.0
        self.song_duration = 182
        self.playlist = [
            ("Drive My Car", "The Beatles", 182),
            ("Highway Star", "Deep Purple", 206),
            ("Ride", "Twenty One Pilots", 214),
            ("Born to Run", "Bruce Springsteen", 270),
            ("Life is a Highway", "Tom Cochrane", 264),
        ]
        self.current_song_index = 0

    def update(self, dt: float = 0.1, manual_override: bool = False) -> None:
        self.time += dt

        # 測試模式：電壓歸零
        if self.test_shutdown_mode:
            elapsed = time.time() - self.startup_time
            if elapsed >= self.shutdown_delay and not self.shutdown_triggered:
                print(f"\n⚡ [測試模式] {self.shutdown_delay} 秒後觸發電壓歸零...")
                print(f"   電壓: {self.battery:.1f}V → 0.0V")
                self.battery = 0.0
                self.shutdown_triggered = True
                return

        # 控制數據模式：僅做合理化處理
        if manual_override:
            self.speed = max(0.0, min(180.0, self.speed))
            self.temp = max(40.0, min(120.0, self.temp + random.uniform(-0.1, 0.1)))
            self.fuel = max(0.0, min(100.0, self.fuel))
            self.battery = max(10.5, min(14.8, self.battery + random.uniform(-0.05, 0.05)))
            self.rpm = max(0.6, min(7.0, 0.8 + (self.speed / 120.0) * 4.5))
            self.turbo = max(-1.0, min(1.2, -0.6 + self.speed * 0.012 + random.uniform(-0.02, 0.02)))
            self.music_time += dt
            return

        # 自動行駛場景
        if self.mode == "idle":
            if self.time > 5:
                self.mode = "accelerating"
                self.target_speed = random.uniform(60, 120)
                self.gear = "D"
                self.time = 0
        elif self.mode == "accelerating" and self.speed >= self.target_speed * 0.95:
            self.mode = "cruising"
            self.time = 0
        elif self.mode == "cruising" and self.time > random.uniform(8, 15):
            self.mode = "decelerating"
            self.time = 0
        elif self.mode == "decelerating" and self.speed < 5:
            self.mode = "idle"
            self.gear = "P"
            self.time = 0

        # 速度與轉速
        if self.mode == "idle":
            self.speed = max(0.0, self.speed - 2 * dt)
            self.rpm = 0.8
        elif self.mode == "accelerating":
            self.speed = min(self.target_speed, self.speed + 3 * dt)
            self.rpm = 0.8 + (self.speed / 100.0) * 4.5
        elif self.mode == "cruising":
            self.speed += random.uniform(-0.5, 0.5) * dt
            self.rpm = 1.5 + (self.speed / 100.0) * 2.5
        elif self.mode == "decelerating":
            self.speed = max(0.0, self.speed - 3 * dt)
            self.rpm = 1.2 + (self.speed / 100.0) * 2.0

        # 渦輪
        if self.rpm < 2.5:
            target_turbo = -0.6 if self.mode in ("idle", "decelerating") and self.speed < 5 else -0.2 + (self.rpm - 2.5) / 1.5 * 0.6
        else:
            target_turbo = 0.4 + (self.rpm - 4.0) / 3.0 * 0.4

        self.turbo = self.turbo + (target_turbo - self.turbo) * 0.15
        if self.rpm > 2.0:
            self.turbo += random.uniform(-0.02, 0.02)
        self.turbo = max(-1.0, min(1.0, self.turbo))

        # 電瓶
        if self.rpm < 1.0:
            target_voltage = 12.4
        elif self.rpm < 2.0:
            target_voltage = 13.2
        else:
            target_voltage = 13.8 + (self.rpm - 2.0) / 5.0 * 0.4
        self.battery = self.battery + (target_voltage - self.battery) * 0.1
        self.battery += random.uniform(-0.05, 0.05)
        self.battery = max(11.0, min(14.5, self.battery))

        # 油量
        if self.speed > 0:
            self.fuel = max(5.0, self.fuel - 0.005 * dt)

        # 水溫
        target_temp = 50.0 if self.rpm > 1.5 else 45.0
        if self.temp < target_temp:
            self.temp += 0.5 * dt
        elif self.temp > target_temp:
            self.temp -= 0.3 * dt
        self.temp += random.uniform(-0.1, 0.1)
        self.temp = max(20.0, min(95.0, self.temp))

        # 檔位
        if self.mode == "idle" and self.speed < 1:
            self.gear = "P"
        else:
            if self.speed < 20:
                self.actual_gear = 1
            elif self.speed < 40:
                self.actual_gear = 2
            elif self.speed < 60:
                self.actual_gear = 3
            elif self.speed < 80:
                self.actual_gear = 4
            else:
                self.actual_gear = 5
            self.gear = str(self.actual_gear)

        # 音樂播放進度
        self.music_time += dt
        if self.music_time >= self.song_duration:
            self.current_song_index = (self.current_song_index + 1) % len(self.playlist)
            _, _, duration = self.playlist[self.current_song_index]
            self.song_duration = duration
            self.music_time = 0.0


class ControlEventFilter(QObject):
    """鍵盤控制數據模式"""

    def __init__(self, simulator: VehicleSimulator) -> None:
        super().__init__()
        self.simulator = simulator

    def eventFilter(self, obj, event):  # noqa: N802 (Qt API naming)
        if event.type() != QEvent.Type.KeyPress:
            return False

        key = event.key()
        handled = True

        if key == Qt.Key.Key_W:
            self.simulator.speed += 5
        elif key == Qt.Key.Key_S:
            self.simulator.speed -= 5
        elif key == Qt.Key.Key_Q:
            self.simulator.temp += 2
        elif key == Qt.Key.Key_E:
            self.simulator.temp -= 2
        elif key == Qt.Key.Key_A:
            self.simulator.fuel -= 1
        elif key == Qt.Key.Key_D:
            self.simulator.fuel += 1
        elif key == Qt.Key.Key_Z:
            self.simulator.battery -= 0.1
        elif key == Qt.Key.Key_X:
            self.simulator.battery += 0.1
        elif key in (Qt.Key.Key_P, Qt.Key.Key_0):
            self.simulator.gear = "P"
        elif key in (Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3, Qt.Key.Key_4, Qt.Key.Key_5, Qt.Key.Key_6):
            self.simulator.gear = str(int(event.text()))
        else:
            handled = False

        return handled


def main() -> None:
    parser = argparse.ArgumentParser(description="Luxgen M7 儀表板演示模式")
    parser.add_argument("--perf", action="store_true", help="啟用效能監控 (等同 PERF_MONITOR=1)")
    parser.add_argument("--test-shutdown", type=float, nargs="?", const=5.0, default=None, metavar="DELAY", help="電壓歸零測試：幾秒後觸發 (預設 5 秒)")
    parser.add_argument("--control-data", action="store_true", help="控制數據模式：鍵盤直接調整數值，停用自動模擬")
    parser.add_argument("--spotify", action="store_true", help="啟用 Spotify Connect 整合（如未安裝模組則忽略）")
    args = parser.parse_args()

    if args.perf:
        os.environ["PERF_MONITOR"] = "1"
        print("🔍 效能監控模式已啟用")

    test_shutdown_mode = args.test_shutdown is not None
    shutdown_delay = args.test_shutdown if test_shutdown_mode else 5.0

    control_data_mode = args.control_data

    if args.spotify:
        try:
            import spotify_auth  # noqa: F401
            import spotify_listener  # noqa: F401
            print("🎧 Spotify 旗標已啟用（此簡化 demo 僅接受旗標，不會連線）")
        except Exception:
            print("⚠️  Spotify 模組未安裝，略過 Spotify 整合")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    print("=" * 50)
    print("演示模式 - Luxgen M7 數位儀表板")
    print("無需 CAN Bus 硬體")
    print("=" * 50)
    print()
    if control_data_mode:
        print("控制數據模式：")
        print("  W/S 調整速度  +5/-5")
        print("  Q/E 調整水溫  +2/-2")
        print("  A/D 調整油量  -1/+1")
        print("  Z/X 調整電壓  -0.1/+0.1")
        print("  1-6 選擇檔位，0 或 P 進入 P 檔")
        print()
    else:
        print("自動場景：怠速 → 加速 → 巡航 → 減速 循環")
        print()

    signals = VehicleSignals()
    simulator = VehicleSimulator(test_shutdown_mode=test_shutdown_mode, shutdown_delay=shutdown_delay)

    def setup_demo_data(dashboard):
        timer = QTimer()
        last_time = time.time()

        event_filter = ControlEventFilter(simulator) if control_data_mode else None

        try:
            from PyQt6.QtWidgets import QApplication

            qt_app = QApplication.instance()
        except Exception:
            qt_app = None

        if control_data_mode and qt_app and event_filter:
            qt_app.installEventFilter(event_filter)

        def tick():
            nonlocal last_time
            now = time.time()
            dt = now - last_time
            last_time = now
            simulator.update(dt=dt, manual_override=control_data_mode)

            signals.update_rpm.emit(simulator.rpm)
            signals.update_speed.emit(simulator.speed)
            signals.update_temp.emit(simulator.temp)
            signals.update_fuel.emit(simulator.fuel)
            signals.update_gear.emit(simulator.gear)
            signals.update_turbo.emit(simulator.turbo)
            signals.update_battery.emit(simulator.battery)

        timer.timeout.connect(tick)
        timer.start(100)

        # 連接 Dashboard 接收端
        signals.update_rpm.connect(dashboard.set_rpm)
        signals.update_speed.connect(dashboard.set_speed)
        signals.update_temp.connect(dashboard.set_temperature)
        signals.update_fuel.connect(dashboard.set_fuel)
        signals.update_gear.connect(dashboard.set_gear)
        signals.update_turbo.connect(dashboard.set_turbo)
        signals.update_battery.connect(dashboard.set_battery)

        def cleanup():
            timer.stop()
            if control_data_mode and qt_app and event_filter:
                qt_app.removeEventFilter(event_filter)

        return cleanup

    window_title = "Luxgen M7 儀表板 - 演示模式"
    if control_data_mode:
        window_title += " (控制數據)"

    run_dashboard(
        window_title=window_title,
        setup_data_source=setup_demo_data,
    )


if __name__ == "__main__":
    main()
