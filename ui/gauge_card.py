import time
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QProgressBar, 
                             QGridLayout, QSizePolicy, QPushButton, QHBoxLayout)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath, QLinearGradient
from PyQt6.QtCore import QRectF

from ui.theme import T


class DigitalGaugeCard(QWidget):
    """數位儀表卡片 - 用於顯示轉速、水溫等數值"""
    
    def __init__(self, title="", unit="", min_val=0, max_val=100, 
                 warning_threshold=None, danger_threshold=None,
                 decimal_places=0, parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.min_val = min_val
        self.max_val = max_val
        self.warning_threshold = warning_threshold
        self.danger_threshold = danger_threshold
        self.decimal_places = decimal_places
        self.current_value = 0
        
        self.setStyleSheet("background: transparent;")
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(8)
        
        self.title_label = QLabel(self.title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 18px;
            font-weight: bold;
            background: transparent;
            letter-spacing: 2px;
        """)
        
        self.value_label = QLabel("0")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setStyleSheet(f"""
            color: {T('PRIMARY')};
            font-size: 72px;
            font-weight: bold;
            font-family: 'Arial', 'Helvetica', sans-serif;
            background: transparent;
        """)
        
        self.unit_label = QLabel(self.unit)
        self.unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_label.setStyleSheet(f"""
            color: {T('TEXT_DISABLED')};
            font-size: 16px;
            background: transparent;
        """)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {T('BG_CARD_ALT')};
                border-radius: 6px;
                border: 1px solid {T('BORDER_HOVER')};
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a9eff, stop:1 {T('PRIMARY')});
                border-radius: 5px;
            }}
        """)
        
        layout.addStretch()
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.unit_label)
        layout.addSpacing(10)
        layout.addWidget(self.progress_bar)
        layout.addStretch()
    
    def set_value(self, value):
        self.current_value = value
        
        if self.decimal_places == 0:
            display_text = f"{int(value):,}"
        else:
            display_text = f"{value:,.{self.decimal_places}f}"
        
        self.value_label.setText(display_text)
        
        progress = int((value - self.min_val) / (self.max_val - self.min_val) * 100)
        progress = max(0, min(100, progress))
        self.progress_bar.setValue(progress)
        
        if self.danger_threshold and value >= self.danger_threshold:
            color = "#f44"
            bar_style = """
                QProgressBar {
                    background: #2a2a35;
                    border-radius: 6px;
                    border: 1px solid #3a3a45;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #f44, stop:1 #f66);
                    border-radius: 5px;
                }
            """
        elif self.warning_threshold and value >= self.warning_threshold:
            color = "#fa0"
            bar_style = """
                QProgressBar {
                    background: #2a2a35;
                    border-radius: 6px;
                    border: 1px solid #3a3a45;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #fa0, stop:1 #fc6);
                    border-radius: 5px;
                }
            """
        else:
            color = "#6af"
            bar_style = """
                QProgressBar {
                    background: #2a2a35;
                    border-radius: 6px;
                    border: 1px solid #3a3a45;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #4a9eff, stop:1 #6af);
                    border-radius: 5px;
                }
            """
        
        self.value_label.setStyleSheet(f"""
            color: {color};
            font-size: 72px;
            font-weight: bold;
            font-family: 'Arial', 'Helvetica', sans-serif;
            background: transparent;
        """)
        self.progress_bar.setStyleSheet(bar_style)
    
    def refresh_theme(self):
        """重新整理 UI 主題顏色（更換強調色後呼叫）"""
        self.title_label.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 18px;
            font-weight: bold;
            background: transparent;
            letter-spacing: 2px;
        """)
        self.value_label.setStyleSheet(f"""
            color: {T('PRIMARY')};
            font-size: 72px;
            font-weight: bold;
            font-family: 'Arial', 'Helvetica', sans-serif;
            background: transparent;
        """)
        self.unit_label.setStyleSheet(f"""
            color: {T('TEXT_DISABLED')};
            font-size: 16px;
            background: transparent;
        """)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {T('BG_CARD_ALT')};
                border-radius: 6px;
                border: 1px solid {T('BORDER_HOVER')};
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a9eff, stop:1 {T('PRIMARY')});
                border-radius: 5px;
            }}
        """)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect().adjusted(5, 5, -5, -5)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 20, 20)
        
        gradient = QLinearGradient(0, 0, 0, rect.height())
        gradient.setColorAt(0, QColor(30, 30, 40, 200))
        gradient.setColorAt(1, QColor(20, 20, 30, 200))
        painter.fillPath(path, gradient)
        
        painter.setPen(QPen(QColor(60, 60, 80), 2))
        painter.drawPath(path)


