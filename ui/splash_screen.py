import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget


class SplashScreen(QWidget):
    """啟動畫面：全螢幕播放短版影片（約 8 秒）
    
    針對 480x1920 直式螢幕旋轉 90 度使用 (1920x480) 最佳化
    """
    
    finished = pyqtSignal()
    
    def __init__(self, video_path=None):
        if video_path is None:
            video_path = os.path.join(os.path.dirname(__file__), "assets", "video", "Splash_short.mp4")
        super().__init__()
        self.video_path = video_path
        self._finished_emitted = False
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setStyleSheet("background-color: black;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.video_widget = QVideoWidget()
        self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        
        self.player = QMediaPlayer()
        self.player.setVideoOutput(self.video_widget)
        
        self.audio_output = QAudioOutput()
        self.audio_output.setMuted(True)
        self.player.setAudioOutput(self.audio_output)
        
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.player.errorOccurred.connect(self.on_error)
        
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self.on_timeout)
        
        layout.addWidget(self.video_widget)
    
    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self.play_video)
    
    def play_video(self):
        if os.path.exists(self.video_path):
            video_url = QUrl.fromLocalFile(os.path.abspath(self.video_path))
            self.player.setSource(video_url)
            print(f"播放啟動畫面: {self.video_path}")
            self.player.play()
            self.timeout_timer.start(10000)
        else:
            print(f"找不到啟動影片: {self.video_path}")
            QTimer.singleShot(100, self._emit_finished)
    
    def _emit_finished(self):
        if not self._finished_emitted:
            self._finished_emitted = True
            self.timeout_timer.stop()
            self.player.stop()
            self.finished.emit()
    
    def on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            print("啟動畫面播放完成")
            self._emit_finished()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            print("無效的媒體檔案")
            self._emit_finished()
        elif status == QMediaPlayer.MediaStatus.NoMedia:
            pass
    
    def on_error(self, error, error_string):
        print(f"[Splash] 播放錯誤: {error} - {error_string}")
        self._emit_finished()
    
    def on_timeout(self):
        print("[Splash] 超時，強制結束啟動畫面")
        self._emit_finished()
    
    def keyPressEvent(self, a0):
        if a0 and a0.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Space, Qt.Key.Key_Return):
            print("使用者跳過啟動畫面")
            self._emit_finished()
    
    def mousePressEvent(self, event):
        print("使用者跳過啟動畫面")
        self._emit_finished()
