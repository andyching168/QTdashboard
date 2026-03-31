from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont, QPixmap
from PyQt6.QtCore import QRectF
import weakref


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
