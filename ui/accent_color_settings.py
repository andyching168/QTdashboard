"""
強調色設定對話框

讓使用者選擇 UI 強調色，支援多個預設顏色選項。
"""

from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QApplication, QMainWindow, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

from ui.theme import T, ACCENT_COLOR_PRESETS, get_theme_manager


class AccentColorSignals(QObject):
    accent_color_changed = pyqtSignal(str)


class AccentColorSettingsDialog(QDialog):
    """強調色設定對話框"""
    
    signals = AccentColorSignals()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent_ref = parent
        self._live_preview_enabled = True
        self.init_ui()

    def showEvent(self, event):
        super().showEvent(event)
        app = QApplication.instance()
        parent_widget = self.parentWidget()

        anchor = None
        if parent_widget is not None:
            anchor = parent_widget.window() if parent_widget.window() else parent_widget
        elif app and app.activeWindow() is not self:
            anchor = app.activeWindow()

        anchor_geo = anchor.frameGeometry() if anchor else None
        screen = QApplication.screenAt(anchor_geo.center()) if anchor_geo else QApplication.primaryScreen()
        if screen is None:
            screen = QApplication.primaryScreen()

        if screen:
            available = screen.availableGeometry()
            if anchor_geo:
                x = anchor_geo.x() + (anchor_geo.width() - self.width()) // 2
                y = anchor_geo.y() + (anchor_geo.height() - self.height()) // 2
            else:
                x = available.x() + (available.width() - self.width()) // 2
                y = available.y() + (available.height() - self.height()) // 2

            max_x = available.x() + available.width() - self.width()
            max_y = available.y() + available.height() - self.height()
            x = max(available.x(), min(x, max_x))
            y = max(available.y(), min(y, max_y))
            self.move(x, y)

        self.raise_()
        self.activateWindow()
    
    def _get_window_scale(self):
        """取得視窗縮放比例"""
        parent_width = 1920
        parent_height = 480
        
        widget = self._parent_ref
        while widget:
            parent = widget.parent() if hasattr(widget, 'parent') else None
            if parent is None:
                if isinstance(widget, QMainWindow):
                    parent_width = widget.width()
                    parent_height = widget.height()
                break
            if isinstance(parent, QMainWindow):
                parent_width = parent.width()
                parent_height = parent.height()
                break
            widget = parent
        
        if parent_width == 1920 and parent_height == 480:
            screen = QApplication.primaryScreen()
            if screen:
                geometry = screen.availableGeometry()
                if geometry.width() < 1920 or geometry.height() < 480:
                    parent_width = geometry.width()
                    parent_height = min(geometry.height(), int(geometry.width() / 4))
        
        scale = min(parent_width / 1920, parent_height / 480)
        return scale, parent_width, parent_height
    
    def init_ui(self):
        scale, parent_width, parent_height = self._get_window_scale()
        
        dialog_width = int(360 * scale)
        dialog_height = int(220 * scale)
        title_font_size = max(12, int(20 * scale))
        label_font_size = max(10, int(14 * scale))
        combo_height = int(40 * scale)
        swatch_height = int(56 * scale)
        btn_radius = max(5, int(8 * scale))
        margin = max(15, int(25 * scale))
        spacing = max(8, int(12 * scale))
        
        self.setWindowTitle("主題強調色設定")
        self.setFixedSize(dialog_width, dialog_height)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {T('BG_CARD')};
            }}
            QLabel {{
                color: {T('TEXT_PRIMARY')};
                background: transparent;
            }}
            QComboBox {{
                background-color: {T('BG_INPUT')};
                color: {T('TEXT_PRIMARY')};
                border: 1px solid {T('BORDER_DEFAULT')};
                border-radius: {btn_radius}px;
                padding: 5px 10px;
                font-size: {label_font_size}px;
            }}
            QComboBox:hover {{
                border-color: {T('BORDER_HOVER')};
            }}
            QComboBox::dropDown {{
                border: none;
                background-color: {T('BG_CARD_ALT')};
            }}
            QComboBox::downArrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {T('TEXT_SECONDARY')};
                margin-right: 10px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {T('BG_INPUT')};
                color: {T('TEXT_PRIMARY')};
                border: 1px solid {T('BORDER_DEFAULT')};
                selection-background-color: {T('BORDER_ACTIVE')};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(spacing)
        
        title = QLabel("🎨 強調色設定")
        title.setStyleSheet(f"font-size: {title_font_size}px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        swatch_label = QLabel("顏色預覽:")
        swatch_label.setStyleSheet(f"font-size: {label_font_size}px;")
        layout.addWidget(swatch_label)

        self.color_swatch = QWidget()
        self.color_swatch.setFixedHeight(swatch_height)
        self.color_swatch.setStyleSheet(f"""
            background-color: {T('PRIMARY')};
            border-radius: {btn_radius}px;
            border: 1px solid {T('BORDER_DEFAULT')};
        """)
        layout.addWidget(self.color_swatch)
        
        select_label = QLabel("選擇顏色:")
        select_label.setStyleSheet(f"font-size: {label_font_size}px; margin-top: {int(10 * scale)}px;")
        layout.addWidget(select_label)
        
        self.color_combo = QComboBox()
        self.color_combo.setFixedHeight(combo_height)
        
        manager = get_theme_manager()
        current_accent = manager.accent_color
        
        for name, color_hex in ACCENT_COLOR_PRESETS.items():
            self.color_combo.addItem(name, color_hex)
            if color_hex == current_accent:
                self.color_combo.setCurrentIndex(self.color_combo.count() - 1)

        # 初始化完成後才連接事件，避免開啟視窗時觸發即時套色
        self.color_combo.currentIndexChanged.connect(self.on_color_changed)
        
        layout.addWidget(self.color_combo)
        layout.addStretch()

        close_btn = QPushButton("關閉")
        close_btn.setFixedHeight(int(40 * scale))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {T('BG_CARD_ALT')};
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: {btn_radius}px;
                font-size: {int(13 * scale)}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {T('BORDER_HOVER')};
            }}
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
    
    def on_color_changed(self, index: int):
        """當選擇的顏色改變時，即時預覽"""
        if not self._live_preview_enabled:
            return
        
        color_hex = self.color_combo.currentData()
        if not color_hex:
            return
        
        manager = get_theme_manager()
        manager.set_accent_color(color_hex)

        scale, _, _ = self._get_window_scale()

        self.color_swatch.setStyleSheet(f"""
            background-color: {color_hex};
            border-radius: {max(5, int(8 * scale))}px;
            border: 1px solid {T('BORDER_DEFAULT')};
        """)


