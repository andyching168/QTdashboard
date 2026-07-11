# Auto-extracted from main.py
import os
import time
import platform
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

from ui.theme import get_theme_manager, T


class SmartCalibrationChart(QWidget):
    """輕量的分層校正係數折線圖。"""
    def __init__(self, statuses, fallback, parent=None):
        super().__init__(parent)
        self.statuses = tuple(statuses)
        self.fallback = float(fallback)
        self._points = []
        self.setMinimumHeight(165)
        self.setMouseTracking(True)

    def _range(self):
        values = [s["coefficient"] for s in self.statuses if s["coefficient"] is not None]
        values.append(self.fallback)
        if len(values) <= 1:
            return 0.95, 1.05
        low, high = min(values), max(values)
        margin = max(0.01, (high - low) * 0.2)
        return low - margin, high + margin

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#15151a"))
        rect = self.rect().adjusted(55, 12, -20, -30)
        painter.setPen(QPen(QColor("#555b66"), 1))
        painter.drawRect(rect)
        if not any(s["samples"] for s in self.statuses):
            painter.setPen(QColor("#a0a4aa"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "尚未取得有效校正資料")
            return
        y_min, y_max = self._range()
        count = max(1, len(self.statuses) - 1)
        def point_for(index, value):
            x = rect.left() + rect.width() * index / count
            y = rect.bottom() - rect.height() * (value - y_min) / max(0.0001, y_max - y_min)
            return QPointF(x, y)
        fallback_y = point_for(0, self.fallback).y()
        fallback_pen = QPen(QColor("#8a8f98"), 1, Qt.PenStyle.DashLine)
        painter.setPen(fallback_pen)
        painter.drawLine(QPointF(rect.left(), fallback_y), QPointF(rect.right(), fallback_y))
        painter.drawText(4, int(fallback_y + 4), f"{self.fallback:.3f}")
        self._points = []
        previous = None
        for index, status in enumerate(self.statuses):
            value = status["coefficient"]
            x = rect.left() + rect.width() * index / count
            painter.setPen(QColor("#8a8f98"))
            painter.drawText(QRectF(x - 25, rect.bottom() + 5, 50, 20), Qt.AlignmentFlag.AlignCenter, status["label"])
            if value is None:
                continue
            point = point_for(index, value)
            mature = status["mature"]
            color = QColor("#4CAF50" if mature else "#FFB74D")
            if previous is not None:
                pen = QPen(color, 2, Qt.PenStyle.SolidLine if mature and previous[1] else Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(previous[0], point)
            painter.setPen(QPen(color, 2))
            painter.setBrush(color if mature else Qt.BrushStyle.NoBrush)
            painter.drawEllipse(point, 5, 5)
            self._points.append((point, status))
            previous = (point, mature)
        painter.setPen(QColor("#a0a4aa"))
        painter.drawText(4, rect.top() + 5, f"{y_max:.3f}")
        painter.drawText(4, rect.bottom(), f"{y_min:.3f}")

    def mousePressEvent(self, event):
        pos = event.position()
        for point, status in self._points:
            if (point.x() - pos.x()) ** 2 + (point.y() - pos.y()) ** 2 <= 196:
                state = "已成熟" if status["mature"] else "學習中"
                QToolTip.showText(event.globalPosition().toPoint(), f"{status['label']} km/h\n係數 {status['coefficient']:.4f}\n樣本 {status['samples']}\n{state}", self)
                break
        super().mousePressEvent(event)


class SmartCalibrationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("全時智慧速度校正")
        self.setFixedSize(1100, 440)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("""
            SmartCalibrationDialog {
                background-color: #111318;
                color: #f2f4f8;
            }
            QTableWidget {
                background-color: #1b1e24;
                alternate-background-color: #22262e;
                color: #f2f4f8;
                gridline-color: #454b57;
                border: 1px solid #454b57;
                selection-background-color: #315f85;
                selection-color: #ffffff;
                font-size: 15px;
            }
            QTableWidget::item {
                background-color: #1b1e24;
                color: #f2f4f8;
                padding: 4px;
            }
            QTableWidget::item:alternate {
                background-color: #22262e;
            }
            QTableWidget::item:selected {
                background-color: #315f85;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #292e37;
                color: #ffffff;
                border: 1px solid #454b57;
                padding: 5px;
                font-size: 15px;
                font-weight: bold;
            }
            QTableCornerButton::section {
                background-color: #292e37;
                border: 1px solid #454b57;
            }
            QScrollBar:vertical {
                background: #171a20;
                width: 20px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #5d6675;
                min-height: 32px;
                border-radius: 8px;
                margin: 2px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QPushButton {
                background-color: #2d333d;
                color: #ffffff;
                border: 1px solid #596273;
                border-radius: 8px;
                padding: 8px 18px;
                min-height: 28px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a4350;
            }
            QPushButton:pressed {
                background-color: #20252d;
            }
            QPushButton#resetCalibrationButton {
                background-color: #8b2f36;
                border-color: #c05259;
            }
            QPushButton#resetCalibrationButton:hover {
                background-color: #a43a42;
            }
        """)
        self._build()

    def _build(self):
        from vehicle import datagrab
        statuses = datagrab.get_smart_calibration_status()
        layout = QVBoxLayout(self)
        table = QTableWidget(len(statuses), 5)
        table.setHorizontalHeaderLabels(["速度層 km/h", "校正係數", "有效樣本", "狀態", "最後更新"])
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setMaximumHeight(155)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row, status in enumerate(statuses):
            updated = time.strftime("%m-%d %H:%M:%S", time.localtime(status["updated_at"])) if status["updated_at"] else "--"
            values = [status["label"], f"{status['coefficient']:.4f}" if status["coefficient"] is not None else "--", str(status["samples"]), "已成熟" if status["mature"] else "學習中", updated]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 3:
                    item.setForeground(QColor("#70d98b" if status["mature"] else "#ffc46b"))
                table.setItem(row, column, item)
        layout.addWidget(table)
        layout.addWidget(SmartCalibrationChart(statuses, datagrab.get_speed_correction(), self))
        buttons = QHBoxLayout()
        reset = QPushButton("重置學習資料")
        reset.setObjectName("resetCalibrationButton")
        close = QPushButton("關閉")
        reset.clicked.connect(self._reset)
        close.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(reset)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _reset(self):
        answer = QMessageBox.question(self, "確認重置", "確定要清除所有速度層的學習資料？\n目前顯示模式不會改變。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            from vehicle import datagrab
            datagrab.reset_smart_calibration()
            self.accept()
            QMessageBox.information(self.parentWidget(), "已重置", "智慧校正資料已清除。")


class BackgroundTask(QThread):
    """執行單一阻塞工作，所有 UI 更新由 result_ready 回主執行緒。"""
    result_ready = pyqtSignal(object)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self._task = task

    def run(self):
        try:
            self.result_ready.emit({'ok': True, 'value': self._task()})
        except Exception as exc:
            self.result_ready.emit({'ok': False, 'error': exc})


class TurnSignalBar(QWidget):
    """方向燈漸層條 - 使用 QPainter 繪製，避免 CSS 效能問題
    
    這個 Widget 取代了原本使用 setStyleSheet 動態更新的 QWidget，
    使用 QPainter 直接繪製漸層，大幅降低 CPU 負擔。
    """
    
    def __init__(self, direction: str = "left", parent=None):
        """
        Args:
            direction: "left" 或 "right"，決定漸層方向
        """
        super().__init__(parent)
        self.direction = direction
        self.gradient_pos = 0.0  # 0.0 (熄滅) 到 1.0 (全亮)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        # 預先建立顏色，避免每次 paintEvent 都重新建立
        self._color_bright = QColor(177, 255, 0)
        self._color_mid = QColor(140, 255, 0)
        self._color_dim = QColor(120, 255, 0)
        self._color_dark = QColor(30, 30, 30)
    
    def set_gradient_pos(self, pos: float):
        """設定漸層位置並觸發重繪
        Args:
            pos: 0.0 到 1.0
        """
        if self.gradient_pos != pos:
            self.gradient_pos = max(0.0, min(1.0, pos))
            self.update()  # 觸發 paintEvent
    
    def paintEvent(self, event):
        """使用 QPainter 繪製漸層效果"""
        if self.gradient_pos <= 0:
            return  # 完全熄滅，不繪製任何東西
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        pos = self.gradient_pos
        
        # 建立漸層
        if self.direction == "left":
            # 左轉燈：從左邊（亮）到右邊（暗）
            gradient = QLinearGradient(0, 0, w, 0)
        else:
            # 右轉燈：從右邊（亮）到左邊（暗）
            gradient = QLinearGradient(w, 0, 0, 0)
        
        if pos >= 1.0:
            # 完全亮起：整條均勻亮色
            self._color_bright.setAlphaF(0.7)
            gradient.setColorAt(0, self._color_bright)
            gradient.setColorAt(1, self._color_bright)
        else:
            # 熄滅中：從邊緣向中間漸暗
            self._color_bright.setAlphaF(pos * 0.7)
            self._color_mid.setAlphaF(pos * 0.5)
            self._color_dim.setAlphaF(pos * 0.3)
            self._color_dark.setAlphaF(0.1)
            
            gradient.setColorAt(0, self._color_bright)
            gradient.setColorAt(0.3 * pos, self._color_bright)
            gradient.setColorAt(0.5 * pos, self._color_mid)
            gradient.setColorAt(0.7 * pos, self._color_dim)
            gradient.setColorAt(min(0.85 * pos, 0.99), self._color_dim)
            gradient.setColorAt(1, self._color_dark)
        
        # 繪製圓角矩形
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, h, 4, 4)
        
        painter.end()



class ControlPanel(QWidget):
    """下拉控制面板（類似 Android 狀態列）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(1920, 300)
        
        # 設置半透明背景 - 使用 AutoFillBackground
        self.setAutoFillBackground(True)
        
        # WiFi 狀態
        self.wifi_ssid = None
        self.wifi_signal = 0
        self.speed_sync_mode = "calibrated"  # 速度同步初始模式
        
        # 主佈局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)
        
        # 標題列
        title_layout = QHBoxLayout()
        title_label = QLabel("快速設定")
        title_label.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: bold;
            background: transparent;
        """)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        # 關閉按鈕
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
                border-radius: 20px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.3);
            }
        """)
        close_btn.clicked.connect(self.hide_panel)
        title_layout.addWidget(close_btn)
        
        layout.addLayout(title_layout)
        
        # === 內容區域：左側快捷按鈕 + 右側系統狀態 ===
        content_layout = QHBoxLayout()
        content_layout.setSpacing(30)
        
        # === 左側：快捷按鈕 ===
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        
        self.buttons = []
        self.button_widgets = {}  # 用於存取特定按鈕
        # 三段速度模式：校正 / 固定1.05 / OBD+GPS
        self.speed_sync_modes = ["calibrated", "fixed", "gps"]
        self.speed_sync_mode_index = 0
        self.speed_sync_mode = self.speed_sync_modes[self.speed_sync_mode_index]
        button_configs = [
            ("WiFi", "📶", T('BTN_WIFI')),
            ("時間", "🕐", T('BTN_TIME')),
            ("亮度", "☀", T('BTN_BRIGHTNESS')),
            ("更新", "🔄", T('BTN_UPDATE')),
            ("電源", "🔌", T('BTN_POWER')),
            ("設定", "⚙", T('BTN_SETTINGS'))
        ]
        
        for title, icon, color in button_configs:
            btn = self.create_control_button(title, icon, color)
            self.buttons.append(btn)
            self.button_widgets[title] = btn
            button_layout.addWidget(btn)

        # 速度同步（三段模式）
        speed_sync_btn = self.create_speed_sync_button()
        self.buttons.append(speed_sync_btn)
        self.button_widgets["速度同步"] = speed_sync_btn
        button_layout.addWidget(speed_sync_btn)
        
        content_layout.addLayout(button_layout)
        content_layout.addStretch()
        
        # === 右側：系統狀態資訊（水平排列兩個卡片）===
        status_layout = QHBoxLayout()
        status_layout.setSpacing(20)
        
        # WiFi 狀態卡片
        wifi_card = QWidget()
        wifi_card.setFixedSize(280, 80)
        wifi_card.setStyleSheet(f"""
            QWidget {{
                background: rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }}
        """)
        wifi_card_layout = QHBoxLayout(wifi_card)
        wifi_card_layout.setContentsMargins(15, 10, 15, 10)
        wifi_card_layout.setSpacing(12)
        
        # WiFi 圖示
        wifi_icon = QLabel("📶")
        wifi_icon.setFixedSize(40, 40)
        wifi_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wifi_icon.setStyleSheet("font-size: 28px; background: transparent;")
        wifi_card_layout.addWidget(wifi_icon)
        
        # WiFi 資訊
        wifi_info_layout = QVBoxLayout()
        wifi_info_layout.setSpacing(2)
        wifi_info_layout.setContentsMargins(0, 0, 0, 0)
        
        self.wifi_status_label = QLabel("檢查中...")
        self.wifi_status_label.setStyleSheet(f"""
            color: {T('TEXT_PRIMARY')};
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        
        self.wifi_detail_label = QLabel("取得連線資訊")
        self.wifi_detail_label.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 12px;
            background: transparent;
        """)
        
        wifi_info_layout.addWidget(self.wifi_status_label)
        wifi_info_layout.addWidget(self.wifi_detail_label)
        wifi_card_layout.addLayout(wifi_info_layout)
        wifi_card_layout.addStretch()
        
        # WiFi 信號強度指示
        self.wifi_signal_label = QLabel("")
        self.wifi_signal_label.setStyleSheet(f"""
            color: {T('SUCCESS')};
            font-size: 18px;
            font-weight: bold;
            background: transparent;
        """)
        wifi_card_layout.addWidget(self.wifi_signal_label)
        
        status_layout.addWidget(wifi_card)
        
        # 日期時間卡片
        datetime_card = QWidget()
        datetime_card.setFixedSize(220, 80)
        datetime_card.setStyleSheet(f"""
            QWidget {{
                background: rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }}
        """)
        datetime_card_layout = QHBoxLayout(datetime_card)
        datetime_card_layout.setContentsMargins(15, 10, 15, 10)
        datetime_card_layout.setSpacing(12)
        
        # 日曆圖示
        calendar_icon = QLabel("📅")
        calendar_icon.setFixedSize(40, 40)
        calendar_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        calendar_icon.setStyleSheet("font-size: 28px; background: transparent;")
        datetime_card_layout.addWidget(calendar_icon)
        
        # 日期時間資訊
        datetime_info_layout = QVBoxLayout()
        datetime_info_layout.setSpacing(2)
        datetime_info_layout.setContentsMargins(0, 0, 0, 0)
        
        self.date_label = QLabel("")
        self.date_label.setStyleSheet(f"""
            color: {T('TEXT_PRIMARY')};
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        
        self.weekday_label = QLabel("")
        self.weekday_label.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 12px;
            background: transparent;
        """)
        
        datetime_info_layout.addWidget(self.date_label)
        datetime_info_layout.addWidget(self.weekday_label)
        datetime_card_layout.addLayout(datetime_info_layout)
        datetime_card_layout.addStretch()
        
        status_layout.addWidget(datetime_card)
        
        content_layout.addLayout(status_layout)
        
        layout.addLayout(content_layout)
        layout.addStretch()
        
        # 隱藏指示
        hint_label = QLabel("向上滑動以關閉")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 14px;
            background: transparent;
        """)
        layout.addWidget(hint_label)
        
        # 啟動狀態更新定時器
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status_info)
        self.status_timer.start(5000)  # 每5秒更新
        
        # 立即更新一次
        QTimer.singleShot(100, self.update_status_info)
        
    def update_status_info(self):
        """更新狀態資訊"""
        from datetime import datetime
        
        # 更新日期時間
        now = datetime.now()
        self.date_label.setText(now.strftime("%Y年%m月%d日"))
        
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        self.weekday_label.setText(weekday_names[now.weekday()])
        
        # 更新 WiFi 狀態
        self.update_wifi_status()
    
    def update_wifi_status(self):
        """要求既有 NetworkMonitor 立即刷新；本方法不執行 subprocess。"""
        parent = self.parent()
        monitor = getattr(parent, 'network_monitor', None) if parent is not None else None
        if monitor is not None:
            monitor.request_check_now()
        self._update_update_button_state()

    def apply_wifi_status(self, snapshot):
        """套用背景 worker 取得的 SSID/訊號快照。"""
        snapshot = snapshot or {}
        ssid = snapshot.get('ssid')
        signal = int(snapshot.get('signal') or 0)
        self.wifi_ssid = ssid
        self.wifi_signal = signal
        if not ssid:
            self.wifi_status_label.setText("未連線")
            self.wifi_detail_label.setText("點擊 WiFi 按鈕進行連線")
            self.wifi_signal_label.setText("")
            return
        self.wifi_status_label.setText(ssid)
        if signal >= 80:
            signal_text, signal_color = "信號極佳", "#6f6"
        elif signal >= 60:
            signal_text, signal_color = "信號良好", "#6f6"
        elif signal >= 40:
            signal_text, signal_color = "信號普通", "#fa0"
        else:
            signal_text, signal_color = "信號較弱", "#f66"
        self.wifi_detail_label.setText(signal_text)
        self.wifi_signal_label.setText(f"{signal}%" if signal else "")
        self.wifi_signal_label.setStyleSheet(
            f"color: {signal_color}; font-size: 16px; font-weight: bold; background: transparent;"
        )
    
    def _update_update_button_state(self):
        """根據網路狀態更新「更新」按鈕"""
        # 檢查父視窗的網路狀態
        parent = self.parent()
        is_online = True
        if parent and hasattr(parent, 'is_offline'):
            is_online = not parent.is_offline
        
        self.set_update_button_enabled(is_online)
        
    def paintEvent(self, a0):  # type: ignore
        """自定義繪製半透明背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 繪製圓角矩形背景（底部圓角）
        rect = self.rect()
        path = QPainterPath()
        radius = 20
        
        # 從左上開始，順時針繪製
        path.moveTo(0, 0)  # 左上
        path.lineTo(rect.width(), 0)  # 右上
        path.lineTo(rect.width(), rect.height() - radius)  # 右側到圓角
        path.arcTo(rect.width() - radius * 2, rect.height() - radius * 2, 
                   radius * 2, radius * 2, 0, -90)  # 右下圓角
        path.lineTo(radius, rect.height())  # 底部
        path.arcTo(0, rect.height() - radius * 2, 
                   radius * 2, radius * 2, -90, -90)  # 左下圓角
        path.closeSubpath()
        
        # 漸層背景
        gradient = QLinearGradient(0, 0, 0, rect.height())
        gradient.setColorAt(0, QColor(42, 42, 53, 220))
        gradient.setColorAt(1, QColor(26, 26, 37, 230))
        
        painter.fillPath(path, QBrush(gradient))
    
    def create_control_button(self, title, icon, color):
        """創建控制按鈕"""
        container = QWidget()
        container.setFixedSize(150, 150)
        container.setCursor(Qt.CursorShape.PointingHandCursor)
        container.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # 按鈕主體
        btn = QPushButton()
        btn.setFixedSize(120, 120)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                border: none;
                border-radius: 20px;
                font-size: 48px;
                color: white;
            }}
            QPushButton:hover {{
                background-color: {self.adjust_color(color, 1.2)};
            }}
            QPushButton:pressed {{
                background-color: {self.adjust_color(color, 0.8)};
            }}
        """)
        btn.setText(icon)
        btn.clicked.connect(lambda checked=False, t=title: self.on_button_clicked(t, checked))
        # 標籤
        label = QLabel(title)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 16px;
                background: transparent;
            }
        """)
        
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        
        return container

    def create_speed_sync_button(self):
        """創建速度同步開關按鈕（反向控制 gps_speed_mode）"""
        container = QWidget()
        container.setFixedSize(150, 150)
        container.setCursor(Qt.CursorShape.PointingHandCursor)
        container.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        btn = QPushButton()
        btn.setFixedSize(120, 120)
        btn.clicked.connect(lambda checked=False: self.on_button_clicked("速度同步", checked))
        
        # 長按檢測（1.5 秒）
        btn._long_press_timer = QTimer()
        btn._long_press_timer.setSingleShot(True)
        btn._long_press_timer.timeout.connect(lambda: self._on_speed_sync_long_press(btn))
        btn._is_long_press = False
        
        def on_pressed():
            btn._is_long_press = False
            btn._long_press_timer.start(1500)  # 1.5 秒長按
        
        def on_released():
            btn._long_press_timer.stop()
        
        btn.pressed.connect(on_pressed)
        btn.released.connect(on_released)

        label = QLabel("速度同步")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 16px;
                background: transparent;
            }
        """)

        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        # 套用預設狀態樣式
        self._apply_speed_sync_style(btn, self.speed_sync_mode)
        return container
    
    def _on_speed_sync_long_press(self, btn):
        """速度同步按鈕長按：顯示全時智慧校正狀態。"""
        btn._is_long_press = True
        SmartCalibrationDialog(self).exec()
    
    def adjust_color(self, hex_color, factor):
        """調整顏色亮度"""
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))
        return f'#{r:02x}{g:02x}{b:02x}'
    
    def _get_button_by_title(self, title):
        """取得指定標題的 QPushButton 物件"""
        if title not in self.button_widgets:
            return None
        container = self.button_widgets[title]
        for child in container.findChildren(QPushButton):
            return child
        return None

    def _apply_speed_sync_style(self, btn: QPushButton, mode: str):
        """套用速度同步按鈕的樣式與文字"""
        label_map = {
            "calibrated": "OBD\n(校正)",
            "fixed": "OBD\n(同步)",
            "gps": "OBD\n(GPS)",
        }
        color_map = {
            "calibrated": "#4CAF50",
            "fixed": "#FF9800",
            "gps": "#2196F3",
        }
        text = label_map.get(mode, mode)
        color = color_map.get(mode, "#555555")
        btn.setText(text)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                border: none;
                border-radius: 20px;
                font-size: 28px;
                color: white;
            }}
            QPushButton:hover {{
                background-color: {self.adjust_color(color, 1.15)};
            }}
            QPushButton:pressed {{
                background-color: {self.adjust_color(color, 0.85)};
            }}
        """)

    def set_speed_sync_state(self, mode: str):
        """更新速度同步按鈕狀態（UI）"""
        self.speed_sync_mode = mode
        btn = self._get_button_by_title("速度同步")
        if btn:
            btn.blockSignals(True)
            self._apply_speed_sync_style(btn, mode)
            btn.blockSignals(False)

    def on_button_clicked(self, title, checked=False):
        """按鈕點擊處理"""
        print(f"控制面板按鈕被點擊: {title}")
        # 這裡可以添加具體功能
        if title == "WiFi":
            # 可以觸發 WiFi 管理器
            parent = self.parent()
            if parent and hasattr(parent, 'show_wifi_manager'):
                parent.show_wifi_manager()  # type: ignore
        elif title == "時間":
            self.do_time_sync()
        elif title == "亮度":
            self.cycle_brightness()
        elif title == "更新":
            self.do_auto_update()
        elif title == "電源":
            self.show_power_menu()
        elif title == "設定":
            self.hide_panel()
            self.show_settings_menu()
        elif title == "速度同步":
            # 檢查是否為長按（長按已處理，不要觸發普通點擊）
            btn = self._get_button_by_title("速度同步")
            if btn and hasattr(btn, '_is_long_press') and btn._is_long_press:
                btn._is_long_press = False
                return  # 長按已處理，跳過
            
            parent = self.parent()
            if parent and hasattr(parent, 'cycle_speed_sync_mode'):
                parent.cycle_speed_sync_mode()  # type: ignore
            else:
                # 後備：僅更新當前模式的 UI 樣式
                self.set_speed_sync_state(getattr(self, "speed_sync_mode", "calibrated"))
    
    def do_time_sync(self):
        """執行 NTP 時間校正"""
        from PyQt6.QtWidgets import QMessageBox
        
        # 檢查網路狀態
        main_window = self.parent()
        if main_window and hasattr(main_window, 'is_offline') and main_window.is_offline:
            msg = QMessageBox()
            msg.setWindowTitle("無法校正時間")
            msg.setText("網路未連線，無法執行 NTP 時間校正。\n請先連接網路後再試。")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            msg.exec()
            return

        worker = getattr(self, '_time_sync_worker', None)
        if worker is not None and worker.isRunning():
            return
        self._update_time_button_syncing(True)
        self._time_sync_worker = BackgroundTask(self._perform_time_sync_task, self)
        self._time_sync_worker.result_ready.connect(self._on_time_sync_finished)
        self._time_sync_worker.start()
    
    def _update_time_button_syncing(self, syncing):
        """更新時間按鈕的同步狀態"""
        if "時間" not in self.button_widgets:
            return
        
        btn_container = self.button_widgets["時間"]
        for child in btn_container.findChildren(QPushButton):
            if syncing:
                child.setText("⏳")
                child.setEnabled(False)
                child.setStyleSheet("""
                    QPushButton {
                        background-color: #666;
                        border: none;
                        border-radius: 20px;
                        font-size: 48px;
                        color: white;
                    }
                """)
            else:
                child.setText("🕐")
                child.setEnabled(True)
                child.setStyleSheet("""
                    QPushButton {
                        background-color: #4285F4;
                        border: none;
                        border-radius: 20px;
                        font-size: 48px;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #5a9cf4;
                    }
                    QPushButton:pressed {
                        background-color: #3367d6;
                    }
                """)

    @staticmethod
    def _perform_time_sync_task():
        import subprocess
        if os.path.exists('/usr/bin/timedatectl'):
            subprocess.run(['sudo', 'timedatectl', 'set-ntp', 'true'], capture_output=True, timeout=5)
            subprocess.run(['sudo', 'systemctl', 'restart', 'systemd-timesyncd'], capture_output=True, timeout=10)
            time.sleep(2)
            result = subprocess.run(
                ['timedatectl', 'show', '--property=NTPSynchronized'],
                capture_output=True, text=True, timeout=5,
            )
            success = True
            text = "NTP 同步成功" if 'NTPSynchronized=yes' in result.stdout else "已嘗試 NTP 同步"
        elif os.path.exists('/usr/sbin/ntpdate'):
            result = subprocess.run(
                ['sudo', 'ntpdate', '-u', 'pool.ntp.org'],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                result = subprocess.run(
                    ['sudo', 'ntpdate', '-u', 'time.google.com'],
                    capture_output=True, text=True, timeout=15,
                )
            success = result.returncode == 0
            text = "NTP 同步成功" if success else "同步失敗"
        else:
            success, text = False, "未找到 NTP 工具"
        if success and os.path.exists('/dev/rtc0'):
            subprocess.run(['sudo', 'hwclock', '-w'], capture_output=True, timeout=5)
            text += "\n已同步到 RTC"
        return {'success': success, 'message': text}

    def _on_time_sync_finished(self, result):
        from datetime import datetime
        self._update_time_button_syncing(False)
        msg = QMessageBox(self)
        msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        if result.get('ok'):
            payload = result['value']
            msg.setWindowTitle("時間校正完成" if payload['success'] else "時間校正失敗")
            msg.setIcon(QMessageBox.Icon.Information if payload['success'] else QMessageBox.Icon.Warning)
            msg.setText(f"{payload['message']}\n\n目前時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            msg.setWindowTitle("時間校正錯誤")
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setText(f"發生錯誤：{result['error']}")
        msg.exec()
        self.update_status_info()

    def cycle_brightness(self):
        """循環切換亮度"""
        parent = self.parent()
        if parent and hasattr(parent, 'cycle_brightness'):
            level = parent.cycle_brightness()
            # 更新按鈕顯示
            self._update_brightness_button(level)
    
    def _update_brightness_button(self, level):
        """更新亮度按鈕的顯示"""
        if "亮度" not in self.button_widgets:
            return
        
        btn_container = self.button_widgets["亮度"]
        for child in btn_container.findChildren(QPushButton):
            # 根據亮度等級更新圖示
            if level == 0:
                child.setText("☀")  # 全亮
                color = "#FF9800"
            elif level == 1:
                child.setText("🔅")  # 75%
                color = "#FFA726"
            else:
                child.setText("🔆")  # 50%
                color = "#FFB74D"
            
            child.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: none;
                    border-radius: 20px;
                    font-size: 48px;
                    color: white;
                }}
                QPushButton:hover {{
                    background-color: {self.adjust_color(color, 1.2)};
                }}
                QPushButton:pressed {{
                    background-color: {self.adjust_color(color, 0.8)};
                }}
            """)
    
    def set_update_button_enabled(self, enabled):
        """設定更新按鈕的啟用狀態"""
        if "更新" in self.button_widgets:
            btn_container = self.button_widgets["更新"]
            # 找到容器內的 QPushButton
            for child in btn_container.findChildren(QPushButton):
                child.setEnabled(enabled)
                if enabled:
                    child.setStyleSheet("""
                        QPushButton {
                            background-color: #00BCD4;
                            border: none;
                            border-radius: 20px;
                            font-size: 48px;
                            color: white;
                        }
                        QPushButton:hover {
                            background-color: #26C6DA;
                        }
                        QPushButton:pressed {
                            background-color: #0097A7;
                        }
                    """)
                else:
                    child.setStyleSheet("""
                        QPushButton {
                            background-color: #444;
                            border: none;
                            border-radius: 20px;
                            font-size: 48px;
                            color: #888;
                        }
                    """)
    
    def do_auto_update(self):
        """執行自動更新"""
        from PyQt6.QtWidgets import QMessageBox, QApplication, QComboBox, QDialog, QVBoxLayout, QLabel
        import subprocess
        import sys
        
        # 檢查網路狀態
        main_window = self.parent()
        if main_window and hasattr(main_window, 'is_offline') and main_window.is_offline:
            msg = QMessageBox()
            msg.setWindowTitle("無法更新")
            msg.setText("網路未連線，無法執行自動更新。\n請先連接網路後再試。")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            msg.exec()
            return
        
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            
            # 取得目前分支
            current_branch_result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=script_dir,
                capture_output=True,
                text=True
            )
            current_branch = current_branch_result.stdout.strip()
            
            # 取得所有遠端分支
            remote_branches_result = subprocess.run(
                ['git', 'branch', '-r'],
                cwd=script_dir,
                capture_output=True,
                text=True
            )
            remote_branches = []
            for line in remote_branches_result.stdout.strip().split('\n'):
                line = line.strip()
                if line and not line.startswith('HEAD'):
                    branch = line.replace('origin/', '')
                    remote_branches.append(branch)
            
            if not remote_branches:
                msg = QMessageBox()
                msg.setWindowTitle("無法更新")
                msg.setText("找不到遠端分支，請確認已設定 Git 遠端。")
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
                msg.exec()
                return
            
            # 選擇分支對話框
            dialog = QDialog()
            dialog.setWindowTitle("選擇分支")
            dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            layout = QVBoxLayout(dialog)
            
            label = QLabel("請選擇要更新的分支：")
            layout.addWidget(label)
            
            combo = QComboBox()
            combo.addItems(remote_branches)
            if current_branch in remote_branches:
                combo.setCurrentText(current_branch)
            layout.addWidget(combo)
            
            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(button_box)
            
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            
            selected_branch = combo.currentText()
            
        except Exception as e:
            err_box = QMessageBox()
            err_box.setWindowTitle("取得分支失敗")
            err_box.setText(f"無法取得分支列表：\n{str(e)}")
            err_box.setIcon(QMessageBox.Icon.Critical)
            err_box.setWindowFlags(err_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            err_box.exec()
            return
        
        # 選擇操作對話框
        dialog = QDialog()
        dialog.setWindowTitle("分支操作")
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        layout = QVBoxLayout(dialog)
        
        label = QLabel(f"「{selected_branch}」分支：")
        layout.addWidget(label)
        
        update_btn = QPushButton("更新（Pull + 重啟）")
        update_btn.setToolTip("執行 git pull 並重新啟動")
        switch_btn = QPushButton("切換分支（僅 Checkout）")
        switch_btn.setToolTip("僅切換分支，不更新代碼")
        cancel_btn = QPushButton("取消")
        
        layout.addWidget(update_btn)
        layout.addWidget(switch_btn)
        layout.addWidget(cancel_btn)
        
        def do_update():
            dialog.done(1)
        def do_switch():
            dialog.done(2)
        def do_cancel():
            dialog.done(0)
        
        update_btn.clicked.connect(do_update)
        switch_btn.clicked.connect(do_switch)
        cancel_btn.clicked.connect(do_cancel)
        
        result = dialog.exec()
        
        if result == 0:
            return
        
        do_pull = (result == 1)

        worker = getattr(self, '_git_update_worker', None)
        if worker is not None and worker.isRunning():
            return
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._git_update_context = (repo_dir, do_pull)
        self._git_update_worker = BackgroundTask(
            lambda: self._perform_git_task(repo_dir, selected_branch, do_pull),
            self,
        )
        self._git_update_worker.result_ready.connect(self._on_git_task_finished)
        self._git_update_worker.start()
    
    @staticmethod
    def _perform_git_task(repo_dir, selected_branch, do_pull):
        import subprocess
        command = (
            ['git', 'pull', 'origin', selected_branch]
            if do_pull else
            ['git', 'checkout', selected_branch]
        )
        result = subprocess.run(
            command, cwd=repo_dir, capture_output=True, text=True, timeout=30,
        )
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'action': "更新" if do_pull else "分支切換",
        }

    def _on_git_task_finished(self, result):
        repo_dir, _ = self._git_update_context
        if not result.get('ok'):
            QMessageBox.critical(self, "更新錯誤", f"更新過程發生錯誤：\n{result['error']}")
            return
        payload = result['value']
        if not payload['success']:
            QMessageBox.critical(
                self,
                f"{payload['action']}失敗",
                payload['stderr'] or payload['stdout'] or "未知錯誤",
            )
            return
        QMessageBox.information(
            self,
            f"{payload['action']}完成",
            f"已成功{payload['action']}！\n\n程式將在 2 秒後重新啟動。",
        )
        QTimer.singleShot(2000, lambda: self._restart_application(repo_dir))

    def on_accent_color_changed(self, color_hex: str):
        """當強調色改變時通知 ControlPanel；實際 UI 刷新由集中主題邏輯處理。"""
        # 保留此 slot 以維持既有 signal/slot 相容性。
        # 不在這裡遞迴重設所有 widget 的 stylesheet，避免：
        # 1. 重新設回相同字串卻未重新計算主題色；
        # 2. 與上層 Dashboard/主題管理器的刷新邏輯重複；
        # 3. 造成不必要的重繪與 processEvents() 開銷。
        print(f"[ControlPanel] 強調色已更改為 {color_hex}，由主題管理流程統一刷新 UI")
    
    def show_settings_menu(self):
        """顯示設定選單"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QApplication, QMainWindow
        
        # 取得實際顯示的視窗大小
        parent_width = 1920
        parent_height = 480
        
        widget = self
        while widget:
            parent = widget.parent()
            if parent is None:
                break
            if isinstance(parent, QMainWindow):
                parent_width = parent.width()
                parent_height = parent.height()
                break
            widget = parent
        
        scale = min(parent_width / 1920, parent_height / 480)
        
        dialog_width = int(1600 * scale)
        dialog_height = int(260 * scale)
        btn_width = int(220 * scale)
        btn_height = int(80 * scale)
        title_font_size = max(12, int(28 * scale))
        btn_font_size = max(10, int(18 * scale))
        btn_radius = max(5, int(15 * scale))
        margin = max(10, int(40 * scale))
        spacing = max(10, int(20 * scale))
        
        app = QApplication.instance()
        dialog_parent = app.activeWindow() if app and app.activeWindow() else (self.window() if self.window() else self)
        dialog = QDialog(dialog_parent)
        dialog.setWindowTitle("設定")
        dialog.setFixedSize(dialog_width, dialog_height)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setModal(True)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {T('BG_CARD')};
            }}
            QLabel {{
                color: {T('TEXT_PRIMARY')};
                font-size: 18px;
                background: transparent;
            }}
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(margin, int(30 * scale), margin, int(30 * scale))
        layout.setSpacing(spacing)
        
        # 標題
        title = QLabel("⚙ 設定選項")
        title.setStyleSheet(f"font-size: {title_font_size}px; font-weight: bold; color: {T('TEXT_PRIMARY')};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        layout.addSpacing(int(10 * scale))
        
        # 設定選項按鈕
        def create_settings_btn(text, icon, description, callback):
            btn = QPushButton(f"{icon} {text}")
            btn.setFixedSize(btn_width, btn_height)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {T('BG_CARD_ALT')};
                    color: {T('TEXT_PRIMARY')};
                    border: none;
                    border-radius: {btn_radius}px;
                    font-size: {btn_font_size}px;
                    font-weight: bold;
                    padding: {int(10 * scale)}px;
                }}
                QPushButton:hover {{
                    background-color: {T('BORDER_HOVER')};
                }}
            """)
            btn.clicked.connect(callback)
            return btn
        
        # MQTT 設定
        def open_mqtt():
            dialog.accept()
            parent = self.parent()
            if parent and hasattr(parent, 'show_mqtt_settings'):
                parent.show_mqtt_settings()
        
        # Spotify 設定
        def open_spotify():
            dialog.accept()
            parent = self.parent()
            if parent and hasattr(parent, 'show_spotify_settings'):
                parent.show_spotify_settings()

        # Telegram 設定
        def open_telegram():
            dialog.accept()
            parent = self.parent()
            if parent and hasattr(parent, 'show_telegram_settings'):
                parent.show_telegram_settings()

        # 亮度設定
        def open_brightness():
            brightness_parent = dialog_parent
            dashboard_parent = self.parent()

            def _show_brightness_dialog():
                if dashboard_parent and hasattr(dashboard_parent, 'show_brightness_settings'):
                    dashboard_parent.show_brightness_settings(parent=brightness_parent)

            dialog.accept()
            QTimer.singleShot(0, _show_brightness_dialog)
        
        # 主題設定
        def open_theme():
            from ui.accent_color_settings import show_accent_color_popup
            # 使用穩定父視窗（show_settings_menu 一開始解析出的頂層視窗）
            # 並延後到設定選單關閉後再開啟，避免 parent 被銷毀導致彈窗消失
            theme_parent = dialog_parent

            def _show_theme_dialog():
                show_accent_color_popup(parent=theme_parent, on_changed=self.on_accent_color_changed)

            dialog.accept()
            QTimer.singleShot(0, _show_theme_dialog)

        # Toast 通知測試
        def test_toast():
            parent = self.parent()

            def _show_test_toast():
                if parent and hasattr(parent, 'show_toast'):
                    if hasattr(parent, 'hide_control_panel'):
                        parent.hide_control_panel()
                    parent.show_toast("這是一則通知測試", "info", 3000)

            dialog.accept()
            QTimer.singleShot(120, _show_test_toast)
        
        options_layout = QHBoxLayout()
        options_layout.setSpacing(int(20 * scale))
        options_layout.addStretch()
        options_layout.addWidget(create_settings_btn("MQTT 設定", "📡", "設定 MQTT 伺服器連線", open_mqtt))
        options_layout.addWidget(create_settings_btn("Spotify 設定", "🎵", "設定 Spotify 音樂播放", open_spotify))
        options_layout.addWidget(create_settings_btn("Telegram 設定", "✈", "設定 Telegram 通知", open_telegram))
        options_layout.addWidget(create_settings_btn("亮度設定", "☀", "設定預設與夜間亮度", open_brightness))
        options_layout.addWidget(create_settings_btn("主題強調色設定", "🎨", "自訂 UI 強調色", open_theme))
        options_layout.addWidget(create_settings_btn("通知測試", "🔔", "測試右上角 toast 通知", test_toast))
        options_layout.addStretch()
        layout.addLayout(options_layout)

        layout.addStretch()
        
        # 取消按鈕
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(int(180 * scale), int(44 * scale))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {T('TEXT_SECONDARY')};
                border: 2px solid {T('BORDER_DEFAULT')};
                border-radius: {btn_radius}px;
                font-size: {int(btn_font_size * 0.8)}px;
            }}
            QPushButton:hover {{
                border-color: {T('TEXT_SECONDARY')};
            }}
        """)
        cancel_btn.clicked.connect(dialog.reject)
        cancel_wrap = QHBoxLayout()
        cancel_wrap.addStretch()
        cancel_wrap.addWidget(cancel_btn)
        cancel_wrap.addStretch()
        layout.addLayout(cancel_wrap)
        
        # 顯示並置中（以可見頂層視窗為準，並限制在螢幕可見範圍）
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
    
    def show_power_menu(self):
        """顯示電源選單"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QApplication, QMainWindow
        import platform
        
        is_linux = platform.system() == 'Linux'
        
        # 取得實際顯示的視窗大小
        # 在開發環境中，Dashboard 被包在 ScalableWindow (QMainWindow) 裡面
        # Dashboard 本身永遠是 1920x480，但 ScalableWindow 是縮放過的
        parent_width = 1920
        parent_height = 480
        
        # 嘗試找到 ScalableWindow（QMainWindow 類型的父視窗）
        widget = self
        while widget:
            parent = widget.parent()
            if parent is None:
                break
            # 檢查是否是 QMainWindow（ScalableWindow）
            if isinstance(parent, QMainWindow):
                parent_width = parent.width()
                parent_height = parent.height()
                print(f"[電源選單] 找到 ScalableWindow: {parent_width}x{parent_height}")
                break
            widget = parent
        
        # 如果找不到 ScalableWindow，檢查是否在全螢幕模式
        if parent_width == 1920 and parent_height == 480:
            # 可能是全螢幕模式或直接顯示 Dashboard
            screen = QApplication.primaryScreen()
            if screen:
                geometry = screen.availableGeometry()
                # 如果螢幕小於 1920x480，使用螢幕大小
                if geometry.width() < 1920 or geometry.height() < 480:
                    parent_width = geometry.width()
                    parent_height = min(geometry.height(), int(geometry.width() / 4))
                    print(f"[電源選單] 使用螢幕大小: {parent_width}x{parent_height}")
        
        print(f"[電源選單] 最終視窗大小: {parent_width}x{parent_height}")
        
        # 計算縮放比例（以 1920x480 為基準）
        scale = min(parent_width / 1920, parent_height / 480)
        print(f"[電源選單] 縮放比例: {scale}")
        
        dialog_width = int(1920 * scale)
        dialog_height = int(480 * scale)
        btn_width = int(280 * scale)
        btn_height = int(200 * scale)
        title_font_size = max(12, int(36 * scale))
        btn_font_size = max(10, int(28 * scale))
        btn_radius = max(5, int(20 * scale))
        margin = max(10, int(60 * scale))
        spacing = max(10, int(40 * scale))
        
        # 創建電源選單對話框
        dialog = QDialog()
        dialog.setWindowTitle("電源選項")
        dialog.setFixedSize(dialog_width, dialog_height)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {T('BG_CARD')};
            }}
            QLabel {{
                color: {T('TEXT_PRIMARY')};
                font-size: 18px;
                background: transparent;
            }}
            QPushButton {{
                background-color: {T('BG_CARD_ALT')};
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: {btn_radius}px;
                font-size: {int(24 * scale)}px;
                font-weight: bold;
                padding: {int(20 * scale)}px;
            }}
            QPushButton:hover {{
                background-color: {T('BORDER_HOVER')};
            }}
            QPushButton:pressed {{
                background-color: {T('BORDER_ACTIVE')};
            }}
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(margin, int(40 * scale), margin, int(40 * scale))
        layout.setSpacing(int(30 * scale))
        
        # 標題
        title = QLabel("🔌 電源選項")
        title.setStyleSheet(f"font-size: {title_font_size}px; font-weight: bold; color: white;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        layout.addStretch()
        
        # 水平按鈕佈局
        button_layout = QHBoxLayout()
        button_layout.setSpacing(spacing)
        
        # 程式重啟按鈕
        btn_app_restart = QPushButton("🔄\n程式重啟")
        btn_app_restart.setFixedSize(btn_width, btn_height)
        btn_app_restart.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_app_restart.setStyleSheet(f"""
            QPushButton {{
                background-color: {T('BTN_UPDATE')};
                font-size: {btn_font_size}px;
                border-radius: {btn_radius}px;
            }}
            QPushButton:hover {{
                background-color: #26C6DA;
            }}
        """)
        btn_app_restart.clicked.connect(lambda: self._power_action('app_restart', dialog))
        button_layout.addWidget(btn_app_restart)
        
        # 系統重啟按鈕
        btn_sys_reboot = QPushButton("🔃\n系統重啟")
        btn_sys_reboot.setFixedSize(btn_width, btn_height)
        btn_sys_reboot.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sys_reboot.setStyleSheet(f"""
            QPushButton {{
                background-color: #FF9800;
                font-size: {btn_font_size}px;
                border-radius: {btn_radius}px;
            }}
            QPushButton:hover {{
                background-color: #FFB74D;
            }}
        """)
        btn_sys_reboot.clicked.connect(lambda: self._power_action('reboot', dialog))
        button_layout.addWidget(btn_sys_reboot)
        
        # 關機按鈕
        btn_shutdown = QPushButton("🔌\n關機")
        btn_shutdown.setFixedSize(btn_width, btn_height)
        btn_shutdown.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_shutdown.setStyleSheet(f"""
            QPushButton {{
                background-color: #E91E63;
                font-size: {btn_font_size}px;
                border-radius: {btn_radius}px;
            }}
            QPushButton:hover {{
                background-color: #F06292;
            }}
        """)
        btn_shutdown.clicked.connect(lambda: self._power_action('shutdown', dialog))
        button_layout.addWidget(btn_shutdown)
        
        # 取消按鈕
        btn_cancel = QPushButton("✕\n取消")
        btn_cancel.setFixedSize(btn_width, btn_height)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: #424242;
                font-size: {btn_font_size}px;
                border-radius: {btn_radius}px;
            }}
            QPushButton:hover {{
                background-color: #616161;
            }}
        """)
        btn_cancel.clicked.connect(dialog.reject)
        button_layout.addWidget(btn_cancel)
        
        layout.addLayout(button_layout)
        
        layout.addStretch()
        
        dialog.exec()
    
    def _prepare_dashboard_exit(self):
        """讓 Dashboard 在任何手動退出前同步保存並停止背景資源。"""
        parent = self.parent()
        if parent is not None and hasattr(parent, 'prepare_for_exit'):
            parent.prepare_for_exit()

    def _execute_system_power_action(self, command):
        """保存資料後才交給系統 reboot/shutdown。"""
        import subprocess
        self._prepare_dashboard_exit()
        subprocess.run(command, check=False)

    def _power_action(self, action, dialog):
        """執行電源操作"""
        from PyQt6.QtWidgets import QMessageBox, QApplication
        import subprocess
        import os
        import platform
        
        is_linux = platform.system() == 'Linux'
        dialog.close()
        
        action_names = {
            'app_restart': '程式重啟',
            'reboot': '系統重啟',
            'shutdown': '關機'
        }
        
        # 確認對話框
        msg = QMessageBox()
        msg.setWindowTitle("確認操作")
        
        if action == 'app_restart':
            # 特殊處理：提供重啟和關閉兩個選項
            msg.setText("請選擇操作：")
            msg.setInformativeText(
                "⚠️ 注意：在 Raspberry Pi 上，若關閉程式後\n"
                "需透過 SSH 才能重新啟動儀表板。\n\n"
                "建議使用「重啟程式」以確保可繼續操作。"
            )
            msg.setIcon(QMessageBox.Icon.Question)
            
            # 自訂按鈕
            btn_restart = msg.addButton("🔄 重啟程式", QMessageBox.ButtonRole.AcceptRole)
            btn_close = msg.addButton("⏹️ 關閉程式", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            
            msg.setDefaultButton(btn_restart)
            msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            msg.exec()
            
            clicked = msg.clickedButton()
            if clicked == btn_restart:
                # 執行重啟
                try:
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    print("[電源] 準備程式重啟...")
                    self._show_power_countdown("程式重啟", 1)
                    QTimer.singleShot(1000, lambda: self._restart_application(script_dir))
                except Exception as e:
                    self._show_power_error(e)
            elif clicked == btn_close:
                # 執行關閉程式
                print("[電源] 關閉程式...")
                # 建立標記檔案，防止自動重啟
                try:
                    with open('/tmp/.dashboard_manual_exit', 'w') as f:
                        f.write('manual_exit')
                except:
                    pass
                self._show_power_countdown("關閉程式", 1)
                def force_exit():
                    print("[電源] 正在安全退出應用程式...")
                    self._prepare_dashboard_exit()
                    QApplication.quit()
                QTimer.singleShot(1000, force_exit)
            # 取消則不做任何事
            return
            
        elif action == 'reboot':
            if is_linux:
                msg.setText("是否要重新啟動系統？\n\n系統將會完全重啟。")
            else:
                msg.setText("是否要模擬系統重啟？\n\n（macOS 上僅模擬，不會真的重啟）")
        elif action == 'shutdown':
            if is_linux:
                msg.setText("是否要關閉系統？\n\n系統將會關機。")
            else:
                msg.setText("是否要模擬關機？\n\n（macOS 上僅模擬，不會真的關機）")
        
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return
        
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            
            # app_restart 已在上面處理，這裡只處理 reboot 和 shutdown
            if action == 'reboot':
                if is_linux:
                    print("[電源] 準備系統重啟...")
                    self._show_power_countdown("系統重啟", 3)
                    QTimer.singleShot(3000, lambda: self._execute_system_power_action(['sudo', 'reboot']))
                else:
                    # macOS 模擬
                    info_box = QMessageBox()
                    info_box.setWindowTitle("模擬系統重啟")
                    info_box.setText("🔃 模擬系統重啟中...\n\n（macOS 上僅顯示此訊息）")
                    info_box.setIcon(QMessageBox.Icon.Information)
                    info_box.setWindowFlags(info_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
                    info_box.exec()
                    
            elif action == 'shutdown':
                if is_linux:
                    print("[電源] 準備關機...")
                    self._show_power_countdown("關機", 3)
                    QTimer.singleShot(3000, lambda: self._execute_system_power_action(['sudo', 'shutdown', '-h', 'now']))
                else:
                    # macOS 模擬
                    info_box = QMessageBox()
                    info_box.setWindowTitle("模擬關機")
                    info_box.setText("🔌 模擬關機中...\n\n（macOS 上僅顯示此訊息）")
                    info_box.setIcon(QMessageBox.Icon.Information)
                    info_box.setWindowFlags(info_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
                    info_box.exec()
                    
        except Exception as e:
            err_box = QMessageBox()
            err_box.setWindowTitle("錯誤")
            err_box.setText(f"操作失敗:\n{str(e)}")
            err_box.setIcon(QMessageBox.Icon.Critical)
            err_box.setWindowFlags(err_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            err_box.exec()
    
    def _show_power_error(self, error):
        """顯示電源操作錯誤"""
        from PyQt6.QtWidgets import QMessageBox
        err_box = QMessageBox()
        err_box.setWindowTitle("錯誤")
        err_box.setText(f"操作失敗:\n{str(error)}")
        err_box.setIcon(QMessageBox.Icon.Critical)
        err_box.setWindowFlags(err_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        err_box.exec()
    
    def _show_power_countdown(self, action_name, seconds):
        """顯示電源操作倒數提示"""
        from PyQt6.QtWidgets import QMessageBox, QApplication
        
        info_box = QMessageBox()
        info_box.setWindowTitle(action_name)
        info_box.setText(f"⏳ {action_name}將在 {seconds} 秒後執行...")
        info_box.setIcon(QMessageBox.Icon.Information)
        info_box.setWindowFlags(info_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        info_box.setStandardButtons(QMessageBox.StandardButton.NoButton)
        info_box.show()
        QApplication.processEvents()
    
    def _restart_application(self, script_dir):
        """重新啟動應用程式
        
        重啟策略：
        1. 如果是從 datagrab.py 或 demo_mode.py 啟動的，重啟原始入口腳本
        2. 如果 DASHBOARD_ENTRY 環境變數有設定，使用它來判斷入口點
        3. 否則直接重啟當前入口腳本
        """
        import subprocess
        import sys
        import os

        self._prepare_dashboard_exit()
        
        python_exe = sys.executable
        env = os.environ.copy()
        
        project_root = os.path.dirname(script_dir)
        
        # 檢查入口點
        # 方法 1: 檢查 sys.argv[0] (啟動腳本)
        entry_script = os.path.basename(sys.argv[0]) if sys.argv else ''
        
        # 方法 2: 檢查環境變數 (由啟動腳本設定)
        main_entry = os.environ.get('DASHBOARD_ENTRY', '')
        
        print(f"[重啟] 偵測入口點: argv[0]={entry_script}, DASHBOARD_ENTRY={main_entry}")
        
        restart_script = None
        restart_args = []
        restart_cwd = project_root
        
        if entry_script == 'main.py':
            restart_script = os.path.join(project_root, 'main.py')
            restart_args = []
            print(f"[重啟] 使用 main.py 模式: {restart_script}")
        elif 'datagrab' in entry_script or (main_entry == 'datagrab' and entry_script != 'main.py'):
            for candidate in ['datagrab.py', 'vehicle/datagrab.py']:
                candidate_path = os.path.join(project_root, candidate)
                if os.path.exists(candidate_path):
                    restart_script = candidate_path
                    break
            restart_args = ['-m', 'vehicle.datagrab']
            print(f"[重啟] 使用 CAN Bus 模式: {restart_script}")
        elif 'demo_mode' in entry_script or main_entry == 'demo':
            for candidate in ['demo_mode.py', 'vehicle/demo_mode.py']:
                candidate_path = os.path.join(project_root, candidate)
                if os.path.exists(candidate_path):
                    restart_script = candidate_path
                    restart_args = ['--spotify']
                    break
            if not restart_script:
                restart_args = ['-m', 'vehicle.demo_mode', '--spotify']
            print(f"[重啟] 使用演示模式: {restart_script}")
        else:
            # 無法判斷入口點，嘗試使用 sys.argv[0] 的完整路徑
            if sys.argv and os.path.exists(sys.argv[0]):
                restart_script = os.path.abspath(sys.argv[0])
                restart_args = []
                restart_cwd = os.path.dirname(restart_script)
                print(f"[重啟] 使用原始啟動腳本: {restart_script}")
            else:
                # 最後手段：直接啟動 main.py
                restart_script = os.path.join(project_root, 'main.py')
                restart_args = []
                print(f"[重啟] 找不到入口點，使用 main.py: {restart_script}")
        
        use_module = False
        if restart_script and os.path.exists(restart_script):
            if restart_args and restart_args[0] == '-m':
                use_module = True
                module_name = restart_args[1]
                cmd = [python_exe, '-m', module_name] + restart_args[2:]
                print(f"[重啟] 正在啟動 module {module_name}...")
            else:
                cmd = [python_exe, restart_script] + restart_args
                print(f"[重啟] 正在啟動 {restart_script} {restart_args}...")
            
            subprocess.Popen(
                cmd,
                cwd=restart_cwd,
                env=env,
                start_new_session=True,
                stdin=subprocess.DEVNULL
            )
        else:
            print(f"[重啟] 錯誤: 找不到重啟腳本 {restart_script}")
        
        # 關閉當前應用
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()
    
    def hide_panel(self):
        """隱藏面板"""
        parent = self.parent()
        if parent and hasattr(parent, 'hide_control_panel'):
            parent.hide_control_panel()  # type: ignore
