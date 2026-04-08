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
        
        dialog_width = int(350 * scale)
        dialog_height = int(280 * scale)
        title_font_size = max(12, int(20 * scale))
        label_font_size = max(10, int(14 * scale))
        combo_height = int(40 * scale)
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
        
        preview_label = QLabel("預覽:")
        preview_label.setStyleSheet(f"font-size: {label_font_size}px;")
        layout.addWidget(preview_label)
        
        self.preview_widget = QWidget()
        self.preview_widget.setFixedHeight(int(50 * scale))
        preview_layout = QHBoxLayout(self.preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(int(10 * scale))
        
        self.preview_btn = QPushButton("套用")
        self.preview_btn.setFixedHeight(combo_height)
        self.preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {T('PRIMARY')};
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: {btn_radius}px;
                font-size: {int(14 * scale)}px;
                font-weight: bold;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                opacity: 0.85;
            }}
        """)
        preview_layout.addWidget(self.preview_btn)
        preview_layout.addStretch()
        layout.addWidget(self.preview_widget)
        
        select_label = QLabel("選擇顏色:")
        select_label.setStyleSheet(f"font-size: {label_font_size}px; margin-top: {int(10 * scale)}px;")
        layout.addWidget(select_label)
        
        self.color_combo = QComboBox()
        self.color_combo.setFixedHeight(combo_height)
        self.color_combo.currentIndexChanged.connect(self.on_color_changed)
        
        manager = get_theme_manager()
        current_accent = manager.accent_color
        
        for name, color_hex in ACCENT_COLOR_PRESETS.items():
            self.color_combo.addItem(name, color_hex)
            if color_hex == current_accent:
                self.color_combo.setCurrentIndex(self.color_combo.count() - 1)
        
        layout.addWidget(self.color_combo)
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(int(15 * scale))
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(int(40 * scale))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
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
        cancel_btn.clicked.connect(self.close)
        
        apply_btn = QPushButton("確定")
        apply_btn.setFixedHeight(int(40 * scale))
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {T('PRIMARY')};
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: {btn_radius}px;
                font-size: {int(13 * scale)}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                opacity: 0.85;
            }}
        """)
        apply_btn.clicked.connect(self.apply_color)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(apply_btn)
        
        layout.addLayout(btn_layout)
    
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
        btn_radius = max(5, int(8 * scale))
        
        self.preview_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color_hex};
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: {btn_radius}px;
                font-size: {int(14 * scale)}px;
                font-weight: bold;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                opacity: 0.85;
            }}
        """)
    
    def apply_color(self):
        """套用顏色並關閉"""
        color_hex = self.color_combo.currentData()
        if color_hex:
            manager = get_theme_manager()
            manager.set_accent_color(color_hex)
            self.signals.accent_color_changed.emit(color_hex)
        self.close()
