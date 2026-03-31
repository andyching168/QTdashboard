# Auto-extracted from main.py
import time
import math
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

class AnalogGauge(QWidget):
    def __init__(self, min_val=0, max_val=100, gauge_style=None, labels=None, title="", 
                 red_zone_start=None, parent=None):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.value = min_val
        self.gauge_style = gauge_style if gauge_style else GaugeStyle()
        self.labels = labels # Dictionary {value: "Label"} or None for auto numbers
        self.title = title
        self.red_zone_start = red_zone_start
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy()
        )
        self.setMinimumSize(300, 300)

    def set_value(self, val):
        self.value = max(self.min_val, min(self.max_val, val))
        self.update()

    def paintEvent(self, a0):  # type: ignore
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        side = min(width, height)
        
        painter.translate(width / 2, height / 2)
        painter.scale(side / 200.0, side / 200.0) # Normalize coordinate system to -100 to 100

        self.draw_background(painter)
        self.draw_ticks(painter)
        self.draw_labels(painter)
        self.draw_needle(painter)
        self.draw_center_circle(painter)
        self.draw_title(painter)

    def draw_background(self, painter):
        # Draw outer circle with gradient
        gradient = QRadialGradient(0, 0, 95)
        gradient.setColorAt(0, QColor(30, 30, 35))
        gradient.setColorAt(0.7, QColor(20, 20, 25))
        gradient.setColorAt(1, QColor(10, 10, 15))
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(50, 50, 60), 2))
        painter.drawEllipse(QPointF(0, 0), 95, 95)

    def draw_ticks(self, painter):
        radius = 75
        pen = QPen(self.gauge_style.tick_color)
        painter.setPen(pen)

        total_ticks = self.gauge_style.major_ticks * (self.gauge_style.minor_ticks + 1)
        
        for i in range(total_ticks + 1):
            ratio = i / total_ticks
            angle = self.gauge_style.start_angle - (ratio * self.gauge_style.span_angle)
            
            is_major = (i % (self.gauge_style.minor_ticks + 1) == 0)
            
            tick_len = 12 if is_major else 6
            pen.setWidth(3 if is_major else 1)
            
            # Determine if in red zone
            current_val = self.min_val + ratio * (self.max_val - self.min_val)
            if self.red_zone_start and current_val >= self.red_zone_start:
                pen.setColor(QColor(255, 50, 50))
            else:
                pen.setColor(self.gauge_style.tick_color)
            
            painter.setPen(pen)

            rad_angle = math.radians(angle)
            p1 = QPointF(math.cos(rad_angle) * radius, -math.sin(rad_angle) * radius)
            p2 = QPointF(math.cos(rad_angle) * (radius - tick_len), -math.sin(rad_angle) * (radius - tick_len))
            painter.drawLine(p1, p2)

    def draw_labels(self, painter):
        radius = 55
        painter.setPen(self.gauge_style.label_color)
        font = QFont("Arial", int(11 * self.gauge_style.text_scale))
        font.setBold(True)
        painter.setFont(font)

        if self.labels:
            # Custom labels (C, H, E, F)
            for val, text in self.labels.items():
                ratio = (val - self.min_val) / (self.max_val - self.min_val)
                angle = self.gauge_style.start_angle - (ratio * self.gauge_style.span_angle)
                rad_angle = math.radians(angle)
                
                x = math.cos(rad_angle) * radius
                y = -math.sin(rad_angle) * radius
                
                rect = QRectF(x - 15, y - 10, 30, 20)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        else:
            # Numeric labels
            step = (self.max_val - self.min_val) / self.gauge_style.major_ticks
            for i in range(self.gauge_style.major_ticks + 1):
                val = self.min_val + i * step
                ratio = i / self.gauge_style.major_ticks
                angle = self.gauge_style.start_angle - (ratio * self.gauge_style.span_angle)
                rad_angle = math.radians(angle)
                
                x = math.cos(rad_angle) * radius
                y = -math.sin(rad_angle) * radius
                
                # Color labels in red zone
                if self.red_zone_start and val >= self.red_zone_start:
                    painter.setPen(QColor(255, 100, 100))
                else:
                    painter.setPen(self.gauge_style.label_color)
                
                rect = QRectF(x - 20, y - 10, 40, 20)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(int(val)))

    def draw_needle(self, painter):
        ratio = (self.value - self.min_val) / (self.max_val - self.min_val)
        angle = self.gauge_style.start_angle - (ratio * self.gauge_style.span_angle)
        
        painter.save()
        painter.rotate(-angle)
        
        # Draw needle with glow effect
        # Outer glow
        glow_color = QColor(self.gauge_style.needle_color)
        glow_color.setAlpha(100)
        painter.setPen(QPen(glow_color, 6))
        painter.drawLine(QPointF(0, 0), QPointF(65, 0))
        
        # Main needle
        needle_gradient = QLinearGradient(0, 0, 65, 0)
        needle_gradient.setColorAt(0, self.gauge_style.needle_color)
        needle_gradient.setColorAt(1, QColor(self.gauge_style.needle_color).lighter(150))
        
        painter.setBrush(QBrush(needle_gradient))
        painter.setPen(QPen(self.gauge_style.needle_color.lighter(120), 1))
        
        needle = QPolygonF([
            QPointF(-5, 0),
            QPointF(0, -3),
            QPointF(65, -1.5),
            QPointF(68, 0),
            QPointF(65, 1.5),
            QPointF(0, 3)
        ])
        painter.drawPolygon(needle)
        
        painter.restore()

    def draw_center_circle(self, painter):
        if not self.gauge_style.show_center_circle:
            return
        
        # Center circle with gradient
        gradient = QRadialGradient(0, 0, 10)
        gradient.setColorAt(0, QColor(60, 60, 70))
        gradient.setColorAt(1, QColor(30, 30, 40))
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(80, 80, 90), 2))
        painter.drawEllipse(QPointF(0, 0), 8, 8)

    def draw_title(self, painter):
        if not self.title:
            return
        painter.setPen(self.gauge_style.label_color)
        font = QFont("Arial", int(7 * self.gauge_style.text_scale))
        painter.setFont(font)
        rect = QRectF(-50, 35, 100, 20)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.title)