class QuadGaugeCard(QWidget):
    """
    四宮格儀表卡片 - 顯示轉速/水溫/渦輪負壓/電瓶電壓
    支援點擊放大和焦點選擇機制
    """
    
    detail_requested = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(380, 380)
        
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a25, stop:1 #0f0f18);
                border-radius: 20px;
            }
        """)
        
        self.gauge_data = [
            {"title": "ENGINE", "unit": "RPM", "value": None, "min": 0, "max": 8000, 
             "warning": 5500, "danger": 6000, "decimals": 0},
            {"title": "COOLANT", "unit": "°C", "value": None, "min": 0, "max": 120, 
             "warning": 100, "danger": 110, "decimals": 0},
            {"title": "TURBO", "unit": "bar", "value": None, "min": -1.0, "max": 1.0, 
             "warning": 0.8, "danger": 0.95, "decimals": 2},
            {"title": "BATTERY", "unit": "V", "value": None, "min": 10, "max": 16, 
             "warning": 12.0, "danger": 11.0, "decimals": 1, "warning_below": True},
        ]
        
        self.focus_index = 0
        self.gauge_cells = []
        self.value_labels = []
        self._flash_timers = [None] * 4
        self._flash_state = [False] * 4
        self._danger_latched = [False] * 4
        
        self._init_ui()
    
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)
        
        grid_container = QWidget()
        grid_container.setStyleSheet("background: transparent;")
        grid_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        grid_layout = QGridLayout(grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(8)
        
        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        for i, (row, col) in enumerate(positions):
            cell = self._create_gauge_cell(i)
            self.gauge_cells.append(cell)
            grid_layout.addWidget(cell, row, col)
            grid_layout.setRowStretch(row, 1)
            grid_layout.setColumnStretch(col, 1)
        
        main_layout.addWidget(grid_container, 1)
    
    def _create_gauge_cell(self, index):
        data = self.gauge_data[index]
        
        cell = QWidget()
        cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        cell.setStyleSheet(f"""
            QWidget {{
                background: rgba(30, 30, 40, 0.5);
                border-radius: 12px;
                border: 2px solid #2a2a35;
            }}
        """)
        
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)
        
        title = QLabel(f"{data['title']} ({data['unit']})")
        title.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 12px;
            font-weight: bold;
            background: transparent;
            letter-spacing: 1px;
            margin: 0px;
            padding: 0px;
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        title.setMargin(0)
        title.setFixedHeight(title.sizeHint().height())
        
        value_label = QLabel(self._format_value(data["value"], data["decimals"]))
        value_label.setStyleSheet(f"""
            color: {T('PRIMARY')};
            font-size: 54px;
            font-weight: bold;
            background: transparent;
        """)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_labels.append(value_label)
        
        progress = QProgressBar()
        progress.setFixedHeight(8)
        progress.setTextVisible(False)
        progress.setMinimum(0)
        progress.setMaximum(100)
        progress.setValue(self._calc_progress(index))
        progress.setStyleSheet("""
            QProgressBar {
                background: #2a2a35;
                border-radius: 3px;
                border: none;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a9eff, stop:1 #6af);
                border-radius: 3px;
            }
        """)
        
        cell.progress_bar = progress
        
        layout.addWidget(title)
        layout.addWidget(value_label)
        layout.addWidget(progress)
        
        return cell
    
    def _format_value(self, value, decimals):
        if value is None:
            return "--"
        if decimals == 0:
            return f"{int(value):,}"
        else:
            return f"{value:.{decimals}f}"
    
    def _calc_progress(self, index):
        data = self.gauge_data[index]
        value = data["value"]
        if value is None:
            return 0
        min_val = data["min"]
        max_val = data["max"]
        progress = int((value - min_val) / (max_val - min_val) * 100)
        return max(0, min(100, progress))
    
    def _get_value_color(self, index):
        data = self.gauge_data[index]
        value = data["value"]
        
        if value is None:
            return "#666"
        
        warning = data.get("warning")
        danger = data.get("danger")
        warning_below = data.get("warning_below", False)
        
        if index == 2 and value >= 0:
            return "#f44"
        
        if warning_below:
            if danger is not None and value <= danger:
                return "#f44"
            elif warning is not None and value <= warning:
                return "#fa0"
        else:
            if danger is not None and value >= danger:
                return "#f44"
            elif warning is not None and value >= warning:
                return "#fa0"
        return "#6af"

    def _set_label_style(self, index, color):
        self.value_labels[index].setStyleSheet(f"""
            color: {color};
            font-size: 54px;
            font-weight: bold;
            background: transparent;
        """)

    def _update_flash(self, index, is_danger, danger_color):
        timer = self._flash_timers[index]

        if not is_danger:
            if timer:
                timer.stop()
                timer.deleteLater()
                self._flash_timers[index] = None
                self._flash_state[index] = False
            self._set_label_style(index, danger_color)
            return

        if timer:
            return

        self._set_label_style(index, danger_color)

        blink_timer = QTimer(self)
        blink_timer.setInterval(400)

        def toggle(idx=index, on_color=danger_color):
            self._flash_state[idx] = not self._flash_state[idx]
            if self._flash_state[idx]:
                self._set_label_style(idx, on_color)
            else:
                self._set_label_style(idx, "#fff")

        blink_timer.timeout.connect(toggle)
        blink_timer.start()
        self._flash_timers[index] = blink_timer

    def reset_danger_latch(self, index=None):
        if index is None:
            self._danger_latched = [False] * 4
            return
        if 0 <= index < 4:
            self._danger_latched[index] = False
    
    def set_rpm(self, value):
        self._set_value(0, value)
    
    def set_coolant_temp(self, value):
        self._set_value(1, value)
    
    def set_intake_manifold_pressure(self, value):
        self._set_value(2, value)
    
    def set_boost(self, value):
        self._set_value(2, value)
    
    def set_turbo(self, value):
        self._set_value(2, value)
    
    def set_battery_voltage(self, value):
        self._set_value(3, value)
    
    def set_battery(self, value):
        self._set_value(3, value)
    
    def _set_value(self, index, value):
        self.gauge_data[index]["value"] = value
        
        data = self.gauge_data[index]
        self.value_labels[index].setText(self._format_value(value, data["decimals"]))
        
        color = self._get_value_color(index)
        is_danger = False
        if value is not None:
            warning = data.get("warning")
            danger = data.get("danger")
            warning_below = data.get("warning_below", False)
            if warning_below:
                if danger is not None and value <= danger:
                    is_danger = True
            else:
                if danger is not None and value >= danger:
                    is_danger = True

        skip_danger_popup = (index == 3 and value is not None and value <= 0.5)
        if is_danger and index in (1, 3) and not self._danger_latched[index] and not skip_danger_popup:
            self._danger_latched[index] = True
            self.detail_requested.emit(index)
        elif not is_danger:
            self._danger_latched[index] = False

        self._update_flash(index, is_danger, color)
        if not is_danger:
            self._set_label_style(index, color)
        
        cell = self.gauge_cells[index]
        progress = self._calc_progress(index)
        cell.progress_bar.setValue(progress)
        
        if color == "#f44":
            bar_color = "stop:0 #f44, stop:1 #f66"
        elif color == "#fa0":
            bar_color = "stop:0 #fa0, stop:1 #fc6"
        else:
            bar_color = "stop:0 #4a9eff, stop:1 #6af"
        
        cell.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: #2a2a35;
                border-radius: 3px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    {bar_color});
                border-radius: 3px;
            }}
        """)
    
    def get_focus(self):
        return self.focus_index
    
    def set_focus(self, index):
        self.focus_index = max(0, min(4, index))
        self._update_focus_style()
    
    def next_focus(self):
        if self.focus_index == 0:
            self.focus_index = 1
            self._update_focus_style()
            return True
        elif self.focus_index < 4:
            self.focus_index += 1
            self._update_focus_style()
            return True
        else:
            self.focus_index = 0
            self._update_focus_style()
            return False
    
    def clear_focus(self):
        self.focus_index = 0
        self._update_focus_style()
    
    def _update_focus_style(self):
        for i, cell in enumerate(self.gauge_cells):
            if i + 1 == self.focus_index:
                cell.setStyleSheet("""
                    QWidget {
                        background: rgba(100, 170, 255, 0.15);
                        border-radius: 12px;
                        border: 3px solid #6af;
                    }
                """)
            else:
                cell.setStyleSheet("""
                    QWidget {
                        background: rgba(30, 30, 40, 0.5);
                        border-radius: 12px;
                        border: 2px solid #2a2a35;
                    }
                """)
    
    def enter_detail_view(self):
        if self.focus_index > 0:
            self.detail_requested.emit(self.focus_index - 1)
            return True
        return False
    
    def get_gauge_data(self, index):
        if 0 <= index < 4:
            return self.gauge_data[index].copy()
        return None
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.pos()
            self._press_time = time.time()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and hasattr(self, '_press_pos') and self._press_pos:
            release_pos = event.pos()
            dx = abs(release_pos.x() - self._press_pos.x())
            dy = abs(release_pos.y() - self._press_pos.y())
            elapsed = time.time() - self._press_time if hasattr(self, '_press_time') else 0
            
            if dx < 20 and dy < 20 and elapsed < 0.5:
                clicked_index = self._get_cell_at_pos(release_pos)
                if clicked_index >= 0:
                    self.set_focus(clicked_index + 1)
                    print(f"點擊儀表 {clicked_index + 1}：進入詳細視圖")
                    self.detail_requested.emit(clicked_index)
            
            self._press_pos = None
            self._press_time = None
        super().mouseReleaseEvent(event)
    
    def _get_cell_at_pos(self, pos):
        for i, cell in enumerate(self.gauge_cells):
            cell_pos = cell.mapFrom(self, pos)
            if cell.rect().contains(cell_pos):
                return i
        return -1
    
    def refresh_theme(self):
        """重新整理 UI 主題顏色（更換強調色後呼叫）"""
        for i, value_label in enumerate(self.value_labels):
            value_label.setStyleSheet(f"""
                color: {T('PRIMARY')};
                font-size: 54px;
                font-weight: bold;
                background: transparent;
            """)
            if hasattr(self.gauge_cells[i], 'progress_bar'):
                self.gauge_cells[i].progress_bar.setStyleSheet(f"""
                    QProgressBar {{
                        background: #2a2a35;
                        border-radius: 3px;
                        border: none;
                    }}
                    QProgressBar::chunk {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #4a9eff, stop:1 {T('PRIMARY')});
                        border-radius: 3px;
                    }}
                """)


