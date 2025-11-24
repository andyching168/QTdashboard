import sys
import os
import math
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QHBoxLayout, QVBoxLayout, QGridLayout, QStackedWidget, QProgressBar, QPushButton
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QPropertyAnimation, QEasingCurve, pyqtSignal, QPoint, pyqtSlot
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPolygonF, QBrush, QLinearGradient, QRadialGradient, QPainterPath, QPixmap, QMouseEvent

# Spotify Imports
from spotify_integration import setup_spotify
from spotify_auth import SpotifyAuthManager
from spotify_qr_auth import SpotifyQRAuthDialog

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

class MusicCard(QWidget):
    """音樂播放器卡片"""
    
    # Signal to notify dashboard to start binding process
    request_bind = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(380, 380)
        
        # 設置背景樣式
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a25, stop:1 #0f0f18);
                border-radius: 20px;
            }
        """)
        
        # Main layout with StackedWidget
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)
        
        # Page 1: Not Configured (Bind UI)
        self.bind_page = QWidget()
        self.setup_bind_ui()
        self.stack.addWidget(self.bind_page)
        
        # Page 2: Player UI
        self.player_page = QWidget()
        self.setup_player_ui()
        self.stack.addWidget(self.player_page)
        
        # Default to Bind page if config missing (logic handled by Dashboard)
        self.stack.setCurrentWidget(self.bind_page)

    def setup_bind_ui(self):
        layout = QVBoxLayout(self.bind_page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_label = QLabel("🎵")
        icon_label.setStyleSheet("font-size: 80px; background: transparent;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        text_label = QLabel("Spotify 未連結")
        text_label.setStyleSheet("color: white; font-size: 24px; font-weight: bold; background: transparent;")
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        desc_label = QLabel("請點擊下方按鈕進行綁定\n以顯示播放資訊")
        desc_label.setStyleSheet("color: #aaa; font-size: 16px; background: transparent;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        
        self.bind_btn = QPushButton("綁定 Spotify")
        self.bind_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bind_btn.setFixedSize(200, 50)
        self.bind_btn.setStyleSheet("""
            QPushButton {
                background-color: #1DB954;
                color: white;
                border-radius: 25px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1ed760;
            }
            QPushButton:pressed {
                background-color: #1aa34a;
            }
        """)
        self.bind_btn.clicked.connect(self.request_bind.emit)
        
        layout.addStretch()
        layout.addWidget(icon_label)
        layout.addWidget(text_label)
        layout.addWidget(desc_label)
        layout.addSpacing(20)
        layout.addWidget(self.bind_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

    def setup_player_ui(self):
        layout = QVBoxLayout(self.player_page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 標題
        title_label = QLabel("Now Playing")
        title_label.setStyleSheet("""
            color: #6af;
            font-size: 14px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 專輯封面
        self.album_art = QLabel()
        self.album_art.setFixedSize(180, 180)
        self.album_art.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #4a5568, stop:0.5 #2d3748, stop:1 #1a202c);
            border-radius: 15px;
            border: 3px solid #4a5568;
        """)
        self.album_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 創建專輯圖標 (音符符號)
        album_icon = QLabel("♪")
        album_icon.setStyleSheet("""
            color: #6af;
            font-size: 80px;
            background: transparent;
        """)
        album_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        album_icon.setParent(self.album_art)
        album_icon.setGeometry(0, 0, 180, 180)
        
        # 歌曲名稱
        self.song_title = QLabel("Waiting for music...")
        self.song_title.setStyleSheet("""
            color: white;
            font-size: 18px;
            font-weight: bold;
            background: transparent;
        """)
        self.song_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 演出者
        self.artist_name = QLabel("-")
        self.artist_name.setStyleSheet("""
            color: #aaa;
            font-size: 14px;
            background: transparent;
        """)
        self.artist_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 進度條容器
        progress_widget = QWidget()
        progress_widget.setStyleSheet("background: transparent;")
        progress_layout = QVBoxLayout(progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(5)
        
        # 進度條
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #2d3748;
                border-radius: 3px;
                border: none;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6af, stop:1 #4a9eff);
                border-radius: 3px;
            }
        """)
        
        # 時間標籤
        time_layout = QHBoxLayout()
        time_layout.setContentsMargins(0, 0, 0, 0)
        
        self.current_time = QLabel("0:00")
        self.current_time.setStyleSheet("""
            color: #888;
            font-size: 11px;
            background: transparent;
        """)
        
        self.total_time = QLabel("0:00")
        self.total_time.setStyleSheet("""
            color: #888;
            font-size: 11px;
            background: transparent;
        """)
        
        time_layout.addWidget(self.current_time)
        time_layout.addStretch()
        time_layout.addWidget(self.total_time)
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addLayout(time_layout)
        
        # 組合佈局
        layout.addWidget(title_label)
        layout.addStretch()
        layout.addWidget(self.album_art, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(10)
        layout.addWidget(self.song_title)
        layout.addWidget(self.artist_name)
        layout.addStretch()
        layout.addWidget(progress_widget)
    
    def show_bind_ui(self):
        self.stack.setCurrentWidget(self.bind_page)
        
    def show_player_ui(self):
        self.stack.setCurrentWidget(self.player_page)

    def set_song(self, title, artist):
        """設置歌曲信息"""
        self.song_title.setText(title)
        self.artist_name.setText(artist)
    
    def set_album_art(self, pixmap):
        """
        設置專輯封面圖片
        
        Args:
            pixmap: QPixmap 物件
        """
        if pixmap and not pixmap.isNull():
            # 縮放圖片以適應尺寸
            scaled_pixmap = pixmap.scaled(
                180, 180,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.album_art.setPixmap(scaled_pixmap)
            # 移除預設的音符圖標
            for child in self.album_art.children():
                if isinstance(child, QLabel):
                    child.hide()
        else:
            # 恢復預設樣式
            self.album_art.clear()
            for child in self.album_art.children():
                if isinstance(child, QLabel):
                    child.show()
    
    def set_progress(self, current_seconds, total_seconds):
        """設置播放進度"""
        if total_seconds > 0:
            progress = int((current_seconds / total_seconds) * 100)
            self.progress_bar.setValue(progress)
        
        # 格式化時間
        self.current_time.setText(f"{int(current_seconds//60)}:{int(current_seconds%60):02d}")
        self.total_time.setText(f"{int(total_seconds//60)}:{int(total_seconds%60):02d}")
    
    def update_from_spotify(self, track_info):
        """
        從 Spotify track_info 更新卡片內容
        
        Args:
            track_info: 包含 name, artists, duration_ms, progress_ms, album_art 的字典
        """
        if not track_info:
            return
        
        # 更新歌曲資訊
        self.set_song(track_info.get('name', 'Unknown'), track_info.get('artists', 'Unknown'))
        
        # 更新進度
        progress_ms = track_info.get('progress_ms', 0)
        duration_ms = track_info.get('duration_ms', 0)
        if duration_ms > 0:
            self.set_progress(progress_ms / 1000, duration_ms / 1000)
        
        # 更新專輯封面 (如果有 PIL Image)
        if 'album_art' in track_info and track_info['album_art']:
            self.set_album_art_from_pil(track_info['album_art'])
    
    def set_album_art_from_pil(self, pil_image):
        """
        從 PIL Image 設置專輯封面
        
        Args:
            pil_image: PIL.Image.Image 物件
        """
        try:
            from PIL.ImageQt import ImageQt
            # 轉換 PIL Image 為 QPixmap
            qim = ImageQt(pil_image)
            pixmap = QPixmap.fromImage(qim)
            self.set_album_art(pixmap)
        except Exception as e:
            import logging
            logging.error(f"設置專輯封面失敗: {e}")


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
    # 定義 Qt Signals，用於從背景執行緒安全地更新 UI
    signal_update_rpm = pyqtSignal(float)
    signal_update_speed = pyqtSignal(float)
    signal_update_temperature = pyqtSignal(float)
    signal_update_fuel = pyqtSignal(float)
    signal_update_gear = pyqtSignal(str)
    signal_update_turn_signal = pyqtSignal(str)  # "left", "right", "both", "off"
    
    # Spotify 相關 Signals
    signal_update_spotify_track = pyqtSignal(str, str)
    signal_update_spotify_progress = pyqtSignal(float, float)
    signal_update_spotify_art = pyqtSignal(object)  # 傳遞 PIL Image 物件

    def __init__(self):
        super().__init__()
        self.setWindowTitle("汽車儀表板模擬器 - W/S:速度 Q/E:水溫 A/D:油量 1-6:檔位 Z/X/C:方向燈")
        
        # 連接 Signals 到 Slots
        self.signal_update_rpm.connect(self._slot_set_rpm)
        self.signal_update_speed.connect(self._slot_set_speed)
        self.signal_update_temperature.connect(self._slot_set_temperature)
        self.signal_update_fuel.connect(self._slot_set_fuel)
        self.signal_update_gear.connect(self._slot_set_gear)
        
        # 連接 Spotify Signals
        self.signal_update_spotify_track.connect(self._slot_update_spotify_track)
        self.signal_update_spotify_progress.connect(self._slot_update_spotify_progress)
        self.signal_update_spotify_art.connect(self._slot_update_spotify_art)
        
        # 連接方向燈 Signal
        self.signal_update_turn_signal.connect(self._slot_update_turn_signal)
        
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
    
    def create_status_bar(self):
        """創建頂部狀態欄，包含方向燈指示"""
        status_bar = QWidget()
        status_bar.setFixedHeight(50)
        status_bar.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a1f, stop:1 #0f0f14);
                border-bottom: 2px solid #2a2a35;
            }
        """)
        
        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # === 左側區域：漸層條（從最左到1/4）+ 圖標疊在上面 ===
        left_container = QWidget()
        left_container.setFixedWidth(480)  # 1920 * 0.25 = 480 (1/4 螢幕寬)
        left_container.setStyleSheet("background: transparent;")
        
        # 漸層條從最邊緣到整個 1/4 區域
        self.left_gradient_bar = QWidget(left_container)
        self.left_gradient_bar.setGeometry(0, 5, 480, 40)  # 整個左側 1/4 區域
        
        # 左轉燈圖標（疊在條的最左邊上方）
        self.left_turn_indicator = QLabel("⬅", left_container)
        self.left_turn_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.left_turn_indicator.setGeometry(10, 5, 60, 40)
        self.left_turn_indicator.setStyleSheet("""
            QLabel {
                color: #2a2a2a;
                font-size: 28px;
                font-weight: bold;
                background: transparent;
                border: 2px solid #000000;
                border-radius: 8px;
            }
        """)
        # 確保圖標在上層
        self.left_turn_indicator.raise_()
        
        # === 中間區域 - 時間顯示 ===
        center_container = QWidget()
        center_container.setStyleSheet("background: transparent;")
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.time_label = QLabel("--:--")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet("""
            QLabel {
                color: #6af;
                font-size: 24px;
                font-weight: bold;
                background: transparent;
                letter-spacing: 2px;
            }
        """)
        center_layout.addWidget(self.time_label)
        
        # 更新時間
        self.time_timer = QTimer()
        self.time_timer.timeout.connect(self.update_time_display)
        self.time_timer.start(1000)
        self.update_time_display()
        
        # === 右側區域：漸層條（從1/4到最右）+ 圖標疊在上面 ===
        right_container = QWidget()
        right_container.setFixedWidth(480)  # 1920 * 0.25 = 480 (1/4 螢幕寬)
        right_container.setStyleSheet("background: transparent;")
        
        # 漸層條從整個 1/4 區域到最邊緣
        self.right_gradient_bar = QWidget(right_container)
        self.right_gradient_bar.setGeometry(0, 5, 480, 40)  # 整個右側 1/4 區域
        
        # 右轉燈圖標（疊在條的最右邊上方）
        self.right_turn_indicator = QLabel("➡", right_container)
        self.right_turn_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.right_turn_indicator.setGeometry(410, 5, 60, 40)
        self.right_turn_indicator.setStyleSheet("""
            QLabel {
                color: #2a2a2a;
                font-size: 28px;
                font-weight: bold;
                background: transparent;
                border: 2px solid #000000;
                border-radius: 8px;
            }
        """)
        # 確保圖標在上層
        self.right_turn_indicator.raise_()
        
        # 組合佈局
        layout.addWidget(left_container)
        layout.addWidget(center_container, 1)
        layout.addWidget(right_container)
        
        # 方向燈狀態（直接反映 CAN 訊號的亮滅狀態）
        self.left_turn_on = False   # 左轉燈當前是否為亮
        self.right_turn_on = False  # 右轉燈當前是否為亮
        
        # 漸層動畫位置 (0.0 到 1.0)
        self.left_gradient_pos = 0.0
        self.right_gradient_pos = 0.0
        
        # 動畫計時器 - 用於平滑的漸層效果
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.update_gradient_animation)
        self.animation_timer.start(16)  # 約 60 FPS
        
        return status_bar
    
    def update_time_display(self):
        """更新時間顯示"""
        from datetime import datetime
        current_time = datetime.now().strftime("%H:%M")
        self.time_label.setText(current_time)
    
    def update_gradient_animation(self):
        """更新漸層動畫效果"""
        # 熄滅動畫速度
        fade_speed = 0.05
        
        # 左轉燈動畫
        if self.left_turn_on:
            # 亮起時直接全滿
            self.left_gradient_pos = 1.0
        else:
            # 熄滅時從中間向外漸暗
            self.left_gradient_pos = max(0.0, self.left_gradient_pos - fade_speed)
        
        # 右轉燈動畫
        if self.right_turn_on:
            # 亮起時直接全滿
            self.right_gradient_pos = 1.0
        else:
            # 熄滅時從中間向外漸暗
            self.right_gradient_pos = max(0.0, self.right_gradient_pos - fade_speed)
        
        # 更新樣式
        self.update_turn_signal_style()
    
    def update_turn_signal_style(self):
        """更新方向燈的視覺樣式"""
        # 方向燈圖標樣式
        indicator_inactive = """
            QLabel {
                color: #2a2a2a;
                font-size: 28px;
                font-weight: bold;
                background: transparent;
                border: 2px solid #2a2a2a;
                border-radius: 8px;
            }
        """
        
        indicator_active = """
            QLabel {
                color: #00FF00;
                font-size: 28px;
                font-weight: bold;
                background: transparent;
                border: 2px solid #000000;
                border-radius: 8px;
            }
        """
        
        # 漸層條背景樣式（關閉時）
        gradient_inactive = """
            QWidget {
                background: transparent;
            }
        """
        
        # === 左轉燈 ===
        # 圖標的亮滅只看 left_turn_on，不受動畫影響
        if self.left_turn_on:
            self.left_turn_indicator.setStyleSheet(indicator_active)
        else:
            self.left_turn_indicator.setStyleSheet(indicator_inactive)
        
        # 漸層條的動畫效果
        pos = self.left_gradient_pos
        
        if pos > 0:
            # pos=1.0 時：整條均勻亮橙色
            # pos<1.0 時：從中間向外漸暗
            if pos >= 1.0:
                # 完全亮起：整條均勻的亮綠色
                left_gradient_style = """
                    QWidget {
                        background: rgba(177, 255, 0, 0.7);
                        border-radius: 4px;
                    }
                """
            else:
                # 熄滅中：從中間向外漸暗
                left_gradient_style = f"""
                    QWidget {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 rgba(177, 255, 0, {pos * 0.7:.2f}),
                            stop:{0.3 * pos:.2f} rgba(177, 255, 0, {pos * 0.7:.2f}),
                            stop:{0.5 * pos:.2f} rgba(177, 255, 0, {pos * 0.5:.2f}),
                            stop:{0.7 * pos:.2f} rgba(140, 255, 0, {pos * 0.3:.2f}),
                            stop:{0.85 * pos:.2f} rgba(120, 255, 0, {pos * 0.15:.2f}),
                            stop:1 rgba(30, 30, 30, 0.1));
                        border-radius: 4px;
                    }}
                """
            self.left_gradient_bar.setStyleSheet(left_gradient_style)
        else:
            self.left_gradient_bar.setStyleSheet(gradient_inactive)
        
        # === 右轉燈 ===
        # 圖標的亮滅只看 right_turn_on，不受動畫影響
        if self.right_turn_on:
            self.right_turn_indicator.setStyleSheet(indicator_active)
        else:
            self.right_turn_indicator.setStyleSheet(indicator_inactive)
        
        # 漸層條的動畫效果
        pos = self.right_gradient_pos
        
        if pos > 0:
            # pos=1.0 時：整條均勻亮橙色
            # pos<1.0 時：從中間向外漸暗
            if pos >= 1.0:
                # 完全亮起：整條均勻的亮綠色
                right_gradient_style = """
                    QWidget {
                        background: rgba(177, 255, 0, 0.7);
                        border-radius: 4px;
                    }
                """
            else:
                # 熄滅中：從中間向外漸暗
                right_gradient_style = f"""
                    QWidget {{
                        background: qlineargradient(x1:1, y1:0, x2:0, y2:0,
                            stop:0 rgba(177, 255, 0, {pos * 0.7:.2f}),
                            stop:{0.3 * pos:.2f} rgba(177, 255, 0, {pos * 0.7:.2f}),
                            stop:{0.5 * pos:.2f} rgba(177, 255, 0, {pos * 0.5:.2f}),
                            stop:{0.7 * pos:.2f} rgba(140, 255, 0, {pos * 0.3:.2f}),
                            stop:{0.85 * pos:.2f} rgba(120, 255, 0, {pos * 0.15:.2f}),
                            stop:1 rgba(30, 30, 30, 0.1));
                        border-radius: 4px;
                    }}
                """
            self.right_gradient_bar.setStyleSheet(right_gradient_style)
        else:
            self.right_gradient_bar.setStyleSheet(gradient_inactive)

    def init_ui(self):
        # 主垂直佈局（包含狀態欄和儀表板）
        main_vertical_layout = QVBoxLayout()
        main_vertical_layout.setContentsMargins(0, 0, 0, 0)
        main_vertical_layout.setSpacing(0)
        self.setLayout(main_vertical_layout)
        
        # === 頂部狀態欄 ===
        self.status_bar = self.create_status_bar()
        main_vertical_layout.addWidget(self.status_bar)
        
        # === 主儀表板區域 ===
        dashboard_container = QWidget()
        main_layout = QHBoxLayout()
        dashboard_container.setLayout(main_layout)
        main_vertical_layout.addWidget(dashboard_container)
        
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
        
        # 右側：油量表 / 音樂卡片 (可切換) - 帶容器
        right_container = QWidget()
        right_container.setFixedSize(380, 420)  # 稍微增加高度以容納指示器
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)
        
        self.right_stack = QStackedWidget()
        self.right_stack.setFixedSize(380, 380)
        
        # 油量表
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
        
        # 音樂卡片
        self.music_card = MusicCard()
        self.music_card.request_bind.connect(self.start_spotify_auth)
        
        # 添加到堆疊
        self.right_stack.addWidget(self.fuel_gauge)  # index 0
        self.right_stack.addWidget(self.music_card)  # index 1
        self.right_stack.setCurrentIndex(0)  # 預設顯示油量表
        
        # 滑動指示器
        indicator_widget = QWidget()
        indicator_widget.setFixedHeight(35)
        indicator_widget.setStyleSheet("background: transparent;")
        indicator_layout = QHBoxLayout(indicator_widget)
        indicator_layout.setContentsMargins(0, 10, 0, 0)
        indicator_layout.setSpacing(8)
        
        # 創建圓點指示器
        self.indicators = []
        for i in range(2):  # 2 張卡片
            dot = QLabel("●")
            dot.setFixedSize(12, 12)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setStyleSheet("""
                color: #444;
                font-size: 20px;
            """)
            self.indicators.append(dot)
            indicator_layout.addWidget(dot)
        
        # 設置初始選中狀態
        self.indicators[0].setStyleSheet("color: #6af; font-size: 20px;")
        
        # 組合佈局
        right_layout.addWidget(self.right_stack)
        right_layout.addWidget(indicator_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # 當前卡片索引
        self.current_card_index = 0
        self.total_cards = 2
        
        # 觸控滑動相關
        self.touch_start_pos = None
        self.touch_start_time = None
        self.swipe_threshold = 50  # 滑動閾值（像素）
        self.is_swiping = False

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
        main_layout.addWidget(right_container)  # 使用包含指示器的容器
        main_layout.addSpacing(20)

    def init_data(self):
        """初始化儀表數據，可以從外部數據源更新"""
        self.speed = 0
        self.rpm = 0
        self.temp = 45  # 正常水溫約在 45-50% 位置（對應 85-95°C）
        self.fuel = 60  # 稍微偏上的油量
        self.gear = "P"
        self.update_display()
        
        # 嘗試初始化 Spotify
        self.check_spotify_config()

    def check_spotify_config(self):
        """檢查 Spotify 設定並初始化"""
        config_path = "spotify_config.json"
        cache_path = ".spotify_cache"
        
        # 只有當配置檔和快取都存在時才自動初始化
        if os.path.exists(config_path) and os.path.exists(cache_path):
            print("發現 Spotify 設定檔和快取，正在初始化...")
            self.music_card.show_player_ui()
            # 在背景執行緒初始化，避免卡住 UI
            QTimer.singleShot(100, lambda: setup_spotify(self))
        else:
            if not os.path.exists(config_path):
                print("未發現 Spotify 設定檔，顯示綁定介面")
            else:
                print("未發現授權快取，顯示綁定介面")
            self.music_card.show_bind_ui()

    def start_spotify_auth(self):
        """啟動 Spotify 授權流程"""
        print("啟動 Spotify 授權流程...")
        self.auth_manager = SpotifyAuthManager()
        self.auth_dialog = SpotifyQRAuthDialog(self.auth_manager)
        self.auth_dialog.signals.auth_completed.connect(self.on_auth_completed)
        
        # 設定為模態對話框，確保在全螢幕模式下也能正常顯示
        self.auth_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        # 設定視窗標誌，確保置於最前方
        self.auth_dialog.setWindowFlags(
            Qt.WindowType.Dialog | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint  # 無邊框，更適合觸控螢幕
        )
        
        # 顯示對話框
        self.auth_dialog.show()
        
        # 確保對話框置於螢幕中央
        screen_geometry = QApplication.primaryScreen().geometry()
        dialog_geometry = self.auth_dialog.geometry()
        x = (screen_geometry.width() - dialog_geometry.width()) // 2
        y = (screen_geometry.height() - dialog_geometry.height()) // 2
        self.auth_dialog.move(x, y)

    def on_auth_completed(self, success):
        """授權完成回調"""
        if success:
            print("Spotify 授權成功！")
            self.music_card.show_player_ui()
            setup_spotify(self)
        else:
            print("Spotify 授權失敗")
            self.music_card.show_bind_ui()
        
        # 關閉對話框 (如果還沒關閉)
        if hasattr(self, 'auth_dialog'):
            self.auth_dialog.close()
            del self.auth_dialog

    # === 執行緒安全的公開方法 (從背景執行緒呼叫) ===
    def set_speed(self, speed):
        """外部數據接口：設置速度 (0-200 km/h)
        執行緒安全：透過 Signal 發送，由主執行緒執行
        """
        self.signal_update_speed.emit(float(speed))
    
    def set_rpm(self, rpm):
        """外部數據接口：設置轉速 (0-8 x1000rpm)
        執行緒安全：透過 Signal 發送，由主執行緒執行
        """
        self.signal_update_rpm.emit(float(rpm))
    
    def set_temperature(self, temp):
        """外部數據接口：設置水溫 (0-100，對應約 40-120°C)
        - 0-30: 冷車 (藍區)
        - 40-75: 正常 (中間區)
        - 85-100: 過熱 (紅區)
        執行緒安全：透過 Signal 發送，由主執行緒執行
        """
        self.signal_update_temperature.emit(float(temp))
    
    def set_fuel(self, fuel):
        """外部數據接口：設置油量 (0-100)
        執行緒安全：透過 Signal 發送，由主執行緒執行
        """
        self.signal_update_fuel.emit(float(fuel))
    
    def set_gear(self, gear):
        """外部數據接口：設置檔位 (P/R/N/D/1/2/3/4/5/6)
        執行緒安全：透過 Signal 發送，由主執行緒執行
        """
        self.signal_update_gear.emit(str(gear).upper())
    
    def set_turn_signal(self, state):
        """外部數據接口：設置方向燈狀態（接收 CAN 訊號的亮滅狀態）
        Args:
            state: "left_on", "left_off", "right_on", "right_off", "both_on", "both_off", "off"
        執行緒安全：透過 Signal 發送，由主執行緒執行
        
        典型使用方式（85 BPM 閃爍，由 CAN bus 控制）：
            # CAN 訊號指示左轉燈亮
            dashboard.set_turn_signal("left_on")
            # CAN 訊號指示左轉燈滅
            dashboard.set_turn_signal("left_off")
        """
        valid_states = ["left_on", "left_off", "right_on", "right_off", "both_on", "both_off", "off"]
        if state in valid_states:
            self.signal_update_turn_signal.emit(state)
    
    # === Spotify 執行緒安全接口 ===
    def update_spotify_track(self, title, artist):
        """更新 Spotify 歌曲資訊 (執行緒安全)"""
        self.signal_update_spotify_track.emit(title, artist)

    def update_spotify_progress(self, current, total):
        """更新 Spotify 播放進度 (執行緒安全)"""
        self.signal_update_spotify_progress.emit(float(current), float(total))

    def update_spotify_art(self, pil_image):
        """更新 Spotify 專輯封面 (執行緒安全)"""
        self.signal_update_spotify_art.emit(pil_image)

    # === 實際執行 UI 更新的 Slot 方法 (在主執行緒中執行) ===
    @pyqtSlot(float)
    def _slot_set_speed(self, speed):
        """Slot: 在主執行緒中更新速度顯示"""
        self.speed = max(0, min(200, speed))
        self.update_display()
    
    @pyqtSlot(float)
    def _slot_set_rpm(self, rpm):
        """Slot: 在主執行緒中更新轉速顯示"""
        self.rpm = max(0, min(8, rpm))
        self.update_display()
    
    @pyqtSlot(float)
    def _slot_set_temperature(self, temp):
        """Slot: 在主執行緒中更新水溫顯示"""
        self.temp = max(0, min(100, temp))
        self.update_display()
    
    @pyqtSlot(float)
    def _slot_set_fuel(self, fuel):
        """Slot: 在主執行緒中更新油量顯示"""
        self.fuel = max(0, min(100, fuel))
        self.update_display()
    
    @pyqtSlot(str)
    def _slot_set_gear(self, gear):
        """Slot: 在主執行緒中更新檔位顯示"""
        self.gear = gear
        self.update_display()
    
    @pyqtSlot(str)
    def _slot_update_turn_signal(self, state):
        """Slot: 在主執行緒中更新方向燈狀態（從 CAN 訊號）
        Args:
            state: "left_on", "left_off", "right_on", "right_off", "both_on", "both_off", "off"
        """
        if state == "left_on":
            self.left_turn_on = True
            self.right_turn_on = False
        elif state == "left_off":
            self.left_turn_on = False
        elif state == "right_on":
            self.right_turn_on = True
            self.left_turn_on = False
        elif state == "right_off":
            self.right_turn_on = False
        elif state == "both_on":
            self.left_turn_on = True
            self.right_turn_on = True
        elif state == "both_off":
            self.left_turn_on = False
            self.right_turn_on = False
        elif state == "off":
            self.left_turn_on = False
            self.right_turn_on = False

    # === Spotify Slots ===
    @pyqtSlot(str, str)
    def _slot_update_spotify_track(self, title, artist):
        if hasattr(self, 'music_card'):
            self.music_card.set_song(title, artist)

    @pyqtSlot(float, float)
    def _slot_update_spotify_progress(self, current, total):
        if hasattr(self, 'music_card'):
            self.music_card.set_progress(current, total)

    @pyqtSlot(object)
    def _slot_update_spotify_art(self, pil_image):
        if hasattr(self, 'music_card'):
            self.music_card.set_album_art_from_pil(pil_image)

    def mousePressEvent(self, event):
        """觸控/滑鼠按下事件"""
        # 檢查是否在右側區域
        right_stack_global = self.right_stack.mapToGlobal(QPoint(0, 0))
        right_stack_rect = self.right_stack.geometry()
        right_stack_rect.moveTopLeft(right_stack_global)
        
        if right_stack_rect.contains(event.globalPosition().toPoint()):
            self.touch_start_pos = event.position().toPoint()
            self.is_swiping = True
            import time
            self.touch_start_time = time.time()
    
    def mouseMoveEvent(self, event):
        """觸控/滑鼠移動事件"""
        if self.is_swiping and self.touch_start_pos:
            # 計算滑動距離
            delta = event.position().toPoint() - self.touch_start_pos
            
            # 顯示視覺回饋（可選）
            if abs(delta.x()) > 10:
                # 這裡可以添加拖曳視覺效果
                pass
    
    def mouseReleaseEvent(self, event):
        """觸控/滑鼠釋放事件"""
        if self.is_swiping and self.touch_start_pos:
            # 計算滑動距離和方向
            end_pos = event.position().toPoint()
            delta = end_pos - self.touch_start_pos
            
            # 判斷是否為有效滑動
            if abs(delta.x()) > self.swipe_threshold:
                if delta.x() > 0:
                    # 向右滑動 - 切換到上一張
                    self.switch_card(-1)
                else:
                    # 向左滑動 - 切換到下一張
                    self.switch_card(1)
            
            # 重置狀態
            self.touch_start_pos = None
            self.is_swiping = False
    
    def switch_card(self, direction):
        """切換卡片
        Args:
            direction: 1 為下一張，-1 為上一張
        """
        self.current_card_index = (self.current_card_index + direction) % self.total_cards
        self.right_stack.setCurrentIndex(self.current_card_index)
        
        # 更新指示器
        for i, indicator in enumerate(self.indicators):
            if i == self.current_card_index:
                indicator.setStyleSheet("color: #6af; font-size: 20px;")  # 選中：藍色
            else:
                indicator.setStyleSheet("color: #444; font-size: 20px;")  # 未選中：灰色
        
        # 顯示提示
        card_names = ["油量表", "音樂播放器"]
        print(f"切換到: {card_names[self.current_card_index]}")
    
    def wheelEvent(self, event):
        """滑鼠滾輪切換右側卡片（桌面使用）"""
        # 檢查滑鼠是否在右側區域
        if self.right_stack.geometry().contains(event.position().toPoint()):
            delta = event.angleDelta().y()
            if delta > 0:  # 向上滾動
                self.switch_card(-1)
            else:  # 向下滾動
                self.switch_card(1)
    
    def keyPressEvent(self, event):
        """鍵盤模擬控制"""
        key = event.key()
        
        # 左右方向鍵切換卡片
        if key == Qt.Key.Key_Left:
            self.switch_card(-1)
            return
        elif key == Qt.Key.Key_Right:
            self.switch_card(1)
            return
        
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
        
        # Z/X/C: 方向燈測試（模擬 CAN 訊號的切換）
        elif key == Qt.Key.Key_Z:
            # 左轉燈切換
            if self.left_turn_on:
                self.set_turn_signal("left_off")
            else:
                self.set_turn_signal("left_on")
        elif key == Qt.Key.Key_X:
            # 右轉燈切換
            if self.right_turn_on:
                self.set_turn_signal("right_off")
            else:
                self.set_turn_signal("right_on")
        elif key == Qt.Key.Key_C:
            # 雙閃切換
            if self.left_turn_on and self.right_turn_on:
                self.set_turn_signal("both_off")
            else:
                self.set_turn_signal("both_on")

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
