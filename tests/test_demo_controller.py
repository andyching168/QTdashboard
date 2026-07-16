from dataclasses import replace

import pytest

from vehicle.demo_controller import DOORS, RADAR_ZONES, SCENARIOS, DemoController, SimulationMode, VehicleState


def test_vehicle_state_normalizes_values_and_dependencies():
    state = VehicleState(speed=999, rpm=-2, fuel=-1, temp=101, turbo=9, battery=-1, gear="bad", cruise_switch=False, cruise_engaged=True).normalized()
    assert (state.speed, state.rpm, state.fuel, state.temp) == (200, 0, 0, 100)
    assert (state.turbo, state.battery, state.gear) == (1.5, 0, "P")
    assert state.cruise_engaged is False


def test_manual_tick_does_not_overwrite_values():
    controller = DemoController(SimulationMode.MANUAL)
    controller.update_values(speed=77, rpm=4.2, gear="4")
    controller.tick(10)
    assert controller.state.speed == 77
    assert controller.state.rpm == 4.2
    assert controller.state.gear == "4"


def test_auto_mode_advances_and_pause_freezes_state():
    controller = DemoController(SimulationMode.AUTO)
    for _ in range(6):
        controller.tick(1)
    assert controller.auto_phase == "accelerating"
    controller.tick(1)
    assert controller.state.speed > 0
    controller.set_running(False)
    frozen = replace(controller.state)
    controller.tick(1)
    assert controller.state == frozen


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenarios_are_complete_normalized_states(name):
    controller = DemoController()
    controller.apply_scenario(name)
    assert controller.mode is SimulationMode.MANUAL
    assert set(controller.state.doors) == set(DOORS)
    assert set(controller.state.radar) == set(RADAR_ZONES)
    assert controller.state == controller.state.normalized()


def test_body_and_navigation_signal_mapping():
    controller = DemoController(SimulationMode.MANUAL)
    doors, radar, gps = [], [], []
    controller.update_door_status.connect(lambda door, closed: doors.append((door, closed)))
    controller.radar_changed.connect(radar.append)
    controller.gps_changed.connect(lambda *values: gps.append(values))
    controller.update_values(
        doors={door: False for door in DOORS},
        radar={zone: 2 for zone in RADAR_ZONES},
        gps_fixed=True,
        latitude=24.985,
        longitude=121.4921,
    )
    assert set(doors) == {(door, False) for door in DOORS}
    assert radar[-1] == "(LR:2,RR:2,LF:2,RF:2)"
    assert gps[-1][0] is True
    assert gps[-1][-2:] == (24.985, 121.4921)


def test_unchanged_discrete_signals_are_not_reemitted():
    controller = DemoController(SimulationMode.MANUAL)
    parking_events = []
    controller.parking_brake_changed.connect(parking_events.append)
    controller.emit_state()
    controller.emit_state()
    assert parking_events == [True]


def test_low_voltage_uses_shutdown_request_signal():
    controller = DemoController()
    requests = []
    controller.shutdown_requested.connect(lambda: requests.append(True))
    controller.apply_scenario("低電壓")
    assert controller.state.battery == 0
    assert requests == [True]