class QuadGaugeDetailView(QWidget):
    """
    四宮格儀表詳細視圖 - 全尺寸顯示單一儀表
    左上角有返回按鈕
    """
    
    back_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(380, 380)
        
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a25, stop:1 #0f0f18);
                border-radius: 20px;
            }
        """)
        
        self.current_data = None
        self._swipe_start_pos = None
        self._swipe_start_time = None
        self._swipe_threshold = 80
        
        self._init_ui()
    
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        top_bar = QWidget()
        top_bar.setStyleSheet("background: transparent;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        self.back_btn = QPushButton("◀ 返回")
        self.back_btn.setFixedSize(80, 35)
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(100, 150, 255, 0.2);
                color: {T('PRIMARY')};
                border: 2px solid {T('PRIMARY')};
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(100, 150, 255, 0.4);
            }}
            QPushButton:pressed {{
                background-color: rgba(100, 150, 255, 0.6);
            }}
        """)
        self.back_btn.clicked.connect(self.back_requested.emit)
        
        top_layout.addWidget(self.back_btn)
        top_layout.addStretch()
        
        main_layout.addWidget(top_bar)
        
        self.title_label = QLabel("ENGINE")
        self.title_label.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 22px;
            font-weight: bold;
            background: transparent;
            letter-spacing: 3px;
        """)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.title_label)
        
        self.value_label = QLabel("0")
        self.value_label.setStyleSheet(f"""
            color: {T('PRIMARY')};
            font-size: 96px;
            font-weight: bold;
            background: transparent;
        """)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.value_label)
        
        self.unit_label = QLabel("RPM")
        self.unit_label.setStyleSheet(f"""
            color: {T('TEXT_DISABLED')};
            font-size: 20px;
            background: transparent;
        """)
        self.unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.unit_label)
        
        main_layout.addSpacing(10)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: #2a2a35;
                border-radius: 8px;
                border: 1px solid #3a3a45;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a9eff, stop:1 #6af);
                border-radius: 7px;
            }}
        """)
        main_layout.addWidget(self.progress_bar)
        
        range_layout = QHBoxLayout()
        self.min_label = QLabel("0")
        self.min_label.setStyleSheet(f"color: {T('TEXT_DISABLED')}; font-size: 12px; background: transparent;")
        self.max_label = QLabel("8000")
        self.max_label.setStyleSheet(f"color: {T('TEXT_DISABLED')}; font-size: 12px; background: transparent;")
        range_layout.addWidget(self.min_label)
        range_layout.addStretch()
        range_layout.addWidget(self.max_label)
        main_layout.addLayout(range_layout)
        
        main_layout.addStretch()
        
        hint_label = QLabel("點擊左上角返回")
        hint_label.setStyleSheet(f"""
            color: {T('TEXT_DISABLED')};
            font-size: 12px;
            background: transparent;
        """)
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(hint_label)
    
    def set_gauge_data(self, data):
        self.current_data = data
        if data:
            self.title_label.setText(data["title"])
            self.unit_label.setText(data["unit"])
            self.min_label.setText(str(data["min"]))
            self.max_label.setText(str(data["max"]))
            self.update_value(data["value"])
    
    def update_value(self, value):
        if not self.current_data:
            return
        
        data = self.current_data
        data["value"] = value
        
        if value is None:
            self.value_label.setText("--")
            color = "#666"
            progress = 0
        else:
            decimals = data.get("decimals", 0)
            if decimals == 0:
                self.value_label.setText(f"{int(value):,}")
            else:
                self.value_label.setText(f"{value:.{decimals}f}")
            color = self._get_value_color()
            progress = int((value - data["min"]) / (data["max"] - data["min"]) * 100)
            progress = max(0, min(100, progress))
        
        self.value_label.setStyleSheet(f"""
            color: {color};
            font-size: 96px;
            font-weight: bold;
            background: transparent;
        """)
        
        self.progress_bar.setValue(progress)
        
        if color == "#f44":
            bar_color = "stop:0 #f44, stop:1 #f66"
        elif color == "#fa0":
            bar_color = "stop:0 #fa0, stop:1 #fc6"
        else:
            bar_color = "stop:0 #4a9eff, stop:1 #6af"
        
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: #2a2a35;
                border-radius: 8px;
                border: 1px solid #3a3a45;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    {bar_color});
                border-radius: 7px;
            }}
        """)
    
    def _get_value_color(self):
        if not self.current_data:
            return "#6af"
        
        data = self.current_data
        value = data["value"]
        
        if value is None:
            return "#666"
        
        warning = data.get("warning")
        danger = data.get("danger")
        warning_below = data.get("warning_below", False)
        
        if data.get("title") == "TURBO" and value >= 0:
            return "#f44"
        
        if warning_below:
            if danger is not None and value <= danger:
                return "#f44"
            elif warning is not None and value <= warning:
                return "#fa0"
        else:
            if danger is not None and value >= danger:
                return "#f44"
            elif warning is not None and value >= warning:
                return "#fa0"
        return "#6af"
    
    def set_value(self, value):
        self.update_value(value)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._swipe_start_pos = event.pos()
            self._swipe_start_time = time.time()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._swipe_start_pos:
            end_pos = event.pos()
            dx = end_pos.x() - self._swipe_start_pos.x()
            dy = abs(end_pos.y() - self._swipe_start_pos.y())
            elapsed = time.time() - self._swipe_start_time if self._swipe_start_time else 1
            
            if dx > self._swipe_threshold and dy < abs(dx) and elapsed < 0.5:
                print("滑動返回：由左往右滑動")
                self.back_requested.emit()
            
            self._swipe_start_pos = None
            self._swipe_start_time = None
        super().mouseReleaseEvent(event)
