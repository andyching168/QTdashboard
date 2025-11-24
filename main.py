import sys
import math
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QHBoxLayout, QVBoxLayout, QGridLayout
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPolygonF, QBrush, QLinearGradient, QRadialGradient, QPainterPath

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

class AnalogGauge(QWidget):
    def __init__(self, min_val=0, max_val=100, style=None, labels=None, title="", 
                 red_zone_start=None, parent=None):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.value = min_val
        self.style = style if style else GaugeStyle()
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

    def paintEvent(self, event):
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
        pen = QPen(self.style.tick_color)
        painter.setPen(pen)

        total_ticks = self.style.major_ticks * (self.style.minor_ticks + 1)
        
        for i in range(total_ticks + 1):
            ratio = i / total_ticks
            angle = self.style.start_angle - (ratio * self.style.span_angle)
            
            is_major = (i % (self.style.minor_ticks + 1) == 0)
            
            tick_len = 12 if is_major else 6
            pen.setWidth(3 if is_major else 1)
            
            # Determine if in red zone
            current_val = self.min_val + ratio * (self.max_val - self.min_val)
            if self.red_zone_start and current_val >= self.red_zone_start:
                pen.setColor(QColor(255, 50, 50))
            else:
                pen.setColor(self.style.tick_color)
            
            painter.setPen(pen)

            rad_angle = math.radians(angle)
            p1 = QPointF(math.cos(rad_angle) * radius, -math.sin(rad_angle) * radius)
            p2 = QPointF(math.cos(rad_angle) * (radius - tick_len), -math.sin(rad_angle) * (radius - tick_len))
            painter.drawLine(p1, p2)

    def draw_labels(self, painter):
        radius = 55
        painter.setPen(self.style.label_color)
        font = QFont("Arial", int(11 * self.style.text_scale))
        font.setBold(True)
        painter.setFont(font)

        if self.labels:
            # Custom labels (C, H, E, F)
            for val, text in self.labels.items():
                ratio = (val - self.min_val) / (self.max_val - self.min_val)
                angle = self.style.start_angle - (ratio * self.style.span_angle)
                rad_angle = math.radians(angle)
                
                x = math.cos(rad_angle) * radius
                y = -math.sin(rad_angle) * radius
                
                rect = QRectF(x - 15, y - 10, 30, 20)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        else:
            # Numeric labels
            step = (self.max_val - self.min_val) / self.style.major_ticks
            for i in range(self.style.major_ticks + 1):
                val = self.min_val + i * step
                ratio = i / self.style.major_ticks
                angle = self.style.start_angle - (ratio * self.style.span_angle)
                rad_angle = math.radians(angle)
                
                x = math.cos(rad_angle) * radius
                y = -math.sin(rad_angle) * radius
                
                # Color labels in red zone
                if self.red_zone_start and val >= self.red_zone_start:
                    painter.setPen(QColor(255, 100, 100))
                else:
                    painter.setPen(self.style.label_color)
                
                rect = QRectF(x - 20, y - 10, 40, 20)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(int(val)))

    def draw_needle(self, painter):
        ratio = (self.value - self.min_val) / (self.max_val - self.min_val)
        angle = self.style.start_angle - (ratio * self.style.span_angle)
        
        painter.save()
        painter.rotate(-angle)
        
        # Draw needle with glow effect
        # Outer glow
        glow_color = QColor(self.style.needle_color)
        glow_color.setAlpha(100)
        painter.setPen(QPen(glow_color, 6))
        painter.drawLine(QPointF(0, 0), QPointF(65, 0))
        
        # Main needle
        needle_gradient = QLinearGradient(0, 0, 65, 0)
        needle_gradient.setColorAt(0, self.style.needle_color)
        needle_gradient.setColorAt(1, QColor(self.style.needle_color).lighter(150))
        
        painter.setBrush(QBrush(needle_gradient))
        painter.setPen(QPen(self.style.needle_color.lighter(120), 1))
        
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
        if not self.style.show_center_circle:
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
        painter.setPen(self.style.label_color)
        font = QFont("Arial", int(7 * self.style.text_scale))
        painter.setFont(font)
        rect = QRectF(-50, 35, 100, 20)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.title)

