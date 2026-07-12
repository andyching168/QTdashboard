"""Demo mode state and scenario controller.

This module deliberately has no dependency on the dashboard widgets.  Both the
test console and the keyboard adapter update this controller, and the dashboard
only consumes its signals.
"""

from dataclasses import dataclass, field, replace
from enum import Enum
import random
import time
from typing import Dict, Mapping

from PyQt6.QtCore import QObject, pyqtSignal


DOORS = ("FL", "FR", "RL", "RR", "BK")
RADAR_ZONES = ("LR", "RR", "LF", "RF")
VALID_GEARS = ("P", "R", "N", "D", "1", "2", "3", "4", "5", "6", "S", "L")


class SimulationMode(str, Enum):
    MANUAL = "manual"
    AUTO = "auto"


@dataclass
class VehicleState:
    speed: float = 0.0
    rpm: float = 0.8
    fuel: float = 65.0
    temp: float = 45.0
    gear: str = "P"
    turbo: float = -0.7
    battery: float = 12.6
    cruise_switch: bool = False
    cruise_engaged: bool = False
    turn_signal: str = "off"
    doors: Dict[str, bool] = field(default_factory=lambda: {door: True for door in DOORS})
    parking_brake: bool = True
    radar: Dict[str, int] = field(default_factory=lambda: {zone: 0 for zone in RADAR_ZONES})
    gps_fixed: bool = False
    gps_internal: bool = True
    gps_fresh: bool = True
    gps_speed: float = 0.0
    latitude: float = 25.0330
    longitude: float = 121.5654

    def normalized(self) -> "VehicleState":
        state = replace(self)
        state.speed = max(0.0, min(200.0, float(state.speed)))
        state.rpm = max(0.0, min(8.0, float(state.rpm)))
        state.fuel = max(0.0, min(100.0, float(state.fuel)))
        state.temp = max(0.0, min(100.0, float(state.temp)))
        state.turbo = max(-1.0, min(1.5, float(state.turbo)))
        state.battery = max(0.0, min(16.0, float(state.battery)))
        state.gear = str(state.gear).upper()
        if state.gear not in VALID_GEARS:
            state.gear = "P"
        if not state.cruise_switch:
            state.cruise_engaged = False
        state.turn_signal = state.turn_signal if state.turn_signal in {"off", "left_on", "right_on", "both_on"} else "off"
        state.doors = {door: bool(state.doors.get(door, True)) for door in DOORS}
        state.radar = {zone: max(0, min(2, int(state.radar.get(zone, 0)))) for zone in RADAR_ZONES}
        state.gps_speed = max(0.0, min(250.0, float(state.gps_speed)))
        state.latitude = max(-90.0, min(90.0, float(state.latitude)))
        state.longitude = max(-180.0, min(180.0, float(state.longitude)))
        return state


def _scenario(**changes) -> VehicleState:
    state = VehicleState()
    for key, value in changes.items():
        setattr(state, key, value)
    return state.normalized()


SCENARIOS: Mapping[str, VehicleState] = {
    "停車": _scenario(),
    "怠速": _scenario(gear="P", rpm=0.8, battery=13.2, parking_brake=True),
    "加速": _scenario(speed=55, rpm=3.6, gear="3", turbo=0.45, battery=13.8, parking_brake=False),
    "巡航": _scenario(speed=100, rpm=2.4, gear="5", turbo=0.1, battery=14.0, cruise_switch=True, cruise_engaged=True, parking_brake=False),
    "煞停": _scenario(speed=8, rpm=1.1, gear="D", turbo=-0.6, parking_brake=False),
    "倒車": _scenario(speed=5, rpm=1.2, gear="R", parking_brake=False, radar={"LR": 1, "RR": 1, "LF": 0, "RF": 0}),
    "全門開": _scenario(doors={door: False for door in DOORS}),
    "雷達警示": _scenario(radar={zone: 2 for zone in RADAR_ZONES}),
    "低電壓": _scenario(battery=0.0),
}


