# Auto-extracted from main.py
import time
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

from core.utils import perf_track
from ui.common import MarqueeLabel
from ui.theme import T


class MusicCard(QWidget):
    """音樂播放器卡片"""
    
    # Signal to notify dashboard to start binding process
    request_bind = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(380, 380)
        
        # 設置背景樣式
        self.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {T('BG_CARD')}, stop:1 #0f0f18);
                border-radius: 20px;
            }}
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
        text_label.setStyleSheet("color: {T('TEXT_PRIMARY')}; font-size: 24px; font-weight: bold; background: transparent;")
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        desc_label = QLabel("請點擊下方按鈕進行綁定\n以顯示播放資訊")
        desc_label.setStyleSheet("color: {T('TEXT_SECONDARY')}; font-size: 16px; background: transparent;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        
        self.bind_btn = QPushButton("綁定 Spotify")
        self.bind_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bind_btn.setFixedSize(200, 50)
        self.bind_btn.setStyleSheet("""
            QPushButton {
                background-color: #1DB954;
                color: {T('TEXT_PRIMARY')};
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
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(5)
        
        # 標題
        title_label = QLabel("Now Playing")
        title_label.setStyleSheet("""
            color: {T('PRIMARY')};
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
            color: {T('PRIMARY')};
            font-size: 80px;
            background: transparent;
        """)
        album_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        album_icon.setParent(self.album_art)
        album_icon.setGeometry(0, 0, 180, 180)
        
        # 文字資訊容器
        info_container = QWidget()
        info_container.setStyleSheet("background: transparent;")
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        
        # 歌曲名稱
        self.song_title = MarqueeLabel("Waiting for music...")
        self.song_title.setStyleSheet("""
            color: {T('TEXT_PRIMARY')};
            font-size: 18px;
            font-weight: bold;
            background: transparent;
        """)
        self.song_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.song_title.setFixedHeight(30)  # 固定高度避免跳動
        
        # 演出者
        self.artist_name = MarqueeLabel("-")
        self.artist_name.setStyleSheet("""
            color: {T('TEXT_SECONDARY')};
            font-size: 14px;
            background: transparent;
        """)
        self.artist_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artist_name.setFixedHeight(25)
        
        # 專輯名稱
        self.album_name = MarqueeLabel("-")
        self.album_name.setStyleSheet("""
            color: {T('TEXT_SECONDARY')};
            font-size: 12px;
            background: transparent;
        """)
        self.album_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_name.setFixedHeight(20)
        
        info_layout.addWidget(self.song_title)
        info_layout.addWidget(self.artist_name)
        info_layout.addWidget(self.album_name)
        
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
            color: {T('TEXT_SECONDARY')};
            font-size: 11px;
            background: transparent;
        """)
        
        self.total_time = QLabel("0:00")
        self.total_time.setStyleSheet("""
            color: {T('TEXT_SECONDARY')};
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
        layout.addStretch(1)
        layout.addWidget(self.album_art, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(10)
        layout.addWidget(info_container)
        layout.addStretch(1)
        layout.addWidget(progress_widget)
    
    def show_bind_ui(self):
        self.stack.setCurrentWidget(self.bind_page)
        
    def show_player_ui(self):
        self.stack.setCurrentWidget(self.player_page)

    def set_song(self, title, artist, album=""):
        """設置歌曲信息"""
        self.song_title.setText(title)
        self.artist_name.setText(artist)
        self.album_name.setText(album)
    
    def set_album_art(self, pixmap):
        """
        設置專輯封面圖片
        
        Args:
            pixmap: QPixmap 物件
        """
        if pixmap and not pixmap.isNull():
            # 縮放並裁切圖片以完全填滿正方形區域
            scaled_pixmap = pixmap.scaled(
                180, 180,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            
            # 如果圖片大於目標尺寸，進行中心裁切
            if scaled_pixmap.width() > 180 or scaled_pixmap.height() > 180:
                x = (scaled_pixmap.width() - 180) // 2
                y = (scaled_pixmap.height() - 180) // 2
                scaled_pixmap = scaled_pixmap.copy(x, y, 180, 180)
            
            # 創建圓角遮罩
            rounded_pixmap = QPixmap(180, 180)
            rounded_pixmap.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(rounded_pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # 創建圓角路徑
            path = QPainterPath()
            path.addRoundedRect(0, 0, 180, 180, 15, 15)
            
            # 設置裁切路徑並繪製圖片
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, scaled_pixmap)
            
            # 繪製邊框 (保持風格一致)
            # 使用 6px 筆寬，因為路徑在邊緣，一半在內一半在外，裁切後只剩 3px 在內
            pen = QPen(QColor("#4a5568"))
            pen.setWidth(6)
            painter.strokePath(path, pen)
            
            painter.end()
            
            self.album_art.setPixmap(rounded_pixmap)
            # 移除 stylesheet 中的 border 和 padding，避免壓縮圖片顯示區域
            self.album_art.setStyleSheet("background: transparent; border: none;")
            
            # 移除預設的音符圖標
            for child in self.album_art.children():
                if isinstance(child, QLabel):
                    child.hide()
        else:
            # 恢復預設樣式
            self.album_art.clear()
            self.album_art.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #4a5568, stop:0.5 #2d3748, stop:1 #1a202c);
                border-radius: 15px;
                border: 3px solid #4a5568;
            """)
            for child in self.album_art.children():
                if isinstance(child, QLabel):
                    child.show()
    
    def set_progress(self, current_seconds, total_seconds, is_playing=True):
        """設置播放進度"""
        if total_seconds > 0:
            progress = int((current_seconds / total_seconds) * 100)
            self.progress_bar.setValue(progress)
        
        # 只在播放狀態改變時才更新 stylesheet（避免頻繁重繪）
        if not hasattr(self, '_last_is_playing') or self._last_is_playing != is_playing:
            self._last_is_playing = is_playing
            if is_playing:
                # 播放中 - 藍色
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
            else:
                # 暫停中 - 黃色
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        background-color: #2d3748;
                        border-radius: 3px;
                        border: none;
                    }
                    QProgressBar::chunk {
                        background-color: #f0ad4e;
                        border-radius: 3px;
                    }
                """)
        
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
        self.set_song(
            track_info.get('name', 'Unknown'), 
            track_info.get('artists', 'Unknown'),
            track_info.get('album', '')
        )
        
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
        從 PIL Image 設置專輯封面（優化版本）
        先在背景縮小圖片，減少主執行緒的處理量
        
        Args:
            pil_image: PIL.Image.Image 物件
        """
        try:
            # 先縮小圖片到需要的大小 (180x180)，減少後續處理量
            # 這比轉換大圖後再縮放效率高很多
            if pil_image.size[0] > 180 or pil_image.size[1] > 180:
                pil_image = pil_image.resize((180, 180), resample=1)  # 1 = BILINEAR
            
            from PIL.ImageQt import ImageQt
            # 轉換 PIL Image 為 QPixmap
            qim = ImageQt(pil_image)
            pixmap = QPixmap.fromImage(qim)
            self.set_album_art(pixmap)
        except Exception as e:
            import logging
            logging.error(f"設置專輯封面失敗: {e}")