class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("汽車儀表板模擬器 - 按 W/S:速度 Q/E:水溫 A/D:油量 1-4:檔位")
        
        # 適配 1920x480 螢幕
        self.setFixedSize(1920, 480)
        
        # Carbon fiber like background
        self.setStyleSheet("""
            QWidget {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a0f, stop:0.5 #15151a, stop:1 #0a0a0f);
            }
        """)

        self.init_ui()
        self.init_data()

    def init_ui(self):
        main_layout = QHBoxLayout()
        self.setLayout(main_layout)
        
        # 左側：水溫表（小型）
        temp_style = GaugeStyle(
            major_ticks=4, minor_ticks=1,
            start_angle=225, span_angle=270,
            tick_color=QColor(100, 150, 255),
            needle_color=QColor(100, 200, 255),  # 稍微偏藍綠色
            text_scale=1.0
        )
        # 水溫標籤：C(冷) - 中間正常 - H(熱)
        temp_labels = {0: "C", 50: "•", 100: "H"}
        self.temp_gauge = AnalogGauge(0, 100, temp_style, labels=temp_labels, title="TEMP", red_zone_start=85)
        self.temp_gauge.setFixedSize(380, 380)
        
        # 中間：轉速表（主要儀表 - 較大）
        rpm_style = GaugeStyle(
            major_ticks=8, minor_ticks=4,
            start_angle=225, span_angle=270,
            tick_color=QColor(100, 150, 255),
            needle_color=QColor(255, 100, 100),  # 紅色指針
            text_scale=1.4
        )
        self.rpm_gauge = AnalogGauge(0, 8, rpm_style, title="RPM x1000", red_zone_start=6.0)
        self.rpm_gauge.setFixedSize(450, 450)
        
        # 右側：油量表（小型）
        fuel_style = GaugeStyle(
            major_ticks=4, minor_ticks=1,
            start_angle=225, span_angle=270,
            tick_color=QColor(100, 150, 255),
            needle_color=QColor(255, 200, 100),  # 橙黃色（油料顏色）
            text_scale=1.0
        )
        # 油量標籤：E(空) - 1/2 - F(滿)
        fuel_labels = {0: "E", 50: "½", 100: "F"}
        self.fuel_gauge = AnalogGauge(0, 100, fuel_style, labels=fuel_labels, title="FUEL")
        self.fuel_gauge.setFixedSize(380, 380)

        # 中央數位速度顯示區
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setSpacing(5)
        center_layout.setContentsMargins(10, 0, 10, 0)
        
        # 速度顯示
        self.speed_label = QLabel("0")
        self.speed_label.setStyleSheet("""
            color: white;
            font-size: 140px;
            font-weight: bold;
            font-family: 'Arial', 'Helvetica', sans-serif;
            background: transparent;
        """)
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 單位標籤
        self.unit_label = QLabel("Km/h")
        self.unit_label.setStyleSheet("""
            color: #999;
            font-size: 24px;
            font-family: Arial;
            background: transparent;
        """)
        self.unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 檔位顯示
        self.gear_label = QLabel("P")
        self.gear_label.setStyleSheet("""
            color: #6af;
            font-size: 90px;
            font-weight: bold;
            font-family: Arial;
            background: transparent;
            border: 4px solid #456;
            border-radius: 20px;
            padding: 15px 30px;
        """)
        self.gear_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gear_label.setFixedSize(180, 180)
        
        center_layout.addStretch()
        center_layout.addWidget(self.speed_label)
        center_layout.addWidget(self.unit_label)
        center_layout.addSpacing(15)
        center_layout.addWidget(self.gear_label, alignment=Qt.AlignmentFlag.AlignCenter)
        center_layout.addStretch()

        # 組合版面 - 針對 1920x480 優化
        main_layout.addSpacing(20)
        main_layout.addWidget(self.temp_gauge)
        main_layout.addSpacing(10)
        main_layout.addWidget(self.rpm_gauge)
        main_layout.addSpacing(30)
        main_layout.addWidget(center_panel)
        main_layout.addSpacing(30)
        main_layout.addWidget(self.fuel_gauge)
        main_layout.addSpacing(20)

    def init_data(self):
        """初始化儀表數據，可以從外部數據源更新"""
        self.speed = 0
        self.rpm = 0
        self.temp = 45  # 正常水溫約在 45-50% 位置（對應 85-95°C）
        self.fuel = 60  # 稍微偏上的油量
        self.gear = "P"
        self.update_display()

    def set_speed(self, speed):
        """外部數據接口：設置速度 (0-200 km/h)"""
        self.speed = max(0, min(200, speed))
        self.update_display()
    
    def set_rpm(self, rpm):
        """外部數據接口：設置轉速 (0-8 x1000rpm)"""
        self.rpm = max(0, min(8, rpm))
        self.update_display()
    
    def set_temperature(self, temp):
        """外部數據接口：設置水溫 (0-100，對應約 40-120°C)
        - 0-30: 冷車 (藍區)
        - 40-75: 正常 (中間區)
        - 85-100: 過熱 (紅區)
        """
        self.temp = max(0, min(100, temp))
        self.update_display()
    
    def set_fuel(self, fuel):
        """外部數據接口：設置油量 (0-100)"""
        self.fuel = max(0, min(100, fuel))
        self.update_display()
    
    def set_gear(self, gear):
        """外部數據接口：設置檔位 (P/R/N/D/1/2/3/4/5/6)"""
        self.gear = str(gear).upper()
        self.update_display()

    def keyPressEvent(self, event):
        """鍵盤模擬控制"""
        key = event.key()
        
        # W/S: 速度與轉速
        if key == Qt.Key.Key_W:
            self.speed = min(180, self.speed + 5)
            # 轉速與速度成比例，但不超過紅區
            self.rpm = min(7, 0.8 + (self.speed / 180.0) * 5.0)
        elif key == Qt.Key.Key_S:
            self.speed = max(0, self.speed - 5)
            # 減速時轉速下降到怠速
            if self.speed < 5:
                self.rpm = 0.8  # 怠速
            else:
                self.rpm = max(0.8, 0.8 + (self.speed / 180.0) * 5.0)
            
        # Q/E: 水溫
        elif key == Qt.Key.Key_Q:
            self.temp = max(0, self.temp - 3)
        elif key == Qt.Key.Key_E:
            self.temp = min(100, self.temp + 3)
            
        # A/D: 油量
        elif key == Qt.Key.Key_A:
            self.fuel = max(0, self.fuel - 5)
        elif key == Qt.Key.Key_D:
            self.fuel = min(100, self.fuel + 5)
            
        # 1-6: 檔位
        elif key == Qt.Key.Key_1:
            self.gear = "P"
        elif key == Qt.Key.Key_2:
            self.gear = "R"
        elif key == Qt.Key.Key_3:
            self.gear = "N"
        elif key == Qt.Key.Key_4:
            self.gear = "D"
        elif key == Qt.Key.Key_5:
            self.gear = "S"
        elif key == Qt.Key.Key_6:
            self.gear = "L"

        self.update_display()

    def update_display(self):
        """更新所有儀表顯示"""
        self.rpm_gauge.set_value(self.rpm)
        self.temp_gauge.set_value(self.temp)
        self.fuel_gauge.set_value(self.fuel)
        self.speed_label.setText(str(int(self.speed)))
        
        # 更新檔位顯示顏色
        gear_colors = {
            "P": "#6af",  # 藍色
            "R": "#f66",  # 紅色
            "N": "#fa6",  # 橙色
            "D": "#6f6",  # 綠色
            "S": "#f6f",  # 紫色
            "L": "#ff6",  # 黃色
        }
        color = gear_colors.get(self.gear, "#6af")
        self.gear_label.setStyleSheet(f"""
            color: {color};
            font-size: 90px;
            font-weight: bold;
            font-family: Arial;
            background: transparent;
            border: 4px solid #456;
            border-radius: 20px;
            padding: 15px 30px;
        """)
        self.gear_label.setText(self.gear)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    dashboard = Dashboard()
    dashboard.show()
    sys.exit(app.exec())
