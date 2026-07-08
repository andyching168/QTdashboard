"""
Brightness settings dialog.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from core.brightness import (
    BrightnessSettings,
    clamp_brightness_percent,
    load_brightness_settings,
    save_brightness_settings,
)
from ui.theme import T


class BrightnessSettingsDialog(QDialog):
    """Dialog for default and night brightness settings."""

    def __init__(self, parent=None, dashboard=None):
        super().__init__(parent)
        self.dashboard = dashboard
        self._loading_values = False
        self.original_settings = load_brightness_settings()
        self.original_percent = (
            dashboard.get_brightness_percent() if dashboard and hasattr(dashboard, "get_brightness_percent") else 100
        )
        self._build_ui()
        self._load_values(self.original_settings)

    def _window_scale(self) -> float:
        parent = self.parent()
        width = parent.width() if parent else 1920
        height = parent.height() if parent else 480
        return min(width / 1920, height / 480)

    def _build_ui(self):
        scale = self._window_scale()
        dialog_width = max(420, int(560 * scale))
        dialog_height = max(300, int(360 * scale))
        font_size = max(12, int(16 * scale))
        title_font_size = max(16, int(24 * scale))
        btn_height = max(38, int(46 * scale))
        slider_height = max(34, int(44 * scale))
        radius = max(6, int(10 * scale))

        self.setWindowTitle("亮度設定")
        self.setFixedSize(dialog_width, dialog_height)
        self.setModal(True)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {T('BG_CARD')};
            }}
            QLabel, QCheckBox {{
                color: {T('TEXT_PRIMARY')};
                background: transparent;
                font-size: {font_size}px;
            }}
            QCheckBox::indicator {{
                width: {int(22 * scale)}px;
                height: {int(22 * scale)}px;
            }}
            QSlider::groove:horizontal {{
                height: {int(8 * scale)}px;
                background: {T('BG_INPUT')};
                border-radius: {int(4 * scale)}px;
            }}
            QSlider::sub-page:horizontal {{
                background: {T('PRIMARY')};
                border-radius: {int(4 * scale)}px;
            }}
            QSlider::handle:horizontal {{
                width: {int(28 * scale)}px;
                height: {int(28 * scale)}px;
                margin: {int(-10 * scale)}px 0;
                border-radius: {int(14 * scale)}px;
                background: {T('TEXT_PRIMARY')};
                border: 2px solid {T('PRIMARY')};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(int(34 * scale), int(26 * scale), int(34 * scale), int(24 * scale))
        layout.setSpacing(int(16 * scale))

        title = QLabel("亮度設定")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: {title_font_size}px; font-weight: bold;")
        layout.addWidget(title)

        self.default_slider, self.default_value_label = self._add_slider_row(
            layout, "預設亮度", slider_height
        )

        self.night_checkbox = QCheckBox("啟用夜間亮度")
        self.night_checkbox.stateChanged.connect(self._on_night_enabled_changed)
        layout.addWidget(self.night_checkbox)

        self.night_slider, self.night_value_label = self._add_slider_row(
            layout, "夜間亮度", slider_height
        )

        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_btn = QPushButton("取消")
        ok_btn = QPushButton("確定")
        for btn in (cancel_btn, ok_btn):
            btn.setFixedSize(int(130 * scale), btn_height)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {T('BG_CARD_ALT')};
                    color: {T('TEXT_PRIMARY')};
                    border: 1px solid {T('BORDER_DEFAULT')};
                    border-radius: {radius}px;
                    font-size: {font_size}px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {T('BORDER_HOVER')};
                }}
            """)
        ok_btn.setStyleSheet(ok_btn.styleSheet() + f"""
            QPushButton {{
                background-color: {T('PRIMARY')};
                color: #081018;
                border: none;
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        ok_btn.clicked.connect(self._save_and_accept)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(ok_btn)
        layout.addLayout(buttons)

    def _add_slider_row(self, parent_layout: QVBoxLayout, label_text: str, slider_height: int):
        row = QHBoxLayout()
        label = QLabel(label_text)
        value_label = QLabel("100%")
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value_label.setFixedWidth(70)
        row.addWidget(label)
        row.addStretch()
        row.addWidget(value_label)
        parent_layout.addLayout(row)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(10, 100)
        slider.setSingleStep(5)
        slider.setPageStep(10)
        slider.setFixedHeight(slider_height)
        slider.valueChanged.connect(self._on_slider_changed)
        parent_layout.addWidget(slider)
        return slider, value_label

    def _load_values(self, settings: BrightnessSettings):
        self._loading_values = True
        self.default_slider.setValue(clamp_brightness_percent(settings.default_percent))
        self.night_checkbox.setChecked(settings.night_enabled)
        self.night_slider.setValue(clamp_brightness_percent(settings.night_percent))
        self._loading_values = False
        self._sync_labels()
        self._sync_night_slider_enabled()

    def _current_settings(self) -> BrightnessSettings:
        return BrightnessSettings(
            default_percent=clamp_brightness_percent(self.default_slider.value()),
            night_enabled=self.night_checkbox.isChecked(),
            night_percent=clamp_brightness_percent(self.night_slider.value()),
        )

    def _sync_labels(self):
        self.default_value_label.setText(f"{self.default_slider.value()}%")
        self.night_value_label.setText(f"{self.night_slider.value()}%")

    def _sync_night_slider_enabled(self):
        enabled = self.night_checkbox.isChecked()
        self.night_slider.setEnabled(enabled)
        self.night_value_label.setEnabled(enabled)

    def _preview_percent(self, source_slider: QSlider) -> int:
        if source_slider is self.night_slider:
            return self.night_slider.value()
        return self.default_slider.value()

    def _on_slider_changed(self):
        self._sync_labels()
        if self._loading_values:
            return
        if self.dashboard and hasattr(self.dashboard, "set_brightness_percent"):
            self.dashboard.set_brightness_percent(self._preview_percent(self.sender()), persist_manual=False)

    def _on_night_enabled_changed(self):
        self._sync_night_slider_enabled()
        if self._loading_values:
            return
        if self.dashboard and hasattr(self.dashboard, "set_brightness_percent"):
            percent = self.night_slider.value() if self.night_checkbox.isChecked() else self.default_slider.value()
            self.dashboard.set_brightness_percent(percent, persist_manual=False)

    def _save_and_accept(self):
        settings = self._current_settings()
        save_brightness_settings(settings)
        if self.dashboard and hasattr(self.dashboard, "reload_brightness_settings"):
            self.dashboard.reload_brightness_settings()
        self.accept()

    def reject(self):
        if self.dashboard and hasattr(self.dashboard, "set_brightness_percent"):
            self.dashboard.set_brightness_percent(self.original_percent, persist_manual=False)
        super().reject()


def show_brightness_settings_popup(parent=None, dashboard=None):
    dialog = BrightnessSettingsDialog(parent=parent, dashboard=dashboard)

    anchor_geo = parent.frameGeometry() if parent else None
    screen = QApplication.screenAt(anchor_geo.center()) if anchor_geo else QApplication.primaryScreen()
    if screen is None:
        screen = QApplication.primaryScreen()

    if screen:
        available = screen.availableGeometry()
        if anchor_geo:
            x = anchor_geo.x() + (anchor_geo.width() - dialog.width()) // 2
            y = anchor_geo.y() + (anchor_geo.height() - dialog.height()) // 2
        else:
            x = available.x() + (available.width() - dialog.width()) // 2
            y = available.y() + (available.height() - dialog.height()) // 2
        max_x = available.x() + available.width() - dialog.width()
        max_y = available.y() + available.height() - dialog.height()
        x = max(available.x(), min(x, max_x))
        y = max(available.y(), min(y, max_y))
        dialog.move(x, y)

    dialog.raise_()
    dialog.activateWindow()
    return dialog.exec()