class MusicCardWide(QWidget):
    """寬版音樂播放器卡片 - 左側專輯封面，右側資訊"""
    
    request_bind = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(800, 380)
        
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
        
        # Default to Bind page
        self.stack.setCurrentWidget(self.bind_page)
        
        # 網路斷線覆蓋層
        self.offline_overlay = QWidget(self)
        self.offline_overlay.setGeometry(0, 0, 800, 380)
        self.offline_overlay.setStyleSheet("""
            background: rgba(10, 10, 15, 0.9);
            border-radius: 20px;
        """)
        self.offline_overlay.hide()
        
        offline_layout = QVBoxLayout(self.offline_overlay)
        offline_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        offline_icon = QLabel("📡")
        offline_icon.setStyleSheet("font-size: 60px; background: transparent;")
        offline_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        offline_text = QLabel("網路已斷線")
        offline_text.setStyleSheet("color: {T('DANGER')}; font-size: 28px; font-weight: bold; background: transparent;")
        offline_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        offline_desc = QLabel("請檢查網路連線")
        offline_desc.setStyleSheet("color: {T('TEXT_SECONDARY')}; font-size: 16px; background: transparent;")
        offline_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        offline_layout.addWidget(offline_icon)
        offline_layout.addWidget(offline_text)
        offline_layout.addWidget(offline_desc)
    
    def set_offline(self, is_offline):
        """設定離線狀態"""
        if is_offline:
            self.offline_overlay.raise_()
            self.offline_overlay.show()
        else:
            self.offline_overlay.hide()

    def setup_bind_ui(self):
        layout = QHBoxLayout(self.bind_page)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(30)
        
        # 左側大圖標
        icon_label = QLabel("🎵")
        icon_label.setStyleSheet("font-size: 120px; background: transparent;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(200, 200)
        
        # 右側文字和按鈕
        right_widget = QWidget()
        right_widget.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(15)
        
        text_label = QLabel("Spotify 未連結")
        text_label.setStyleSheet("color: {T('TEXT_PRIMARY')}; font-size: 32px; font-weight: bold; background: transparent;")
        
        desc_label = QLabel("請點擊下方按鈕進行綁定，以顯示您的 Spotify 播放資訊")
        desc_label.setStyleSheet("color: {T('TEXT_SECONDARY')}; font-size: 18px; background: transparent;")
        desc_label.setWordWrap(True)
        
        self.bind_btn = QPushButton("綁定 Spotify")
        self.bind_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bind_btn.setFixedSize(250, 60)
        self.bind_btn.setStyleSheet("""
            QPushButton {
                background-color: #1DB954;
                color: {T('TEXT_PRIMARY')};
                border-radius: 30px;
                font-size: 22px;
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
        
        right_layout.addStretch()
        right_layout.addWidget(text_label)
        right_layout.addWidget(desc_label)
        right_layout.addSpacing(20)
        right_layout.addWidget(self.bind_btn)
        right_layout.addStretch()
        
        layout.addWidget(icon_label)
        layout.addWidget(right_widget, 1)

    def setup_player_ui(self):
        layout = QHBoxLayout(self.player_page)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(30)
        
        # === 左側：專輯封面 ===
        album_container = QWidget()
        album_container.setFixedSize(320, 320)
        album_container.setStyleSheet("background: transparent;")
        album_layout = QVBoxLayout(album_container)
        album_layout.setContentsMargins(0, 0, 0, 0)
        album_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.album_art = QLabel()
        self.album_art.setFixedSize(300, 300)
        self.album_art.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #4a5568, stop:0.5 #2d3748, stop:1 #1a202c);
            border-radius: 20px;
            border: 3px solid #4a5568;
        """)
        self.album_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 預設音符圖標
        self.album_icon = QLabel("♪", self.album_art)
        self.album_icon.setStyleSheet("""
            color: {T('PRIMARY')};
            font-size: 120px;
            background: transparent;
        """)
        self.album_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_icon.setGeometry(0, 0, 300, 300)
        
        album_layout.addWidget(self.album_art)
        
        # === 右側：歌曲資訊和進度 ===
        info_container = QWidget()
        info_container.setStyleSheet("background: transparent;")
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 10, 0, 10)
        info_layout.setSpacing(10)
        
        # Now Playing 標題
        title_label = QLabel("Now Playing")
        title_label.setStyleSheet("""
            color: {T('PRIMARY')};
            font-size: 16px;
            font-weight: bold;
            background: transparent;
            letter-spacing: 2px;
        """)
        
        # 歌曲名稱（大字）
        self.song_title = MarqueeLabel("Waiting for music...")
        self.song_title.setStyleSheet("""
            color: {T('TEXT_PRIMARY')};
            font-size: 32px;
            font-weight: bold;
            background: transparent;
        """)
        self.song_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.song_title.setFixedHeight(50)
        
        # 演出者
        self.artist_name = MarqueeLabel("-")
        self.artist_name.setStyleSheet("""
            color: {T('TEXT_PRIMARY')};
            font-size: 22px;
            background: transparent;
        """)
        self.artist_name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.artist_name.setFixedHeight(35)
        
        # 專輯名稱
        self.album_name = MarqueeLabel("-")
        self.album_name.setStyleSheet("""
            color: {T('TEXT_SECONDARY')};
            font-size: 16px;
            background: transparent;
        """)
        self.album_name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.album_name.setFixedHeight(25)
        
        # 進度條區域
        progress_widget = QWidget()
        progress_widget.setStyleSheet("background: transparent;")
        progress_layout = QVBoxLayout(progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(8)
        
        # 進度條
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #2d3748;
                border-radius: 5px;
                border: none;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6af, stop:1 #4a9eff);
                border-radius: 5px;
            }
        """)
        
        # 時間標籤
        time_layout = QHBoxLayout()
        time_layout.setContentsMargins(0, 0, 0, 0)
        
        self.current_time = QLabel("0:00")
        self.current_time.setStyleSheet("""
            color: {T('TEXT_SECONDARY')};
            font-size: 16px;
            background: transparent;
        """)
        
        self.total_time = QLabel("0:00")
        self.total_time.setStyleSheet("""
            color: {T('TEXT_SECONDARY')};
            font-size: 16px;
            background: transparent;
        """)
        
        time_layout.addWidget(self.current_time)
        time_layout.addStretch()
        time_layout.addWidget(self.total_time)
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addLayout(time_layout)
        
        # 組合右側佈局
        info_layout.addWidget(title_label)
        info_layout.addSpacing(15)
        info_layout.addWidget(self.song_title)
        info_layout.addSpacing(5)
        info_layout.addWidget(self.artist_name)
        info_layout.addSpacing(3)
        info_layout.addWidget(self.album_name)
        info_layout.addStretch()
        info_layout.addWidget(progress_widget)
        
        # 組合主佈局
        layout.addWidget(album_container)
        layout.addWidget(info_container, 1)
    
    def show_bind_ui(self):
        self.stack.setCurrentWidget(self.bind_page)
        
    def show_player_ui(self):
        self.stack.setCurrentWidget(self.player_page)

    def set_song(self, title, artist, album=""):
        """設置歌曲信息"""
        self.song_title.setText(title)
        self.artist_name.setText(artist)
        self.album_name.setText(album if album else "")
    
    def set_album_art(self, pixmap):
        """設置專輯封面圖片"""
        if pixmap and not pixmap.isNull():
            # 縮放並裁切圖片
            scaled_pixmap = pixmap.scaled(
                300, 300,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            
            if scaled_pixmap.width() > 300 or scaled_pixmap.height() > 300:
                x = (scaled_pixmap.width() - 300) // 2
                y = (scaled_pixmap.height() - 300) // 2
                scaled_pixmap = scaled_pixmap.copy(x, y, 300, 300)
            
            # 創建圓角遮罩
            rounded_pixmap = QPixmap(300, 300)
            rounded_pixmap.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(rounded_pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            path = QPainterPath()
            path.addRoundedRect(0, 0, 300, 300, 20, 20)
            
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, scaled_pixmap)
            
            pen = QPen(QColor("#4a5568"))
            pen.setWidth(6)
            painter.strokePath(path, pen)
            
            painter.end()
            
            self.album_art.setPixmap(rounded_pixmap)
            self.album_art.setStyleSheet("background: transparent; border: none;")
            self.album_icon.hide()
        else:
            self.album_art.clear()
            self.album_art.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #4a5568, stop:0.5 #2d3748, stop:1 #1a202c);
                border-radius: 20px;
                border: 3px solid #4a5568;
            """)
            self.album_icon.show()
    
    def set_progress(self, current_seconds, total_seconds, is_playing=True):
        """設置播放進度"""
        if total_seconds > 0:
            progress = int((current_seconds / total_seconds) * 100)
            self.progress_bar.setValue(progress)
        
        # 只在播放狀態改變時才更新 stylesheet（避免頻繁重繪）
        if not hasattr(self, '_last_is_playing') or self._last_is_playing != is_playing:
            self._last_is_playing = is_playing
            if is_playing:
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        background-color: #2d3748;
                        border-radius: 5px;
                        border: none;
                    }
                    QProgressBar::chunk {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #6af, stop:1 #4a9eff);
                        border-radius: 5px;
                    }
                """)
            else:
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        background-color: #2d3748;
                        border-radius: 5px;
                        border: none;
                    }
                    QProgressBar::chunk {
                        background-color: #f0ad4e;
                        border-radius: 5px;
                    }
                """)
        
        self.current_time.setText(f"{int(current_seconds//60)}:{int(current_seconds%60):02d}")
        self.total_time.setText(f"{int(total_seconds//60)}:{int(total_seconds%60):02d}")
    
    @perf_track
    def set_album_art_from_pil(self, pil_image):
        """從 PIL Image 設置專輯封面（優化版本）"""
        try:
            # 先縮小圖片到需要的大小 (300x300)，減少後續處理量
            if pil_image.size[0] > 300 or pil_image.size[1] > 300:
                pil_image = pil_image.resize((300, 300), resample=1)  # 1 = BILINEAR
            
            from PIL.ImageQt import ImageQt
            qim = ImageQt(pil_image)
            pixmap = QPixmap.fromImage(qim)
            self.set_album_art(pixmap)
        except Exception as e:
            import logging
            logging.error(f"設置專輯封面失敗: {e}")