class DemoController(QObject):
    """Single source of truth for demo mode."""

    update_rpm = pyqtSignal(float)
    update_speed = pyqtSignal(float)
    update_temp = pyqtSignal(float)
    update_fuel = pyqtSignal(float)
    update_gear = pyqtSignal(str)
    update_turbo = pyqtSignal(float)
    update_battery = pyqtSignal(float)
    update_turn_signal = pyqtSignal(str)
    update_door_status = pyqtSignal(str, bool)
    update_fuel_consumption = pyqtSignal(float, float)
    update_obd_batch = pyqtSignal(dict)

    parking_brake_changed = pyqtSignal(bool)
    cruise_changed = pyqtSignal(bool, bool)
    radar_changed = pyqtSignal(str)
    gps_changed = pyqtSignal(bool, bool, bool, float, float, float)
    state_changed = pyqtSignal(object)
    mode_changed = pyqtSignal(str)
    running_changed = pyqtSignal(bool)
    shutdown_requested = pyqtSignal()

    def __init__(self, mode: SimulationMode = SimulationMode.AUTO) -> None:
        super().__init__()
        self.state = VehicleState()
        self.mode = mode
        self.running = True
        self.auto_phase = "idle"
        self.phase_time = 0.0
        self.target_speed = 90.0
        self._last_turn_signal = "off"
        self._last_discrete_state = None
        self._last_tick = time.monotonic()

    def set_mode(self, mode) -> None:
        self.mode = SimulationMode(mode)
        self.phase_time = 0.0
        self.mode_changed.emit(self.mode.value)
        self.state_changed.emit(self.state)

    def set_running(self, running: bool) -> None:
        self.running = bool(running)
        self._last_tick = time.monotonic()
        self.running_changed.emit(self.running)

    def reset(self) -> None:
        self.auto_phase = "idle"
        self.phase_time = 0.0
        self.set_state(VehicleState(), emit=True)

    def set_state(self, state: VehicleState, emit: bool = True) -> None:
        self.state = state.normalized()
        if emit:
            self.emit_state()

    def update_values(self, **changes) -> None:
        values = {**self.state.__dict__, **changes}
        self.set_state(VehicleState(**values), emit=True)

    def set_door(self, door: str, is_closed: bool) -> None:
        doors = dict(self.state.doors)
        doors[door.upper()] = bool(is_closed)
        self.update_values(doors=doors)

    def set_radar(self, zone: str, level: int) -> None:
        radar = dict(self.state.radar)
        radar[zone.upper()] = level
        self.update_values(radar=radar)

    def apply_scenario(self, name: str) -> None:
        if name not in SCENARIOS:
            raise KeyError(name)
        self.set_mode(SimulationMode.MANUAL)
        self.set_state(replace(SCENARIOS[name], doors=dict(SCENARIOS[name].doors), radar=dict(SCENARIOS[name].radar)))
        if name == "低電壓":
            self.shutdown_requested.emit()

    def tick(self, dt: float = None) -> None:
        now = time.monotonic()
        if dt is None:
            dt = now - self._last_tick
        self._last_tick = now
        if not self.running:
            return
        if self.mode is SimulationMode.AUTO:
            self._update_auto(max(0.0, min(float(dt), 1.0)))
        self.emit_state()

    def _update_auto(self, dt: float) -> None:
        state = self.state
        self.phase_time += dt
        if self.auto_phase == "idle" and self.phase_time >= 5.0:
            self.auto_phase, self.phase_time = "accelerating", 0.0
            self.target_speed = random.uniform(60.0, 120.0)
        elif self.auto_phase == "accelerating" and state.speed >= self.target_speed * 0.95:
            self.auto_phase, self.phase_time = "cruising", 0.0
        elif self.auto_phase == "cruising" and self.phase_time >= 10.0:
            self.auto_phase, self.phase_time = "decelerating", 0.0
        elif self.auto_phase == "decelerating" and state.speed <= 1.0:
            self.auto_phase, self.phase_time = "idle", 0.0

        if self.auto_phase == "idle":
            speed, rpm, gear, turbo = max(0.0, state.speed - 4 * dt), 0.8, "P", -0.6
        elif self.auto_phase == "accelerating":
            speed = min(self.target_speed, state.speed + 12 * dt)
            rpm, gear, turbo = min(6.5, 1.0 + speed / 22.0), self._gear_for_speed(speed), min(1.0, -0.2 + speed / 100.0)
        elif self.auto_phase == "cruising":
            speed = max(0.0, state.speed + random.uniform(-0.3, 0.3))
            rpm, gear, turbo = 1.5 + speed / 100 * 2.0, self._gear_for_speed(speed), 0.1
        else:
            speed = max(0.0, state.speed - 14 * dt)
            rpm, gear, turbo = 1.0 + speed / 100 * 1.5, self._gear_for_speed(speed), -0.5

        self.state = replace(
            state,
            speed=speed,
            rpm=rpm,
            gear=gear,
            turbo=turbo,
            battery=13.2 if rpm < 1.0 else min(14.2, 13.5 + rpm * 0.1),
            temp=max(20.0, min(95.0, state.temp + (0.2 if rpm > 1.5 else -0.05) * dt)),
            fuel=max(0.0, state.fuel - (0.001 * dt if speed > 0 else 0.0)),
            parking_brake=self.auto_phase == "idle" and speed < 1.0,
        ).normalized()

    @staticmethod
    def _gear_for_speed(speed: float) -> str:
        if speed < 1:
            return "P"
        if speed < 20:
            return "1"
        if speed < 40:
            return "2"
        if speed < 60:
            return "3"
        if speed < 80:
            return "4"
        return "5"

    def emit_state(self) -> None:
        state = self.state.normalized()
        self.state = state
        self.update_rpm.emit(state.rpm)
        self.update_speed.emit(state.speed)
        self.update_temp.emit(state.temp)
        self.update_fuel.emit(state.fuel)
        self.update_gear.emit(state.gear)
        self.update_turbo.emit(state.turbo)
        self.update_battery.emit(state.battery)
        if self._last_turn_signal != "off" and state.turn_signal != self._last_turn_signal:
            self.update_turn_signal.emit(self._last_turn_signal.replace("_on", "_off"))
        self.update_turn_signal.emit(state.turn_signal)
        self._last_turn_signal = state.turn_signal
        previous = self._last_discrete_state
        for door, is_closed in state.doors.items():
            if previous is None or previous.doors[door] != is_closed:
                self.update_door_status.emit(door, is_closed)
        if previous is None or previous.parking_brake != state.parking_brake:
            self.parking_brake_changed.emit(state.parking_brake)
        if previous is None or (previous.cruise_switch, previous.cruise_engaged) != (state.cruise_switch, state.cruise_engaged):
            self.cruise_changed.emit(state.cruise_switch, state.cruise_engaged)
        radar = "(" + ",".join(f"{zone}:{state.radar[zone]}" for zone in RADAR_ZONES) + ")"
        if previous is None or previous.radar != state.radar:
            self.radar_changed.emit(radar)
        gps_values = (state.gps_fixed, state.gps_internal, state.gps_fresh, state.gps_speed, state.latitude, state.longitude)
        previous_gps = None if previous is None else (previous.gps_fixed, previous.gps_internal, previous.gps_fresh, previous.gps_speed, previous.latitude, previous.longitude)
        if previous_gps != gps_values:
            self.gps_changed.emit(*gps_values)
        self.state_changed.emit(state)
        self._last_discrete_state = replace(state, doors=dict(state.doors), radar=dict(state.radar))
