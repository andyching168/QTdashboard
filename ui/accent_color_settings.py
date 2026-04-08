"""
強調色設定對話框

讓使用者選擇 UI 強調色，支援多個預設顏色選項。
"""

from PyQt6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QApplication, QMainWindow
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QPainter, QPixmap

from ui.theme import T, ACCENT_COLOR_PRESETS, get_theme_manager


class AccentColorSignals(QObject):
    accent_color_changed = pyqtSignal(str)


class AccentColorSettingsDialog(QDialog):
    """強調色設定對話框"""
    
    signals = AccentColorSignals()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent_ref = parent
        self.selected_color = None
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
        
        dialog_width = int(500 * scale)
        dialog_height = int(550 * scale)
        color_btn_size = int(80 * scale)
        title_font_size = max(12, int(24 * scale))
        label_font_size = max(10, int(16 * scale))
        btn_radius = max(5, int(10 * scale))
        margin = max(15, int(30 * scale))
        spacing = max(10, int(15 * scale))
        
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
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(spacing)
        
        title = QLabel("🎨 選擇強調色")
        title.setStyleSheet(f"font-size: {title_font_size}px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        current_label = QLabel(f"目前顏色:")
        current_label.setStyleSheet(f"font-size: {label_font_size}px;")
        layout.addWidget(current_label)
        
        current_color_widget = QWidget()
        current_color_widget.setFixedHeight(int(40 * scale))
        current_color_layout = QHBoxLayout(current_color_widget)
        current_color_layout.setContentsMargins(0, 0, 0, 0)
        
        self.current_color_preview = QLabel()
        self.current_color_preview.setFixedSize(int(120 * scale), int(30 * scale))
        self.current_color_preview.setStyleSheet(f"""
            background-color: {T('PRIMARY')};
            border-radius: {int(5 * scale)}px;
            border: 1px solid {T('BORDER_DEFAULT')};
        """)
        current_color_layout.addWidget(self.current_color_preview)
        current_color_layout.addStretch()
        layout.addWidget(current_color_widget)
        
        preset_label = QLabel("選擇預設顏色:")
        preset_label.setStyleSheet(f"font-size: {label_font_size}px; margin-top: {int(10 * scale)}px;")
        layout.addWidget(preset_label)
        
        colors_grid = QGridLayout()
        colors_grid.setSpacing(int(10 * scale))
        
        self.color_buttons = []
        manager = get_theme_manager()
        current_accent = manager.accent_color
        
        row, col = 0, 0
        for name, color_hex in ACCENT_COLOR_PRESETS.items():
            btn = QPushButton()
            btn.setFixedSize(color_btn_size, color_btn_size)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color_hex};
                    border-radius: {btn_radius}px;
                    border: 2px solid {T('BORDER_DEFAULT')};
                }}
                QPushButton:hover {{
                    border-color: {T('BORDER_HOVER')};
                }}
                QPushButton:selected {{
                    border-color: {T('TEXT_PRIMARY')};
                    border-width: 3px;
                }}
            """)
            btn._color_hex = color_hex
            btn._color_name = name
            btn.clicked.connect(lambda checked, c=color_hex, n=name: self.select_color(c, n))
            
            if color_hex == current_accent:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color_hex};
                        border-radius: {btn_radius}px;
                        border: 3px solid {T('TEXT_PRIMARY')};
                    }}
                """)
                self.selected_color = color_hex
            
            self.color_buttons.append(btn)
            colors_grid.addWidget(btn, row, col)
            
            col += 1
            if col >= 3:
                col = 0
                row += 1
        
        layout.addLayout(colors_grid)
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(int(15 * scale))
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(int(45 * scale))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {T('BG_CARD_ALT')};
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: {btn_radius}px;
                font-size: {int(14 * scale)}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {T('BORDER_HOVER')};
            }}
        """)
        cancel_btn.clicked.connect(self.close)
        
        apply_btn = QPushButton("套用")
        apply_btn.setFixedHeight(int(45 * scale))
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {T('PRIMARY')};
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: {btn_radius}px;
                font-size: {int(14 * scale)}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                opacity: 0.8;
            }}
        """)
        apply_btn.clicked.connect(self.apply_color)
        
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(apply_btn)
        
        layout.addLayout(btn_layout)
    
    def select_color(self, color_hex: str, color_name: str):
        """選擇顏色"""
        self.selected_color = color_hex
        manager = get_theme_manager()
        current_accent = manager.accent_color
        
        scale, _, _ = self._get_window_scale()
        btn_radius = max(5, int(10 * scale))
        
        for btn in self.color_buttons:
            if btn._color_hex == color_hex:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color_hex};
                        border-radius: {btn_radius}px;
                        border: 3px solid {T('TEXT_PRIMARY')};
                    }}
                """)
            elif btn._color_hex == current_accent:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {btn._color_hex};
                        border-radius: {btn_radius}px;
                        border: 3px solid {T('TEXT_PRIMARY')};
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {btn._color_hex};
                        border-radius: {btn_radius}px;
                        border: 2px solid {T('BORDER_DEFAULT')};
                    }}
                    QPushButton:hover {{
                        border-color: {T('BORDER_HOVER')};
                    }}
                """)
    
    def apply_color(self):
        """套用顏色"""
        if self.selected_color:
            manager = get_theme_manager()
            manager.set_accent_color(self.selected_color)
            self.signals.accent_color_changed.emit(self.selected_color)
            self.close()