def show_accent_color_popup(parent=None, on_changed=None):
    """顯示強調色設定彈窗（採用與電源選單相同的即時建立/exec 模式）"""
    app = QApplication.instance()
    dialog_parent = parent if parent else (app.activeWindow() if app else None)

    parent_width = 1920
    parent_height = 480
    if dialog_parent:
        parent_width = max(1, dialog_parent.width())
        parent_height = max(1, dialog_parent.height())
    else:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            parent_width = geo.width()
            parent_height = min(geo.height(), int(geo.width() / 4))

    scale = min(parent_width / 1920, parent_height / 480)

    dialog_width = max(320, int(360 * scale))
    title_font_size = max(12, int(20 * scale))
    label_font_size = max(10, int(14 * scale))
    combo_height = max(34, int(40 * scale))
    swatch_height = max(52, int(56 * scale))
    close_btn_height = max(36, int(40 * scale))
    btn_radius = max(5, int(8 * scale))
    margin = max(15, int(25 * scale))
    spacing = max(8, int(12 * scale))

    title_min_height = max(30, int(34 * scale))
    label_min_height = max(18, int(20 * scale))
    content_height = (
        (margin * 2)
        + title_min_height
        + spacing
        + label_min_height
        + spacing
        + swatch_height
        + spacing
        + label_min_height
        + spacing
        + combo_height
        + spacing
        + close_btn_height
    )
    dialog_height = min(max(180, parent_height - 16), max(int(220 * scale), content_height))

    dialog = QDialog(dialog_parent)
    dialog.setWindowTitle("強調色設定")
    dialog.setFixedSize(dialog_width, dialog_height)
    dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
    dialog.setStyleSheet(f"""
        QDialog {{
            background-color: {T('BG_CARD')};
        }}
        QLabel {{
            color: {T('TEXT_PRIMARY')};
            background: transparent;
        }}
        QComboBox {{
            background-color: {T('BG_INPUT')};
            color: {T('TEXT_PRIMARY')};
            border: 1px solid {T('BORDER_DEFAULT')};
            border-radius: {btn_radius}px;
            padding: 5px 10px;
            font-size: {label_font_size}px;
        }}
        QComboBox:hover {{
            border-color: {T('BORDER_HOVER')};
        }}
        QComboBox::dropDown {{
            border: none;
            background-color: {T('BG_CARD_ALT')};
        }}
        QComboBox::downArrow {{
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid {T('TEXT_SECONDARY')};
            margin-right: 10px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {T('BG_INPUT')};
            color: {T('TEXT_PRIMARY')};
            border: 1px solid {T('BORDER_DEFAULT')};
            selection-background-color: {T('BORDER_ACTIVE')};
        }}
    """)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(spacing)

    title = QLabel("🎨 強調色設定")
    title.setStyleSheet(f"font-size: {title_font_size}px; font-weight: bold;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title.setMinimumHeight(title_min_height)
    layout.addWidget(title)

    swatch_label = QLabel("顏色預覽:")
    swatch_label.setStyleSheet(f"font-size: {label_font_size}px;")
    swatch_label.setMinimumHeight(label_min_height)
    layout.addWidget(swatch_label)

    color_swatch = QWidget()
    color_swatch.setFixedSize(swatch_height, swatch_height)
    color_swatch.setStyleSheet(f"""
        background-color: {T('PRIMARY')};
        border-radius: {btn_radius}px;
        border: 1px solid {T('BORDER_DEFAULT')};
    """)

    swatch_layout = QHBoxLayout()
    swatch_layout.addStretch()
    swatch_layout.addWidget(color_swatch)
    swatch_layout.addStretch()
    swatch_layout.setContentsMargins(0, 0, 0, 0)
    layout.addLayout(swatch_layout)

    layout.addSpacing(max(4, int(6 * scale)))
    select_label = QLabel("選擇顏色:")
    select_label.setStyleSheet(f"font-size: {label_font_size}px;")
    select_label.setMinimumHeight(label_min_height)
    layout.addWidget(select_label)

    color_combo = QComboBox()
    color_combo.setFixedHeight(combo_height)

    manager = get_theme_manager()
    current_accent = manager.accent_color
    for name, color_hex in ACCENT_COLOR_PRESETS.items():
        color_combo.addItem(name, color_hex)
        if color_hex == current_accent:
            color_combo.setCurrentIndex(color_combo.count() - 1)

    def _on_color_changed(index: int):
        color_hex = color_combo.currentData()
        if not color_hex:
            return

        manager.set_accent_color(color_hex)
        color_swatch.setStyleSheet(f"""
            background-color: {color_hex};
            border-radius: {btn_radius}px;
            border: 1px solid {T('BORDER_DEFAULT')};
        """)
        if callable(on_changed):
            on_changed(color_hex)

    color_combo.currentIndexChanged.connect(_on_color_changed)
    layout.addWidget(color_combo)

    close_btn = QPushButton("關閉")
    close_btn.setFixedHeight(close_btn_height)
    close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    close_btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {T('BG_CARD_ALT')};
            color: {T('TEXT_PRIMARY')};
            border: none;
            border-radius: {btn_radius}px;
            font-size: {int(13 * scale)}px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {T('BORDER_HOVER')};
        }}
    """)
    close_btn.clicked.connect(dialog.accept)
    layout.addWidget(close_btn)

    anchor_geo = dialog_parent.frameGeometry() if dialog_parent else None
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
    dialog.exec()
