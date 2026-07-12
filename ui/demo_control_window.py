"""Tabbed control console for demo mode."""

from functools import partial

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QMainWindow, QPushButton, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget,
)

from vehicle.demo_controller import DOORS, RADAR_ZONES, SCENARIOS, DemoController, SimulationMode, VALID_GEARS


class DemoControlWindow(QMainWindow):
    def __init__(self, controller: DemoController) -> None:
        super().__init__()
        self.controller = controller
        self._syncing = False
        self._allow_close = False
        self.setWindowTitle("Luxgen M7 測試控制台（F11 顯示／隱藏）")
        self.resize(620, 680)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addLayout(self._build_header())
        self.tabs = QTabWidget()
        self.tabs.addTab(self._driving_tab(), "行車")
        self.tabs.addTab(self._body_tab(), "車身")
        self.tabs.addTab(self._navigation_tab(), "導航")
        self.tabs.addTab(self._scenario_tab(), "情境／系統")
        layout.addWidget(self.tabs)
        self.setCentralWidget(root)
        controller.state_changed.connect(self.sync_from_state)
        controller.mode_changed.connect(self._sync_mode)
        controller.running_changed.connect(self._sync_running)
        self.sync_from_state(controller.state)
        self._sync_mode(controller.mode.value)
        self._sync_running(controller.running)

    def _build_header(self):
        layout = QHBoxLayout()
        layout.addWidget(QLabel("控制模式"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("手動控制", SimulationMode.MANUAL.value)
        self.mode_combo.addItem("自動情境", SimulationMode.AUTO.value)
        self.mode_combo.currentIndexChanged.connect(lambda: self.controller.set_mode(self.mode_combo.currentData()))
        layout.addWidget(self.mode_combo)
        self.running_button = QPushButton("暫停")
        self.running_button.setCheckable(True)
        self.running_button.clicked.connect(lambda checked: self.controller.set_running(not checked))
        layout.addWidget(self.running_button)
        layout.addStretch()
        return layout

    def _spin(self, minimum, maximum, step, callback, decimals=1):
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setSingleStep(step)
        widget.setDecimals(decimals)
        widget.valueChanged.connect(callback)
        return widget

    def _driving_tab(self):
        page, form = QWidget(), QFormLayout()
        self.speed = self._spin(0, 200, 5, lambda value: self._change(speed=value))
        self.rpm = self._spin(0, 8, .1, lambda value: self._change(rpm=value))
        self.temp = self._spin(0, 100, 1, lambda value: self._change(temp=value))
        self.fuel = self._spin(0, 100, 1, lambda value: self._change(fuel=value))
        self.turbo = self._spin(-1, 1.5, .1, lambda value: self._change(turbo=value))
        self.battery = self._spin(0, 16, .1, lambda value: self._change(battery=value))
        self.gear = QComboBox(); self.gear.addItems(VALID_GEARS)
        self.gear.currentTextChanged.connect(lambda value: self._change(gear=value))
        self.cruise_switch = QCheckBox("巡航待命")
        self.cruise_engaged = QCheckBox("巡航作動")
        self.cruise_switch.toggled.connect(lambda value: self._change(cruise_switch=value))
        self.cruise_engaged.toggled.connect(lambda value: self._change(cruise_engaged=value))
        for label, widget in (("速度 km/h", self.speed), ("轉速 ×1000 rpm", self.rpm), ("檔位", self.gear), ("水溫 %", self.temp), ("油量 %", self.fuel), ("渦輪 bar", self.turbo), ("電瓶 V", self.battery)):
            form.addRow(label, widget)
        form.addRow(self.cruise_switch); form.addRow(self.cruise_engaged)
        page.setLayout(form)
        return page

    def _body_tab(self):
        page, layout = QWidget(), QVBoxLayout()
        turn_box, turn_layout = QGroupBox("方向燈"), QHBoxLayout()
        self.turn_buttons = {}
        for label, value in (("關閉", "off"), ("左轉", "left_on"), ("右轉", "right_on"), ("雙黃", "both_on")):
            button = QPushButton(label); button.setCheckable(True)
            button.clicked.connect(partial(self._select_turn, value))
            self.turn_buttons[value] = button; turn_layout.addWidget(button)
        turn_box.setLayout(turn_layout); layout.addWidget(turn_box)
        door_box, door_layout = QGroupBox("車門（勾選代表關閉）"), QGridLayout()
        self.door_checks = {}
        names = {"FL": "左前", "FR": "右前", "RL": "左後", "RR": "右後", "BK": "尾門"}
        for index, door in enumerate(DOORS):
            check = QCheckBox(names[door]); check.toggled.connect(partial(self._door_changed, door))
            self.door_checks[door] = check; door_layout.addWidget(check, index // 2, index % 2)
        door_box.setLayout(door_layout); layout.addWidget(door_box)
        self.parking_brake = QCheckBox("手煞車拉起")
        self.parking_brake.toggled.connect(lambda value: self._change(parking_brake=value)); layout.addWidget(self.parking_brake)
        radar_box, radar_layout = QGroupBox("雷達（0 關／1 黃／2 紅）"), QFormLayout()
        self.radar_spins = {}
        for zone in RADAR_ZONES:
            spin = QSpinBox(); spin.setRange(0, 2); spin.valueChanged.connect(partial(self._radar_changed, zone))
            self.radar_spins[zone] = spin; radar_layout.addRow(zone, spin)
        radar_box.setLayout(radar_layout); layout.addWidget(radar_box); layout.addStretch(); page.setLayout(layout)
        return page

    def _navigation_tab(self):
        page, form = QWidget(), QFormLayout()
        self.gps_fixed = QCheckBox("已定位"); self.gps_fixed.toggled.connect(lambda v: self._change(gps_fixed=v))
        self.gps_internal = QCheckBox("內建 GPS"); self.gps_internal.toggled.connect(lambda v: self._change(gps_internal=v))
        self.gps_fresh = QCheckBox("資料新鮮"); self.gps_fresh.toggled.connect(lambda v: self._change(gps_fresh=v))
        self.gps_speed = self._spin(0, 250, 1, lambda v: self._change(gps_speed=v))
        self.latitude = self._spin(-90, 90, .0001, lambda v: self._change(latitude=v), 6)
        self.longitude = self._spin(-180, 180, .0001, lambda v: self._change(longitude=v), 6)
        self.gps_presets = QComboBox()
        for name, lat, lon in (("台北市區", 25.0330, 121.5654), ("國3 35K", 24.9850, 121.4921), ("國3 267K", 23.6751, 120.5846), ("國10 0K", 22.7090, 120.3604)):
            self.gps_presets.addItem(name, (lat, lon))
        self.gps_presets.currentIndexChanged.connect(self._apply_gps_preset)
        for label, widget in (("GPS 狀態", self.gps_fixed), ("來源", self.gps_internal), ("資料狀態", self.gps_fresh), ("GPS 速度 km/h", self.gps_speed), ("緯度", self.latitude), ("經度", self.longitude), ("座標預設／速限測試", self.gps_presets)):
            form.addRow(label, widget)
        page.setLayout(form); return page

    def _scenario_tab(self):
        page, layout = QWidget(), QVBoxLayout()
        grid = QGridLayout()
        for index, name in enumerate(SCENARIOS):
            button = QPushButton(name); button.clicked.connect(lambda checked=False, scenario=name: self.controller.apply_scenario(scenario))
            grid.addWidget(button, index // 3, index % 3)
        layout.addLayout(grid)
        reset = QPushButton("重設為安全停車狀態"); reset.clicked.connect(self.controller.reset); layout.addWidget(reset)
        self.summary = QLabel(); self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.summary.setWordWrap(True); layout.addWidget(self.summary); layout.addStretch(); page.setLayout(layout)
        return page

    def _change(self, **changes):
        if not self._syncing:
            self.controller.update_values(**changes)

    def _door_changed(self, door, checked):
        if not self._syncing: self.controller.set_door(door, checked)

    def _radar_changed(self, zone, value):
        if not self._syncing: self.controller.set_radar(zone, value)

    def _select_turn(self, value, *_):
        if not self._syncing: self.controller.update_values(turn_signal=value)

    def _apply_gps_preset(self):
        if self._syncing: return
        lat, lon = self.gps_presets.currentData()
        self.controller.update_values(gps_fixed=True, latitude=lat, longitude=lon)

    def _sync_mode(self, mode):
        self._syncing = True
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(mode))
        manual = mode == SimulationMode.MANUAL.value
        for index in range(self.tabs.count() - 1): self.tabs.widget(index).setEnabled(manual)
        self._syncing = False

    def _sync_running(self, running):
        self.running_button.setChecked(not running); self.running_button.setText("暫停" if running else "繼續")

    def sync_from_state(self, state):
        self._syncing = True
        for widget, value in ((self.speed, state.speed), (self.rpm, state.rpm), (self.temp, state.temp), (self.fuel, state.fuel), (self.turbo, state.turbo), (self.battery, state.battery), (self.gps_speed, state.gps_speed), (self.latitude, state.latitude), (self.longitude, state.longitude)):
            widget.setValue(value)
        self.gear.setCurrentText(state.gear); self.cruise_switch.setChecked(state.cruise_switch); self.cruise_engaged.setChecked(state.cruise_engaged)
        for name, button in self.turn_buttons.items(): button.setChecked(name == state.turn_signal)
        for door, check in self.door_checks.items(): check.setChecked(state.doors[door])
        self.parking_brake.setChecked(state.parking_brake)
        for zone, spin in self.radar_spins.items(): spin.setValue(state.radar[zone])
        self.gps_fixed.setChecked(state.gps_fixed); self.gps_internal.setChecked(state.gps_internal); self.gps_fresh.setChecked(state.gps_fresh)
        self.summary.setText(f"模式：{self.controller.mode.value}｜階段：{self.controller.auto_phase}\n速度：{state.speed:.1f} km/h｜轉速：{state.rpm:.1f}｜檔位：{state.gear}\n電瓶：{state.battery:.1f} V｜GPS：{'定位' if state.gps_fixed else '未定位'}")
        self._syncing = False

    def closeEvent(self, event):  # noqa: N802
        if self._allow_close:
            event.accept()
            return
        event.ignore()
        self.hide()

    def shutdown(self):
        """Really close the console while the application is shutting down."""
        self._allow_close = True
        self.close()
