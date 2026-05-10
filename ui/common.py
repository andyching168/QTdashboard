from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF, QRect, QEvent
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont, QPixmap
import weakref
import time

from ui.theme import T


class GaugeStyle:
    def __init__(self, major_ticks=8, minor_ticks=4, start_angle=225, span_angle=270, 
                 label_color=Qt.GlobalColor.white, tick_color=QColor(100, 150, 255),
                 needle_color=QColor(100, 150, 255), text_scale=1.0, show_center_circle=True):
        self.major_ticks = major_ticks
        self.minor_ticks = minor_ticks
        self.start_angle = start_angle
        self.span_angle = span_angle
        self.label_color = label_color
        self.tick_color = tick_color
        self.needle_color = needle_color
        self.text_scale = text_scale
        self.show_center_circle = show_center_circle


class RadarOverlay(QWidget):
    """雷達波紋覆蓋層"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")
        
        self.levels = {
            "LF": 0, "RF": 0,
            "LR": 0, "RR": 0
        }
        
    def set_levels(self, lf, rf, lr, rr):
        self.levels["LF"] = lf
        self.levels["RF"] = rf
        self.levels["LR"] = lr
        self.levels["RR"] = rr
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w, h = self.width(), self.height()
        
        padding_x = 20
        padding_y = 20
        margin_x = 80 
        margin_y = -10
        
        self._draw_radar_waves(painter, 
                             center_x=padding_x + margin_x + 40, 
                             center_y=padding_y + margin_y + 40, 
                             start_angle=120, span_angle=60, 
                             level=self.levels["LF"])
                              
        self._draw_radar_waves(painter, 
                             center_x=w - padding_x - margin_x - 40, 
                             center_y=padding_y + margin_y + 40, 
                             start_angle=0, span_angle=60, 
                             level=self.levels["RF"])
                              
        self._draw_radar_waves(painter, 
                             center_x=padding_x + margin_x + 40, 
                             center_y=h - padding_y - margin_y - 40, 
                             start_angle=180, span_angle=60, 
                             level=self.levels["LR"])
                              
        self._draw_radar_waves(painter, 
                             center_x=w - padding_x - margin_x - 40, 
                             center_y=h - padding_y - margin_y - 40, 
                             start_angle=300, span_angle=60, 
                             level=self.levels["RR"])

    def _draw_radar_waves(self, painter, center_x, center_y, start_angle, span_angle, level):
        if level == 0:
            return
            
        color = QColor("#FFD700") if level == 1 else QColor("#FF4444")
        
        pen = QPen(color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        wave_count = 3
        base_radius = 20
        gap = 12
        
        for i in range(wave_count):
            radius = base_radius + i * gap
            rect = QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)
            
            alpha = 255 - (i * 60)
            color.setAlpha(alpha)
            pen.setColor(color)
            painter.setPen(pen)
            
            painter.drawArc(rect, int(start_angle * 16), int(span_angle * 16))


class ClickableLabel(QLabel):
    """可點擊的 QLabel，發出 clicked 信號"""
    clicked = pyqtSignal()
    
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MarqueeLabel(QLabel):
    """跑馬燈標籤：當文字過長時自動捲動，全部回到定點後暫停再重新開始"""
    _global_pause_counter = 0
    _global_pause_threshold = 166
    _instances = weakref.WeakSet()
    _waiting_for_sync = False
    
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._scroll_pos = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timeout)
        self._timer.setInterval(30)
        self._is_scrollable = False
        self._at_home = True
        self._is_active = False
        
        MarqueeLabel._instances.add(self)

    def setText(self, text):
        if text == self.text():
            return
        super().setText(text)
        self._scroll_pos = 0
        self._at_home = True
        self._check_scrollable()
        
        if self._is_active:
            MarqueeLabel._waiting_for_sync = False
            MarqueeLabel._global_pause_counter = MarqueeLabel._global_pause_threshold
            if not self._timer.isActive():
                self._timer.start()
        
        self.update()
    
    def showEvent(self, event):
        super().showEvent(event)
        self._activate()
    
    def hideEvent(self, event):
        super().hideEvent(event)
        self._deactivate()
    
    def _activate(self):
        if self._is_active:
            return
        self._is_active = True
        self._scroll_pos = 0
        self._at_home = True
        self._check_scrollable()
        MarqueeLabel._global_pause_counter = MarqueeLabel._global_pause_threshold
        MarqueeLabel._waiting_for_sync = False
        if self._is_scrollable and not self._timer.isActive():
            self._timer.start()
        self.update()
    
    def _deactivate(self):
        if not self._is_active:
            return
        self._is_active = False
        if self._timer.isActive():
            self._timer.stop()
        self._scroll_pos = 0
        self._at_home = True

    def _check_scrollable(self):
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self.text())
        self._is_scrollable = text_width > self.width()
        
    def paintEvent(self, a0):
        painter = QPainter(self)
        
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self.text())
        
        if text_width <= self.width():
            if self._timer.isActive():
                self._timer.stop()
            self._is_scrollable = False
            painter.drawText(self.rect(), int(self.alignment()), self.text())
            return

        self._is_scrollable = True
        
        if self._is_active and not self._timer.isActive():
            self._timer.start()

        painter.save()
        painter.setClipRect(self.rect())
        
        x = -self._scroll_pos
        y = (self.height() + fm.ascent() - fm.descent()) / 2
        
        painter.drawText(int(x), int(y), self.text())
        
        if self._scroll_pos > 0:
            painter.drawText(int(x + text_width + 20), int(y), self.text())
        
        painter.restore()

    def _on_timeout(self):
        if not self._is_active:
            if self._timer.isActive():
                self._timer.stop()
            return
        
        if MarqueeLabel._global_pause_counter > 0:
            MarqueeLabel._global_pause_counter -= 1
            if MarqueeLabel._global_pause_counter == 0:
                MarqueeLabel._waiting_for_sync = False
            self.update()
            return
        
        if not self._is_scrollable:
            self._at_home = True
            return
        
        if MarqueeLabel._waiting_for_sync:
            if self._scroll_pos == 0:
                self._at_home = True
                self.update()
                return
            else:
                self._scroll_pos += 1
                fm = self.fontMetrics()
                text_width = fm.horizontalAdvance(self.text())
                
                if self._scroll_pos >= text_width + 20:
                    self._scroll_pos = 0
                    self._at_home = True
                    
                    all_at_home = all(
                        inst._at_home for inst in MarqueeLabel._instances
                        if inst._is_active
                    )
                    
                    if all_at_home:
                        MarqueeLabel._global_pause_counter = MarqueeLabel._global_pause_threshold
                        MarqueeLabel._waiting_for_sync = False
                
                self.update()
                return
        
        self._at_home = False
        self._scroll_pos += 1
        
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self.text())
        
        if self._scroll_pos >= text_width + 20:
            self._scroll_pos = 0
            self._at_home = True
            
            all_at_home = all(
                inst._at_home for inst in MarqueeLabel._instances
                if inst._is_active
            )
            
            if all_at_home:
                MarqueeLabel._global_pause_counter = MarqueeLabel._global_pause_threshold
                MarqueeLabel._waiting_for_sync = False
            elif not MarqueeLabel._waiting_for_sync:
                MarqueeLabel._waiting_for_sync = True
            
        self.update()
    
    def __del__(self):
        try:
            if hasattr(self, '_timer') and self._timer is not None:
                if self._timer.isActive():
                    self._timer.stop()
                self._timer.deleteLater()
        except RuntimeError:
            pass


class ToastManager(QWidget):
    """用 paintEvent 繪製的 toast 覆蓋層，避免浮動 child widget 疊層問題。"""

    COLORS = {
        "info": ("#1d4ed8", "i"),
        "success": ("#16a34a", "✓"),
        "warning": ("#d97706", "!"),
        "error": ("#dc2626", "×"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self._toasts = []
        self._toast_rects = []
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        if parent is not None:
            parent.installEventFilter(self)
            self.update_position()
            self.show()

    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.update_position()
        return super().eventFilter(obj, event)

    def update_position(self):
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(0, 0, parent.width(), parent.height())
        self.raise_()
        self.update()

    def show_toast(self, message, level="info", duration_ms=3000):
        if not self.isVisible():
            self.show()
        now = time.monotonic()
        self._toasts.append({
            "message": str(message),
            "level": level if level in self.COLORS else "info",
            "duration": max(800, int(duration_ms)) / 1000.0,
            "created_at": now,
        })
        self.update_position()
        if not self._timer.isActive():
            self._timer.start()
        print(f"[Toast] 顯示通知: {message} ({level}, {duration_ms}ms)")
        return True

    def _tick(self):
        now = time.monotonic()
        before = len(self._toasts)
        self._toasts = [
            toast for toast in self._toasts
            if now - toast["created_at"] < toast["duration"] + 0.25
        ]
        if self._toasts:
            self.update()
        else:
            self._timer.stop()
            if before:
                self.update()

    def paintEvent(self, event):
        if not self._toasts:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        now = time.monotonic()
        margin = 18
        spacing = 10
        width = 360
        x = self.width() - width - margin
        y = margin
        self._toast_rects = []

        for toast in self._toasts:
            message = toast["message"]
            elapsed = now - toast["created_at"]
            duration = toast["duration"]
            if elapsed < 0.18:
                opacity = elapsed / 0.18
            elif elapsed > duration:
                opacity = max(0.0, 1.0 - (elapsed - duration) / 0.25)
            else:
                opacity = 1.0

            color_hex, icon_text = self.COLORS[toast["level"]]
            accent = QColor(color_hex)
            bg = QColor(20, 22, 30, int(238 * opacity))
            border = QColor(accent)
            border.setAlpha(int(255 * opacity))
            text_color = QColor(T('TEXT_PRIMARY'))
            text_color.setAlpha(int(255 * opacity))

            font = QFont("Arial", 18)
            font.setBold(True)
            painter.setFont(font)
            fm = painter.fontMetrics()
            text_rect = fm.boundingRect(
                QRect(0, 0, width - 72, 200),
                Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft,
                message,
            )
            height = max(54, text_rect.height() + 24)
            rect = QRect(x, y, width, height)
            self._toast_rects.append(rect)

            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), 8, 8)
            painter.fillPath(path, bg)

            painter.setPen(QPen(border, 1))
            painter.drawPath(path)
            painter.fillRect(rect.x(), rect.y() + 1, 5, rect.height() - 2, border)

            painter.setPen(text_color)
            icon_font = QFont("Arial", 22)
            icon_font.setBold(True)
            painter.setFont(icon_font)
            painter.drawText(QRect(rect.x() + 14, rect.y() + 12, 28, 28), Qt.AlignmentFlag.AlignCenter, icon_text)

            painter.setFont(font)
            painter.drawText(
                QRect(rect.x() + 52, rect.y() + 12, width - 72, height - 24),
                Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                message,
            )

            y += height + spacing

        painter.end()

    def mousePressEvent(self, event):
        for index, rect in enumerate(self._toast_rects):
            if rect.contains(event.pos()):
                if index < len(self._toasts):
                    self._toasts.pop(index)
                    self.update()
                return
        super().mousePressEvent(event)
