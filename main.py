import sys
import os
import math
import platform
import time
import json
from pathlib import Path
from functools import wraps
from collections import deque

# 抑制 Qt 多媒體 FFmpeg 音訊格式解析警告
os.environ.setdefault('QT_LOGGING_RULES', '*.debug=false;qt.multimedia.ffmpeg=false')

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QHBoxLayout, QVBoxLayout, QGridLayout, QStackedWidget, QProgressBar, QPushButton, QDialog, QGraphicsView, QGraphicsScene, QGraphicsProxyWidget, QMainWindow
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QPropertyAnimation, QEasingCurve, pyqtSignal, QPoint, pyqtSlot, QUrl
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPolygonF, QBrush, QLinearGradient, QRadialGradient, QPainterPath, QPixmap, QMouseEvent, QTransform
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

# Spotify Imports
from spotify_integration import setup_spotify
from spotify_auth import SpotifyAuthManager
from spotify_qr_auth import SpotifyQRAuthDialog


# === 效能監控 ===
class PerformanceMonitor:
    """效能監控器 - 追蹤函數執行時間"""
    
    _instance = None
    SLOW_THRESHOLD_MS = 16  # 超過 16ms (60fps) 視為卡頓
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.enabled = os.environ.get('PERF_MONITOR', '').lower() in ('1', 'true', 'yes')
        self.slow_calls = deque(maxlen=100)  # 最近 100 個慢呼叫
        self.stats = {}  # 函數統計
        self._report_timer = None
        self._frame_start = None  # 幀開始時間
        self._frame_times = deque(maxlen=60)  # 最近 60 幀的時間
    
    def start_frame(self):
        """開始計時一幀"""
        if self.enabled:
            self._frame_start = time.perf_counter()
    
    def end_frame(self, context: str = ""):
        """結束計時一幀"""
        if not self.enabled or self._frame_start is None:
            return
        
        duration_ms = (time.perf_counter() - self._frame_start) * 1000
        self._frame_times.append(duration_ms)
        
        if duration_ms > self.SLOW_THRESHOLD_MS:
            print(f"⚠️ [PERF] 幀延遲: {duration_ms:.1f}ms {context}")
            self.slow_calls.append({
                'func': f"Frame: {context}" if context else "Frame",
                'duration_ms': duration_ms,
                'time': time.time()
            })
    
    def track(self, func_name: str, duration_ms: float):
        """記錄函數執行時間"""
        if not self.enabled:
            return
        
        # 更新統計
        if func_name not in self.stats:
            self.stats[func_name] = {'count': 0, 'total_ms': 0, 'max_ms': 0, 'slow_count': 0}
        
        stat = self.stats[func_name]
        stat['count'] += 1
        stat['total_ms'] += duration_ms
        stat['max_ms'] = max(stat['max_ms'], duration_ms)
        
        # 記錄慢呼叫
        if duration_ms > self.SLOW_THRESHOLD_MS:
            stat['slow_count'] += 1
            self.slow_calls.append({
                'func': func_name,
                'duration_ms': duration_ms,
                'time': time.time()
            })
            print(f"⚠️ [PERF] 慢呼叫: {func_name} 耗時 {duration_ms:.1f}ms")
    
    def report(self):
        """輸出效能報告"""
        if not self.stats:
            print("[PERF] 無統計資料")
            return
        
        print("\n" + "=" * 60)
        print("📊 效能報告")
        print("=" * 60)
        
        # 按慢呼叫次數排序
        sorted_stats = sorted(
            self.stats.items(), 
            key=lambda x: x[1]['slow_count'], 
            reverse=True
        )
        
        print(f"{'函數名稱':<40} {'呼叫次數':>8} {'慢呼叫':>6} {'平均ms':>8} {'最大ms':>8}")
        print("-" * 60)
        
        for func_name, stat in sorted_stats[:20]:  # 前 20 個
            avg_ms = stat['total_ms'] / stat['count'] if stat['count'] > 0 else 0
            print(f"{func_name:<40} {stat['count']:>8} {stat['slow_count']:>6} {avg_ms:>8.1f} {stat['max_ms']:>8.1f}")
        
        print("=" * 60)
        
        # 最近的慢呼叫
        if self.slow_calls:
            print("\n🐢 最近 10 個慢呼叫:")
            for call in list(self.slow_calls)[-10:]:
                print(f"  - {call['func']}: {call['duration_ms']:.1f}ms")
        print()


class JankDetector:
    """卡頓偵測器 - 使用 QTimer 偵測主執行緒阻塞"""
    
    def __init__(self, threshold_ms=50):
        self.threshold_ms = threshold_ms
        self.last_tick = None
        self.enabled = os.environ.get('PERF_MONITOR', '').lower() in ('1', 'true', 'yes')
        self.timer = None
        self.jank_count = 0
        self.start_time = None
    
    def start(self):
        """開始監控"""
        if not self.enabled:
            return
        
        from PyQt6.QtCore import QTimer
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)  # 約 60fps
        self.last_tick = time.perf_counter()
        self.start_time = time.perf_counter()
        print("[JankDetector] 卡頓偵測器已啟動（閾值: 50ms）")
    
    def _tick(self):
        """每 16ms 檢查一次"""
        now = time.perf_counter()
        if self.last_tick is not None:
            elapsed_ms = (now - self.last_tick) * 1000
            if elapsed_ms > self.threshold_ms:
                self.jank_count += 1
                time_since_start = now - self.start_time if self.start_time else 0
                print(f"🔴 [JANK] 主執行緒阻塞 {elapsed_ms:.0f}ms (累計: {self.jank_count}, 啟動後 {time_since_start:.1f}s)")
        self.last_tick = now
    
    def stop(self):
        """停止監控"""
        if self.timer:
            self.timer.stop()
            if self.jank_count > 0:
                print(f"[JankDetector] 總共偵測到 {self.jank_count} 次卡頓")


def perf_track(func):
    """裝飾器 - 追蹤函數執行時間"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        monitor = PerformanceMonitor()
        if not monitor.enabled:
            return func(*args, **kwargs)
        
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            # 獲取類名（如果有）
            if args and hasattr(args[0], '__class__'):
                func_name = f"{args[0].__class__.__name__}.{func.__name__}"
            else:
                func_name = func.__name__
            monitor.track(func_name, duration_ms)
    return wrapper


# === 持久化存儲管理 ===
class OdometerStorage:
    """ODO 和 Trip 資料的持久化存儲（非同步節流寫入）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # 決定存儲路徑
        if platform.system() == 'Windows':
            config_dir = Path(os.environ.get('APPDATA', '.')) / 'QTDashboard'
        else:
            config_dir = Path.home() / '.config' / 'qtdashboard'
        
        config_dir.mkdir(parents=True, exist_ok=True)
        self.data_file = config_dir / 'odometer_data.json'
        
        # 預設資料
        self.data = {
            'odo_total': 0.0,
            'trip1_distance': 0.0,
            'trip2_distance': 0.0,
            'trip1_reset_time': None,
            'trip2_reset_time': None,
            'last_update': None
        }
        
        # 節流控制
        self._dirty = False  # 資料是否有變更
        self._last_save_time = 0  # 上次儲存時間
        self._save_interval = 10.0  # 最少 10 秒儲存一次
        self._save_timer = None  # 延遲儲存計時器
        self._lock = None  # 執行緒鎖（延遲初始化）
        
        # 載入現有資料
        self.load()
    
    def _get_lock(self):
        """延遲初始化執行緒鎖"""
        if self._lock is None:
            import threading
            self._lock = threading.Lock()
        return self._lock
    
    def load(self):
        """從檔案載入資料"""
        try:
            if self.data_file.exists():
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    saved_data = json.load(f)
                    self.data.update(saved_data)
                    print(f"[Storage] 已載入里程資料: ODO={self.data['odo_total']:.1f}km, "
                          f"Trip1={self.data['trip1_distance']:.1f}km, "
                          f"Trip2={self.data['trip2_distance']:.1f}km")
        except Exception as e:
            print(f"[Storage] 載入里程資料失敗: {e}")
    
    def _do_save(self):
        """實際執行儲存（在背景執行緒中）"""
        try:
            with self._get_lock():
                if not self._dirty:
                    return
                self.data['last_update'] = time.time()
                # 寫入臨時檔案再重命名，避免寫入中斷導致檔案損壞
                temp_file = self.data_file.with_suffix('.tmp')
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, indent=2, ensure_ascii=False)
                temp_file.replace(self.data_file)
                self._dirty = False
                self._last_save_time = time.time()
        except Exception as e:
            print(f"[Storage] 儲存里程資料失敗: {e}")
    
    def _schedule_save(self):
        """排程延遲儲存"""
        import threading
        
        now = time.time()
        time_since_last_save = now - self._last_save_time
        
        # 如果距離上次儲存超過間隔，立即在背景儲存
        if time_since_last_save >= self._save_interval:
            threading.Thread(target=self._do_save, daemon=True).start()
        else:
            # 否則設定計時器延遲儲存
            if self._save_timer is None or not self._save_timer.is_alive():
                delay = self._save_interval - time_since_last_save
                self._save_timer = threading.Timer(delay, self._do_save)
                self._save_timer.daemon = True
                self._save_timer.start()
    
    def _mark_dirty(self):
        """標記資料已變更，排程儲存"""
        self._dirty = True
        self._schedule_save()
    
    def save_now(self):
        """立即儲存（程式關閉時使用）"""
        if self._save_timer:
            self._save_timer.cancel()
        self._dirty = True
        self._do_save()
        print("[Storage] 里程資料已儲存")
    
    def update_odo(self, value: float):
        """更新 ODO 總里程"""
        self.data['odo_total'] = value
        self._mark_dirty()
    
    def update_trip1(self, distance: float, reset_time: float = None):
        """更新 Trip 1"""
        self.data['trip1_distance'] = distance
        if reset_time is not None:
            self.data['trip1_reset_time'] = reset_time
        self._mark_dirty()
    
    def update_trip2(self, distance: float, reset_time: float = None):
        """更新 Trip 2"""
        self.data['trip2_distance'] = distance
        if reset_time is not None:
            self.data['trip2_reset_time'] = reset_time
        self._mark_dirty()
    
    def get_odo(self) -> float:
        return self.data.get('odo_total', 0.0)
    
    def get_trip1(self) -> tuple:
        return (self.data.get('trip1_distance', 0.0), 
                self.data.get('trip1_reset_time'))
    
    def get_trip2(self) -> tuple:
        return (self.data.get('trip2_distance', 0.0), 
                self.data.get('trip2_reset_time'))


def is_raspberry_pi():
    """檢測是否在樹莓派上運行"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            return 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo
    except:
        return False


def is_production_environment():
    """
    檢測是否為生產環境（應使用全螢幕）
    
    Returns:
        bool: True = 生產環境（樹莓派或 Linux 嵌入式），False = 開發環境（Mac/Windows）
    """
    # 檢查是否為樹莓派
    if is_raspberry_pi():
        return True
    
    # 檢查環境變數
    if os.environ.get('QTDASHBOARD_FULLSCREEN', '').lower() in ('1', 'true', 'yes'):
        return True
    
    # macOS 和 Windows 視為開發環境
    system = platform.system()
    if system in ('Darwin', 'Windows'):
        return False
    
    # Linux 但非樹莓派，檢查是否有桌面環境
    if system == 'Linux':
        # 如果有 DISPLAY 且不是樹莓派，視為開發環境
        if os.environ.get('DISPLAY'):
            # 檢查是否為嵌入式 Linux（通常沒有完整桌面環境）
            has_desktop = os.environ.get('XDG_CURRENT_DESKTOP') or os.environ.get('DESKTOP_SESSION')
            return not has_desktop  # 無桌面環境 = 生產環境
    
    # 預設為開發環境
    return False


class SplashScreen(QWidget):
    """啟動畫面：全螢幕播放短版影片（約 8 秒）"""
    
    finished = pyqtSignal()  # 播放完成信號
    
    def __init__(self, video_path="Splash_short.mp4"):
        super().__init__()
        self.video_path = video_path
        
        # 設置為全螢幕無邊框
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        # 設置黑色背景
        self.setStyleSheet("background-color: black;")
        
        # 建立佈局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 建立影片播放器
        self.video_widget = QVideoWidget()
        self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        
        self.player = QMediaPlayer()
        self.player.setVideoOutput(self.video_widget)
        
        # 設置靜音
        self.audio_output = QAudioOutput()
        self.audio_output.setMuted(True)
        self.player.setAudioOutput(self.audio_output)
        
        # 連接信號
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        
        layout.addWidget(self.video_widget)
        
    def showEvent(self, event): # type: ignore
        """視窗顯示時自動播放"""
        super().showEvent(event)
        # 延遲一下確保視窗完全顯示
        QTimer.singleShot(100, self.play_video)
    
    def play_video(self):
        """播放影片"""
        if os.path.exists(self.video_path):
            video_url = QUrl.fromLocalFile(os.path.abspath(self.video_path))
            self.player.setSource(video_url)
            print(f"播放啟動畫面: {self.video_path}")
            self.player.play()
        else:
            print(f"找不到啟動影片: {self.video_path}")
            # 如果找不到影片，直接發出完成信號
            QTimer.singleShot(100, self.finished.emit)
    
    def on_media_status_changed(self, status):
        """媒體狀態變更處理"""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            print("啟動畫面播放完成")
            self.finished.emit()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            print("無效的媒體檔案")
            self.finished.emit()
    
    def keyPressEvent(self, a0):  # type: ignore
        """按任意鍵跳過啟動畫面"""
        if a0 and a0.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Space, Qt.Key.Key_Return):
            print("使用者跳過啟動畫面")
            self.player.stop()
            self.finished.emit()
    
    def mousePressEvent(self, event): # pyright: ignore[reportIncompatibleMethodOverride]
        """點擊滑鼠跳過啟動畫面"""
        print("使用者跳過啟動畫面")
        self.player.stop()
        self.finished.emit()


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

class DoorStatusCard(QWidget):
    """門狀態顯示卡片"""
    
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
        
        # 門狀態
        self.door_fl_closed = True  # 左前門 (false=開, true=關)
        self.door_fr_closed = True  # 右前門
        self.door_rl_closed = True  # 左後門
        self.door_rr_closed = True  # 右後門
        self.door_bk_closed = True  # 尾門
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        # 標題
        title_label = QLabel("Door Status")
        title_label.setStyleSheet("""
            color: #6af;
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 圖片顯示區域（使用絕對定位來疊加圖層）
        self.image_container = QWidget()
        self.image_container.setFixedSize(340, 280)
        self.image_container.setStyleSheet("background: transparent;")
        
        # 基底圖層
        self.base_layer = QLabel(self.image_container)
        self.base_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 左前門把手圖層
        self.fl_handle_layer = QLabel(self.image_container)
        self.fl_handle_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 右前門把手圖層
        self.fr_handle_layer = QLabel(self.image_container)
        self.fr_handle_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 左前門開啟圖層
        self.fl_open_layer = QLabel(self.image_container)
        self.fl_open_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 右前門開啟圖層
        self.fr_open_layer = QLabel(self.image_container)
        self.fr_open_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 左後門開啟圖層
        self.rl_open_layer = QLabel(self.image_container)
        self.rl_open_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 右後門開啟圖層
        self.rr_open_layer = QLabel(self.image_container)
        self.rr_open_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 尾門開啟圖層
        self.bk_open_layer = QLabel(self.image_container)
        self.bk_open_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 設置所有圖層的位置和大小，使其疊加
        for layer in [self.base_layer, self.fl_handle_layer, self.fr_handle_layer,
                      self.fl_open_layer, self.fr_open_layer, self.rl_open_layer,
                      self.rr_open_layer, self.bk_open_layer]:
            layer.setGeometry(0, 0, 340, 280)
        
        # 載入圖片
        self.load_images()
        
        # 狀態文字
        self.status_label = QLabel("All Doors Closed")
        self.status_label.setStyleSheet("""
            color: #6f6;
            font-size: 14px;
            font-weight: bold;
            background: transparent;
        """)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 組合佈局
        layout.addWidget(title_label)
        layout.addStretch()
        layout.addWidget(self.image_container, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(self.status_label)
        
        # 初始更新
        self.update_display()
    
    def load_images(self):
        """載入所有門狀態圖片"""
        sprite_path = "carSprite"
        
        # 載入基底圖並縮放保持比例
        base_pixmap = QPixmap(os.path.join(sprite_path, "closed_base.png"))
        if not base_pixmap.isNull():
            scaled_base = base_pixmap.scaled(340, 280, 
                                            Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
            self.base_layer.setPixmap(scaled_base)
        
        # 載入把手圖片
        self.fl_handle_pixmap = QPixmap(os.path.join(sprite_path, "closed_fl_handle.png"))
        self.fr_handle_pixmap = QPixmap(os.path.join(sprite_path, "closed_fr_handle.png"))
        
        # 載入門開啟圖片
        self.fl_open_pixmap = QPixmap(os.path.join(sprite_path, "FL.png"))
        self.fr_open_pixmap = QPixmap(os.path.join(sprite_path, "FR.png"))
        self.rl_open_pixmap = QPixmap(os.path.join(sprite_path, "RL.png"))
        self.rr_open_pixmap = QPixmap(os.path.join(sprite_path, "RR.png"))
        self.bk_open_pixmap = QPixmap(os.path.join(sprite_path, "BK.png"))
    
    def set_door_status(self, door, is_closed):
        """設置門的狀態
        Args:
            door: "FL", "FR", "RL", "RR", "BK"
            is_closed: True=關閉, False=開啟
        """
        door = door.upper()
        if door == "FL":
            self.door_fl_closed = is_closed
        elif door == "FR":
            self.door_fr_closed = is_closed
        elif door == "RL":
            self.door_rl_closed = is_closed
        elif door == "RR":
            self.door_rr_closed = is_closed
        elif door == "BK":
            self.door_bk_closed = is_closed
        
        self.update_display()
    
    def update_display(self):
        """更新顯示 - 根據門的狀態疊加圖層"""
        # 1. 基底圖永遠顯示（已經在 base_layer 上）
        
        # 2. 左前門：關閉時顯示把手，打開時顯示開啟狀態
        if self.door_fl_closed:
            scaled_pixmap = self.fl_handle_pixmap.scaled(340, 280,
                                                         Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation)
            self.fl_handle_layer.setPixmap(scaled_pixmap)
            self.fl_open_layer.clear()
        else:
            self.fl_handle_layer.clear()
            scaled_pixmap = self.fl_open_pixmap.scaled(340, 280,
                                                       Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation)
            self.fl_open_layer.setPixmap(scaled_pixmap)
        
        # 3. 右前門：關閉時顯示把手，打開時顯示開啟狀態
        if self.door_fr_closed:
            scaled_pixmap = self.fr_handle_pixmap.scaled(340, 280,
                                                         Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation)
            self.fr_handle_layer.setPixmap(scaled_pixmap)
            self.fr_open_layer.clear()
        else:
            self.fr_handle_layer.clear()
            scaled_pixmap = self.fr_open_pixmap.scaled(340, 280,
                                                       Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation)
            self.fr_open_layer.setPixmap(scaled_pixmap)
        
        # 4. 左後門：只在打開時顯示
        if not self.door_rl_closed:
            scaled_pixmap = self.rl_open_pixmap.scaled(340, 280,
                                                       Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation)
            self.rl_open_layer.setPixmap(scaled_pixmap)
        else:
            self.rl_open_layer.clear()
        
        # 5. 右後門：只在打開時顯示
        if not self.door_rr_closed:
            scaled_pixmap = self.rr_open_pixmap.scaled(340, 280,
                                                       Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation)
            self.rr_open_layer.setPixmap(scaled_pixmap)
        else:
            self.rr_open_layer.clear()
        
        # 6. 尾門：只在打開時顯示
        if not self.door_bk_closed:
            scaled_pixmap = self.bk_open_pixmap.scaled(340, 280,
                                                       Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation)
            self.bk_open_layer.setPixmap(scaled_pixmap)
        else:
            self.bk_open_layer.clear()
        
        # 更新狀態文字
        open_doors = []
        if not self.door_fl_closed:
            open_doors.append("FL")
        if not self.door_fr_closed:
            open_doors.append("FR")
        if not self.door_rl_closed:
            open_doors.append("RL")
        if not self.door_rr_closed:
            open_doors.append("RR")
        if not self.door_bk_closed:
            open_doors.append("BK")
        
        if open_doors:
            self.status_label.setText(f"Doors Open: {', '.join(open_doors)}")
            self.status_label.setStyleSheet("""
                color: #f66;
                font-size: 14px;
                font-weight: bold;
                background: transparent;
            """)
        else:
            self.status_label.setText("All Doors Closed")
            self.status_label.setStyleSheet("""
                color: #6f6;
                font-size: 14px;
                font-weight: bold;
                background: transparent;
            """)


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
        
        # 標題
        self.title_label = QLabel(self.title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("""
            color: #888;
            font-size: 18px;
            font-weight: bold;
            background: transparent;
            letter-spacing: 2px;
        """)
        
        # 主數值顯示
        self.value_label = QLabel("0")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setStyleSheet("""
            color: #6af;
            font-size: 72px;
            font-weight: bold;
            font-family: 'Arial', 'Helvetica', sans-serif;
            background: transparent;
        """)
        
        # 單位
        self.unit_label = QLabel(self.unit)
        self.unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_label.setStyleSheet("""
            color: #666;
            font-size: 16px;
            background: transparent;
        """)
        
        # 進度條（視覺化）
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
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
        """)
        
        layout.addStretch()
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.unit_label)
        layout.addSpacing(10)
        layout.addWidget(self.progress_bar)
        layout.addStretch()
    
    def set_value(self, value):
        """設定數值"""
        self.current_value = value
        
        # 格式化顯示
        if self.decimal_places == 0:
            display_text = f"{int(value):,}"
        else:
            display_text = f"{value:,.{self.decimal_places}f}"
        
        self.value_label.setText(display_text)
        
        # 更新進度條
        progress = int((value - self.min_val) / (self.max_val - self.min_val) * 100)
        progress = max(0, min(100, progress))
        self.progress_bar.setValue(progress)
        
        # 根據閾值更新顏色
        if self.danger_threshold and value >= self.danger_threshold:
            color = "#f44"  # 紅色
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
            color = "#fa0"  # 橙色
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
            color = "#6af"  # 正常藍色
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
    
    def paintEvent(self, event):
        """繪製卡片背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 繪製圓角矩形背景
        rect = self.rect().adjusted(5, 5, -5, -5)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 20, 20)
        
        # 背景漸層
        gradient = QLinearGradient(0, 0, 0, rect.height())
        gradient.setColorAt(0, QColor(30, 30, 40, 200))
        gradient.setColorAt(1, QColor(20, 20, 30, 200))
        painter.fillPath(path, gradient)
        
        # 邊框
        painter.setPen(QPen(QColor(60, 60, 80), 2))
        painter.drawPath(path)


class QuadGaugeCard(QWidget):
    """
    四宮格儀表卡片 - 顯示轉速/水溫/渦輪負壓/電瓶電壓
    支援點擊放大和焦點選擇機制
    """
    
    # 信號：請求顯示詳細視圖
    detail_requested = pyqtSignal(int)  # 參數: gauge_index (0-3)
    
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
        
        # 儀表數據
        self.gauge_data = [
            {"title": "ENGINE", "unit": "RPM", "value": 0, "min": 0, "max": 8000, 
             "warning": 5500, "danger": 6500, "decimals": 0},
            {"title": "COOLANT", "unit": "°C", "value": 0, "min": 0, "max": 120, 
             "warning": 95, "danger": 105, "decimals": 0},
            {"title": "TURBO", "unit": "bar", "value": -0.7, "min": -1.0, "max": 1.0, 
             "warning": 0.8, "danger": 0.95, "decimals": 2},
            {"title": "BATTERY", "unit": "V", "value": 12.6, "min": 10, "max": 16, 
             "warning": 11.5, "danger": 11.0, "decimals": 1, "warning_below": True},
        ]
        

        
        # 焦點狀態：0=無焦點, 1-4=對應儀表有焦點
        self.focus_index = 0
        
        # 儲存各個儀表格子的 widget
        self.gauge_cells = []
        self.value_labels = []
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化 UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        # 標題
        title_label = QLabel("Engine Monitor")
        title_label.setStyleSheet("""
            color: #6af;
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 四宮格容器
        grid_container = QWidget()
        grid_container.setStyleSheet("background: transparent;")
        grid_layout = QGridLayout(grid_container)
        grid_layout.setContentsMargins(5, 5, 5, 5)
        grid_layout.setSpacing(10)
        
        # 創建四個儀表格子
        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        for i, (row, col) in enumerate(positions):
            cell = self._create_gauge_cell(i)
            self.gauge_cells.append(cell)
            grid_layout.addWidget(cell, row, col)
        
        main_layout.addWidget(grid_container, 1)
        
        # 提示文字
        hint_label = QLabel("點擊進入詳細視圖")
        hint_label.setStyleSheet("""
            color: #555;
            font-size: 11px;
            background: transparent;
        """)
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(hint_label)
    
    def _create_gauge_cell(self, index):
        """創建單個儀表格子"""
        data = self.gauge_data[index]
        
        cell = QWidget()
        cell.setFixedSize(165, 145)
        cell.setStyleSheet("""
            QWidget {
                background: rgba(30, 30, 40, 0.5);
                border-radius: 12px;
                border: 2px solid #2a2a35;
            }
        """)
        
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        
        # 標題
        title = QLabel(data["title"])
        title.setStyleSheet("""
            color: #888;
            font-size: 12px;
            font-weight: bold;
            background: transparent;
            letter-spacing: 1px;
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 數值
        value_label = QLabel(self._format_value(data["value"], data["decimals"]))
        value_label.setStyleSheet("""
            color: #6af;
            font-size: 36px;
            font-weight: bold;
            background: transparent;
        """)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_labels.append(value_label)
        
        # 單位
        unit = QLabel(data["unit"])
        unit.setStyleSheet("""
            color: #666;
            font-size: 11px;
            background: transparent;
        """)
        unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 進度條
        progress = QProgressBar()
        progress.setFixedHeight(6)
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
        
        # 儲存進度條引用以便後續更新
        cell.progress_bar = progress
        
        layout.addWidget(title)
        layout.addWidget(value_label)
        layout.addWidget(unit)
        layout.addWidget(progress)
        
        return cell
    
    def _format_value(self, value, decimals):
        """格式化數值顯示"""
        if decimals == 0:
            return f"{int(value):,}"
        else:
            return f"{value:.{decimals}f}"
    
    def _calc_progress(self, index):
        """計算進度條百分比"""
        data = self.gauge_data[index]
        value = data["value"]
        min_val = data["min"]
        max_val = data["max"]
        progress = int((value - min_val) / (max_val - min_val) * 100)
        return max(0, min(100, progress))
    
    def _get_value_color(self, index):
        """根據數值獲取顏色"""
        data = self.gauge_data[index]
        value = data["value"]
        warning = data.get("warning")
        danger = data.get("danger")
        warning_below = data.get("warning_below", False)
        
        if warning_below:
            # 低於閾值警告（如電瓶電壓）
            if danger is not None and value <= danger:
                return "#f44"
            elif warning is not None and value <= warning:
                return "#fa0"
        else:
            # 高於閾值警告（如轉速、水溫）
            if danger is not None and value >= danger:
                return "#f44"
            elif warning is not None and value >= warning:
                return "#fa0"
        return "#6af"
    
    def set_rpm(self, value):
        """設置轉速"""
        self._set_value(0, value)
    
    def set_coolant_temp(self, value):
        """設置水溫"""
        self._set_value(1, value)
    
    def set_intake_manifold_pressure(self, value):
        """設置進氣歧管壓力 (kPa, 負值為真空/負壓)"""
        self._set_value(2, value)
    
    # 別名，保持相容
    def set_boost(self, value):
        """設置渦輪增壓值 (kPa)"""
        self._set_value(2, value)
    
    def set_turbo(self, value):
        """設置渦輪增壓值 (bar)"""
        self._set_value(2, value)
    
    def set_battery_voltage(self, value):
        """設置電瓶電壓"""
        self._set_value(3, value)
    
    def set_battery(self, value):
        """設置電瓶電壓 (V)"""
        self._set_value(3, value)
    
    def _set_value(self, index, value):
        """設置指定儀表的數值"""
        self.gauge_data[index]["value"] = value
        
        # 更新顯示
        data = self.gauge_data[index]
        self.value_labels[index].setText(self._format_value(value, data["decimals"]))
        
        # 更新顏色
        color = self._get_value_color(index)
        self.value_labels[index].setStyleSheet(f"""
            color: {color};
            font-size: 36px;
            font-weight: bold;
            background: transparent;
        """)
        
        # 更新進度條
        cell = self.gauge_cells[index]
        progress = self._calc_progress(index)
        cell.progress_bar.setValue(progress)
        
        # 更新進度條顏色
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
    
    # === 焦點機制 ===
    def get_focus(self):
        """獲取當前焦點狀態 (0=無, 1-4=對應儀表)"""
        return self.focus_index
    
    def set_focus(self, index):
        """設置焦點 (0=無, 1-4=對應儀表)"""
        self.focus_index = max(0, min(4, index))
        self._update_focus_style()
    
    def next_focus(self):
        """
        切換到下一個焦點
        Returns: True=還在卡片內, False=應該離開到下一張卡片
        """
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
        """清除焦點"""
        self.focus_index = 0
        self._update_focus_style()
    
    def _update_focus_style(self):
        """更新焦點視覺樣式"""
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
        """
        進入當前焦點的詳細視圖
        Returns: True=成功進入, False=沒有焦點
        """
        if self.focus_index > 0:
            self.detail_requested.emit(self.focus_index - 1)
            return True
        return False
    
    def get_gauge_data(self, index):
        """獲取指定儀表的數據"""
        if 0 <= index < 4:
            return self.gauge_data[index].copy()
        return None
    
    # === 觸控/滑鼠事件處理 ===
    def mousePressEvent(self, event):
        """滑鼠/觸控按下 - 記錄起始位置"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.pos()
            self._press_time = time.time()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """滑鼠/觸控放開 - 檢測是否為點擊（非滑動）"""
        if event.button() == Qt.MouseButton.LeftButton and hasattr(self, '_press_pos') and self._press_pos:
            release_pos = event.pos()
            # 計算移動距離
            dx = abs(release_pos.x() - self._press_pos.x())
            dy = abs(release_pos.y() - self._press_pos.y())
            elapsed = time.time() - self._press_time if hasattr(self, '_press_time') else 0
            
            # 只有移動距離小於閾值且時間短才視為點擊（非滑動）
            if dx < 20 and dy < 20 and elapsed < 0.5:
                clicked_index = self._get_cell_at_pos(release_pos)
                if clicked_index >= 0:
                    # 設置焦點並直接進入詳細視圖
                    self.set_focus(clicked_index + 1)
                    print(f"點擊儀表 {clicked_index + 1}：進入詳細視圖")
                    self.detail_requested.emit(clicked_index)
            
            self._press_pos = None
            self._press_time = None
        super().mouseReleaseEvent(event)
    
    def _get_cell_at_pos(self, pos):
        """根據位置獲取儀表格子索引 (0-3)，沒有則返回 -1"""
        for i, cell in enumerate(self.gauge_cells):
            # 將位置轉換為相對於 cell 的座標
            cell_pos = cell.mapFrom(self, pos)
            if cell.rect().contains(cell_pos):
                return i
        return -1


class QuadGaugeDetailView(QWidget):
    """
    四宮格儀表詳細視圖 - 全尺寸顯示單一儀表
    左上角有返回按鈕
    """
    
    # 信號：請求返回
    back_requested = pyqtSignal()
    
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
        
        # 當前顯示的儀表數據
        self.current_data = None
        
        # 滑動檢測
        self._swipe_start_pos = None
        self._swipe_start_time = None
        self._swipe_threshold = 80  # 滑動閾值（像素）
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化 UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        # 頂部：返回按鈕
        top_bar = QWidget()
        top_bar.setStyleSheet("background: transparent;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        self.back_btn = QPushButton("◀ 返回")
        self.back_btn.setFixedSize(80, 35)
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 150, 255, 0.2);
                color: #6af;
                border: 2px solid #6af;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(100, 150, 255, 0.4);
            }
            QPushButton:pressed {
                background-color: rgba(100, 150, 255, 0.6);
            }
        """)
        self.back_btn.clicked.connect(self.back_requested.emit)
        
        top_layout.addWidget(self.back_btn)
        top_layout.addStretch()
        
        main_layout.addWidget(top_bar)
        
        # 標題
        self.title_label = QLabel("ENGINE")
        self.title_label.setStyleSheet("""
            color: #888;
            font-size: 22px;
            font-weight: bold;
            background: transparent;
            letter-spacing: 3px;
        """)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.title_label)
        
        # 數值
        self.value_label = QLabel("0")
        self.value_label.setStyleSheet("""
            color: #6af;
            font-size: 96px;
            font-weight: bold;
            background: transparent;
        """)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.value_label)
        
        # 單位
        self.unit_label = QLabel("RPM")
        self.unit_label.setStyleSheet("""
            color: #666;
            font-size: 20px;
            background: transparent;
        """)
        self.unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.unit_label)
        
        main_layout.addSpacing(10)
        
        # 進度條
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: #2a2a35;
                border-radius: 8px;
                border: 1px solid #3a3a45;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a9eff, stop:1 #6af);
                border-radius: 7px;
            }
        """)
        main_layout.addWidget(self.progress_bar)
        
        # 範圍標示
        range_layout = QHBoxLayout()
        self.min_label = QLabel("0")
        self.min_label.setStyleSheet("color: #555; font-size: 12px; background: transparent;")
        self.max_label = QLabel("8000")
        self.max_label.setStyleSheet("color: #555; font-size: 12px; background: transparent;")
        range_layout.addWidget(self.min_label)
        range_layout.addStretch()
        range_layout.addWidget(self.max_label)
        main_layout.addLayout(range_layout)
        
        main_layout.addStretch()
        
        # 提示文字
        hint_label = QLabel("點擊左上角返回")
        hint_label.setStyleSheet("""
            color: #555;
            font-size: 12px;
            background: transparent;
        """)
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(hint_label)
    
    def set_gauge_data(self, data):
        """設置要顯示的儀表數據"""
        self.current_data = data
        if data:
            self.title_label.setText(data["title"])
            self.unit_label.setText(data["unit"])
            self.min_label.setText(str(data["min"]))
            self.max_label.setText(str(data["max"]))
            self.update_value(data["value"])
    
    def update_value(self, value):
        """更新數值顯示"""
        if not self.current_data:
            return
        
        data = self.current_data
        data["value"] = value
        
        # 格式化顯示
        decimals = data.get("decimals", 0)
        if decimals == 0:
            self.value_label.setText(f"{int(value):,}")
        else:
            self.value_label.setText(f"{value:.{decimals}f}")
        
        # 計算顏色
        color = self._get_value_color()
        self.value_label.setStyleSheet(f"""
            color: {color};
            font-size: 96px;
            font-weight: bold;
            background: transparent;
        """)
        
        # 更新進度條
        progress = int((value - data["min"]) / (data["max"] - data["min"]) * 100)
        progress = max(0, min(100, progress))
        self.progress_bar.setValue(progress)
        
        # 更新進度條顏色
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
        """根據數值獲取顏色"""
        if not self.current_data:
            return "#6af"
        
        data = self.current_data
        value = data["value"]
        warning = data.get("warning")
        danger = data.get("danger")
        warning_below = data.get("warning_below", False)
        
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
        """設置數值（update_value 的別名）"""
        self.update_value(value)
    
    # === 滑動返回功能 ===
    def mousePressEvent(self, event):
        """記錄滑動起始位置"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._swipe_start_pos = event.pos()
            self._swipe_start_time = time.time()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """檢測滑動手勢"""
        if event.button() == Qt.MouseButton.LeftButton and self._swipe_start_pos:
            end_pos = event.pos()
            dx = end_pos.x() - self._swipe_start_pos.x()
            dy = abs(end_pos.y() - self._swipe_start_pos.y())
            elapsed = time.time() - self._swipe_start_time if self._swipe_start_time else 1
            
            # 由左往右滑動：dx > 閾值，且水平滑動為主（dy < dx），且時間短
            if dx > self._swipe_threshold and dy < abs(dx) and elapsed < 0.5:
                print("滑動返回：由左往右滑動")
                self.back_requested.emit()
            
            self._swipe_start_pos = None
            self._swipe_start_time = None
        super().mouseReleaseEvent(event)


class NumericKeypad(QDialog):
    """虛擬數字鍵盤對話框"""
    
    def __init__(self, parent=None, current_value=0.0):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self._result_value: float | None = None
        self.current_input = str(int(current_value)) if current_value > 0 else ""
        
        # 設置固定大小
        self.setFixedSize(400, 500)
        
        # 主容器
        container = QWidget(self)
        container.setGeometry(0, 0, 400, 500)
        container.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a35, stop:1 #1a1a25);
                border-radius: 20px;
                border: 3px solid #6af;
            }
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 標題
        title = QLabel("輸入總里程")
        title.setStyleSheet("""
            color: #6af;
            font-size: 20px;
            font-weight: bold;
            background: transparent;
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 顯示器
        self.display = QLabel(self.current_input if self.current_input else "0")
        self.display.setFixedHeight(60)
        self.display.setStyleSheet("""
            QLabel {
                background: #1a1a25;
                color: white;
                font-size: 36px;
                font-weight: bold;
                border: 2px solid #4a4a55;
                border-radius: 10px;
                padding: 10px;
            }
        """)
        self.display.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        # 單位標籤
        unit_label = QLabel("km")
        unit_label.setStyleSheet("""
            color: #888;
            font-size: 14px;
            background: transparent;
        """)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        # 按鈕網格
        button_grid = QGridLayout()
        button_grid.setSpacing(10)
        
        # 數字按鈕 1-9
        for i in range(9):
            btn = self.create_number_button(str(i + 1))
            row = i // 3
            col = i % 3
            button_grid.addWidget(btn, row, col)
        
        # 第四行：0, BS
        btn_0 = self.create_number_button("0")
        button_grid.addWidget(btn_0, 3, 0, 1, 2)  # 占兩格
        
        btn_bs = self.create_function_button("⌫", self.backspace)
        button_grid.addWidget(btn_bs, 3, 2)
        
        # 操作按鈕行
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(50)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #666;
            }
            QPushButton:pressed {
                background-color: #444;
            }
        """)
        btn_cancel.clicked.connect(self.cancel)
        
        btn_ok = QPushButton("確定")
        btn_ok.setFixedHeight(50)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #6af;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5ad;
            }
            QPushButton:pressed {
                background-color: #49c;
            }
        """)
        btn_ok.clicked.connect(self.confirm)
        
        action_layout.addWidget(btn_cancel)
        action_layout.addWidget(btn_ok)
        
        # 組合佈局
        layout.addWidget(title)
        layout.addWidget(self.display)
        layout.addWidget(unit_label)
        layout.addSpacing(10)
        layout.addLayout(button_grid)
        layout.addLayout(action_layout)
    
    def create_number_button(self, text):
        """創建數字按鈕"""
        btn = QPushButton(text)
        btn.setFixedSize(110, 60)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a45;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a4a55;
            }
            QPushButton:pressed {
                background-color: #2a2a35;
            }
        """)
        btn.clicked.connect(lambda: self.append_digit(text))
        return btn
    
    def create_function_button(self, text, callback):
        """創建功能按鈕"""
        btn = QPushButton(text)
        btn.setFixedSize(110, 60)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #6a5acd;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7a6add;
            }
            QPushButton:pressed {
                background-color: #5a4abd;
            }
        """)
        btn.clicked.connect(callback)
        return btn
    
    def append_digit(self, digit):
        """追加數字"""
        if len(self.current_input) < 7:  # 限制最大7位數（9999999 km）
            self.current_input += digit
            self.display.setText(self.current_input if self.current_input else "0")
    
    def backspace(self):
        """刪除最後一位"""
        if self.current_input:
            self.current_input = self.current_input[:-1]
            self.display.setText(self.current_input if self.current_input else "0")
    
    def confirm(self):
        """確認輸入"""
        try:
            self._result_value = float(self.current_input) if self.current_input else 0.0
        except ValueError:
            self._result_value = 0.0
        self.close()
    
    def cancel(self):
        """取消輸入"""
        self._result_value = None
        self.close()
    
    def get_value(self):
        """獲取輸入值"""
        return self._result_value


class OdometerCard(QWidget):
    """總里程表卡片 (Odometer) - 內嵌虛擬鍵盤"""
    
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
        
        # 總里程數據
        self.total_distance = 0.0  # km
        self.last_sync_time = None
        
        # 當前速度（由 Dashboard 物理心跳驅動里程計算）
        self.current_speed = 0.0
        
        # 輸入狀態
        self.current_input = ""
        self.is_editing = False
        
        # 主佈局使用 StackedWidget 切換顯示/輸入模式
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        
        # === 頁面 1: 顯示模式 ===
        self.display_page = self.create_display_page()
        self.stack.addWidget(self.display_page)
        
        # === 頁面 2: 輸入模式（虛擬鍵盤）===
        self.input_page = self.create_input_page()
        self.stack.addWidget(self.input_page)
        
        # 預設顯示模式
        self.stack.setCurrentWidget(self.display_page)
    
    def create_display_page(self):
        """創建顯示頁面"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # 標題
        title_label = QLabel("Odometer")
        title_label.setStyleSheet("""
            color: #6af;
            font-size: 20px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # ODO 圖標
        icon_label = QLabel("🚗")
        icon_label.setStyleSheet("font-size: 60px; background: transparent;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 總里程顯示區域
        odo_container = QWidget()
        odo_container.setStyleSheet("""
            QWidget {
                background: rgba(30, 30, 40, 0.5);
                border-radius: 15px;
                border: 2px solid #2a2a35;
            }
        """)
        odo_layout = QVBoxLayout(odo_container)
        odo_layout.setContentsMargins(15, 15, 15, 15)
        odo_layout.setSpacing(10)
        
        # 里程顯示
        distance_layout = QHBoxLayout()
        distance_layout.setSpacing(10)
        
        self.odo_distance_label = QLabel("0")
        self.odo_distance_label.setStyleSheet("""
            color: white;
            font-size: 56px;
            font-weight: bold;
            background: transparent;
        """)
        self.odo_distance_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        unit_label = QLabel("km")
        unit_label.setStyleSheet("""
            color: #888;
            font-size: 24px;
            background: transparent;
        """)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        
        distance_layout.addStretch()
        distance_layout.addWidget(self.odo_distance_label)
        distance_layout.addWidget(unit_label)
        distance_layout.addSpacing(10)
        
        # 同步時間顯示
        self.sync_time_label = QLabel("未同步")
        self.sync_time_label.setStyleSheet("""
            color: #666;
            font-size: 12px;
            background: transparent;
        """)
        self.sync_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        odo_layout.addLayout(distance_layout)
        odo_layout.addWidget(self.sync_time_label)
        
        # 同步按鈕
        sync_btn = QPushButton("同步里程")
        sync_btn.setFixedSize(200, 45)
        sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sync_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 150, 255, 0.3);
                color: #6af;
                border: 2px solid #6af;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(100, 150, 255, 0.5);
            }
            QPushButton:pressed {
                background-color: rgba(100, 150, 255, 0.7);
            }
        """)
        sync_btn.clicked.connect(self.show_keypad)
        
        # 組合佈局
        layout.addWidget(title_label)
        layout.addWidget(icon_label)
        layout.addWidget(odo_container)
        layout.addSpacing(10)
        layout.addWidget(sync_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        
        return page
    
    def create_input_page(self):
        """創建輸入頁面（虛擬鍵盤）"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # 標題
        title = QLabel("輸入總里程")
        title.setStyleSheet("""
            color: #6af;
            font-size: 18px;
            font-weight: bold;
            background: transparent;
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 顯示器
        self.input_display = QLabel("0")
        self.input_display.setFixedHeight(50)
        self.input_display.setStyleSheet("""
            QLabel {
                background: #1a1a25;
                color: white;
                font-size: 32px;
                font-weight: bold;
                border: 2px solid #4a4a55;
                border-radius: 8px;
                padding: 5px 10px;
            }
        """)
        self.input_display.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        # 單位標籤
        unit_label = QLabel("km")
        unit_label.setStyleSheet("""
            color: #888;
            font-size: 12px;
            background: transparent;
        """)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        # 按鈕網格
        button_grid = QGridLayout()
        button_grid.setSpacing(8)
        
        # 數字按鈕 1-9
        for i in range(9):
            btn = self.create_number_button(str(i + 1))
            row = i // 3
            col = i % 3
            button_grid.addWidget(btn, row, col)
        
        # 第四行：0, BS
        btn_0 = self.create_number_button("0")
        button_grid.addWidget(btn_0, 3, 0, 1, 2)  # 占兩格
        
        btn_bs = self.create_function_button("⌫", self.backspace)
        button_grid.addWidget(btn_bs, 3, 2)
        
        # 操作按鈕行
        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(40)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #666;
            }
            QPushButton:pressed {
                background-color: #444;
            }
        """)
        btn_cancel.clicked.connect(self.cancel_input)
        
        btn_ok = QPushButton("確定")
        btn_ok.setFixedHeight(40)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #6af;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5ad;
            }
            QPushButton:pressed {
                background-color: #49c;
            }
        """)
        btn_ok.clicked.connect(self.confirm_input)
        
        action_layout.addWidget(btn_cancel)
        action_layout.addWidget(btn_ok)
        
        # 組合佈局
        layout.addWidget(title)
        layout.addWidget(self.input_display)
        layout.addWidget(unit_label)
        layout.addSpacing(5)
        layout.addLayout(button_grid)
        layout.addLayout(action_layout)
        
        return page
    
    def create_number_button(self, text):
        """創建數字按鈕"""
        btn = QPushButton(text)
        btn.setFixedSize(108, 50)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a45;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a4a55;
            }
            QPushButton:pressed {
                background-color: #2a2a35;
            }
        """)
        btn.clicked.connect(lambda: self.append_digit(text))
        return btn
    
    def create_function_button(self, text, callback):
        """創建功能按鈕"""
        btn = QPushButton(text)
        btn.setFixedSize(108, 50)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #6a5acd;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7a6add;
            }
            QPushButton:pressed {
                background-color: #5a4abd;
            }
        """)
        btn.clicked.connect(callback)
        return btn
    
    def show_keypad(self):
        """顯示虛擬鍵盤並禁用滑動"""
        self.current_input = str(int(self.total_distance)) if self.total_distance > 0 else ""
        self.input_display.setText(self.current_input if self.current_input else "0")
        self.is_editing = True
        self.stack.setCurrentWidget(self.input_page)
        
        # 通知 Dashboard 禁用滑動
        dashboard = self.get_dashboard()
        if dashboard:
            dashboard.set_swipe_enabled(False)
    
    def append_digit(self, digit):
        """追加數字"""
        if len(self.current_input) < 7:  # 限制最大7位數
            self.current_input += digit
            self.input_display.setText(self.current_input if self.current_input else "0")
    
    def backspace(self):
        """刪除最後一位"""
        if self.current_input:
            self.current_input = self.current_input[:-1]
            self.input_display.setText(self.current_input if self.current_input else "0")
    
    def confirm_input(self):
        """確認輸入"""
        try:
            self.total_distance = float(self.current_input) if self.current_input else 0.0
        except ValueError:
            self.total_distance = 0.0
        
        self.odo_distance_label.setText(f"{int(self.total_distance)}")
        self.last_sync_time = time.time()
        self.update_sync_time_display()
        print(f"里程表已同步: {int(self.total_distance)} km")
        
        self.hide_keypad()
    
    def cancel_input(self):
        """取消輸入"""
        self.hide_keypad()
    
    def hide_keypad(self):
        """隱藏虛擬鍵盤並恢復滑動"""
        self.is_editing = False
        self.stack.setCurrentWidget(self.display_page)
        
        # 通知 Dashboard 恢復滑動
        dashboard = self.get_dashboard()
        if dashboard:
            dashboard.set_swipe_enabled(True)
    
    def get_dashboard(self):
        """獲取 Dashboard 實例"""
        parent = self.parent()
        while parent:
            if isinstance(parent, Dashboard):
                return parent
            parent = parent.parent()
        return None
    
    def add_distance(self, distance_km):
        """由 Dashboard 物理心跳呼叫，累加里程"""
        self.total_distance += distance_km
        # 更新顯示（不帶小數點，模擬真實里程表）
        self.odo_distance_label.setText(f"{int(self.total_distance)}")
    
    def update_sync_time_display(self):
        """更新同步時間顯示"""
        from datetime import datetime
        
        if self.last_sync_time:
            sync_dt = datetime.fromtimestamp(self.last_sync_time)
            time_str = sync_dt.strftime("%Y-%m-%d %H:%M")
            self.sync_time_label.setText(f"上次同步: {time_str}")
        else:
            self.sync_time_label.setText("未同步")


class OdometerCardWide(QWidget):
    """總里程表卡片（寬版 800x380）- 顯示模式 / 輸入模式切換"""
    
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
        
        # 持久化存儲
        self.storage = OdometerStorage()
        
        # 總里程數據（從存儲載入）
        self.total_distance = self.storage.get_odo()
        self.last_sync_time = None
        
        # 輸入狀態
        self.current_input = ""
        self.is_editing = False
        
        # 主佈局使用 StackedWidget 切換模式
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        
        # === 頁面 1: 顯示模式 ===
        self.display_page = self._create_display_page()
        self.stack.addWidget(self.display_page)
        
        # === 頁面 2: 輸入模式（虛擬鍵盤）===
        self.input_page = self._create_input_page()
        self.stack.addWidget(self.input_page)
        
        # 預設顯示模式
        self.stack.setCurrentWidget(self.display_page)
        
        # 初始化顯示（載入的值）
        self.odo_distance_label.setText(f"{int(self.total_distance)}")
    
    def _create_display_page(self):
        """創建顯示頁面 - 水平佈局"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(40)
        
        # === 左側：圖示 ===
        icon_container = QWidget()
        icon_container.setFixedWidth(100)
        icon_container.setStyleSheet("background: transparent;")
        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        
        icon_label = QLabel("🚗")
        icon_label.setStyleSheet("font-size: 48px; background: transparent;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_layout.addStretch()
        icon_layout.addWidget(icon_label)
        icon_layout.addStretch()
        
        # === 中央：里程顯示 ===
        center_container = QWidget()
        center_container.setStyleSheet("background: transparent;")
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)
        
        # 標題
        title_label = QLabel("Odometer")
        title_label.setStyleSheet("""
            color: #6af;
            font-size: 28px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 里程數字 + 單位
        distance_widget = QWidget()
        distance_widget.setStyleSheet("""
            background: rgba(30, 30, 40, 0.5);
            border-radius: 15px;
            border: 2px solid #2a2a35;
        """)
        distance_layout = QHBoxLayout(distance_widget)
        distance_layout.setContentsMargins(20, 20, 20, 20)
        distance_layout.setSpacing(8)
        
        self.odo_distance_label = QLabel("0")
        self.odo_distance_label.setStyleSheet("""
            color: white;
            font-size: 56px;
            font-weight: bold;
            background: transparent;
        """)
        self.odo_distance_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        unit_label = QLabel("km")
        unit_label.setStyleSheet("""
            color: #888;
            font-size: 24px;
            background: transparent;
        """)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        
        distance_layout.addStretch()
        distance_layout.addWidget(self.odo_distance_label)
        distance_layout.addWidget(unit_label)
        distance_layout.addStretch()
        
        # 同步時間
        self.sync_time_label = QLabel("未同步")
        self.sync_time_label.setStyleSheet("""
            color: #666;
            font-size: 16px;
            background: transparent;
        """)
        self.sync_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        center_layout.addStretch()
        center_layout.addWidget(title_label)
        center_layout.addSpacing(10)
        center_layout.addWidget(distance_widget)
        center_layout.addWidget(self.sync_time_label)
        center_layout.addStretch()
        
        # === 右側：同步按鈕 ===
        right_container = QWidget()
        right_container.setFixedWidth(120)
        right_container.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        sync_btn = QPushButton("同步\n里程")
        sync_btn.setFixedSize(90, 90)
        sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sync_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 150, 255, 0.2);
                color: #6af;
                border: 3px solid #6af;
                border-radius: 45px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(100, 150, 255, 0.4);
            }
            QPushButton:pressed {
                background-color: rgba(100, 150, 255, 0.6);
            }
        """)
        sync_btn.clicked.connect(self._show_keypad)
        
        right_layout.addStretch()
        right_layout.addWidget(sync_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        right_layout.addStretch()
        
        # 組合佈局
        layout.addWidget(icon_container)
        layout.addWidget(center_container, 1)
        layout.addWidget(right_container)
        
        return page
    
    def _create_input_page(self):
        """創建輸入頁面（虛擬鍵盤）- 左右並排"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(30)
        
        # === 左側：當前里程 + 輸入預覽 ===
        left_panel = QWidget()
        left_panel.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(15)
        
        # 標題
        title_label = QLabel("同步里程")
        title_label.setStyleSheet("""
            color: #6af;
            font-size: 28px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 當前里程顯示
        current_container = QWidget()
        current_container.setStyleSheet("""
            QWidget {
                background: rgba(30, 30, 40, 0.5);
                border-radius: 15px;
                border: 2px solid #2a2a35;
            }
        """)
        current_layout = QVBoxLayout(current_container)
        current_layout.setContentsMargins(20, 20, 20, 20)
        current_layout.setSpacing(10)
        
        current_title = QLabel("目前里程")
        current_title.setStyleSheet("color: #888; font-size: 16px; background: transparent;")
        current_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.current_odo_label = QLabel("0 km")
        self.current_odo_label.setStyleSheet("""
            color: #666;
            font-size: 36px;
            font-weight: bold;
            background: transparent;
        """)
        self.current_odo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        current_layout.addWidget(current_title)
        current_layout.addWidget(self.current_odo_label)
        
        # 新里程輸入預覽
        new_container = QWidget()
        new_container.setStyleSheet("""
            QWidget {
                background: rgba(100, 150, 255, 0.1);
                border-radius: 15px;
                border: 2px solid #6af;
            }
        """)
        new_layout = QVBoxLayout(new_container)
        new_layout.setContentsMargins(20, 20, 20, 20)
        new_layout.setSpacing(10)
        
        new_title = QLabel("新里程")
        new_title.setStyleSheet("color: #6af; font-size: 16px; background: transparent;")
        new_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.input_display = QLabel("_ _ _ _ _ _")
        self.input_display.setStyleSheet("""
            color: white;
            font-size: 42px;
            font-weight: bold;
            background: transparent;
        """)
        self.input_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        new_layout.addWidget(new_title)
        new_layout.addWidget(self.input_display)
        
        left_layout.addWidget(title_label)
        left_layout.addWidget(current_container, 1)
        left_layout.addWidget(new_container, 1)
        
        # 中央分隔線
        separator = QWidget()
        separator.setFixedWidth(2)
        separator.setStyleSheet("background: #333;")
        
        # === 右側：虛擬鍵盤 ===
        right_panel = QWidget()
        right_panel.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(10)
        
        # 按鈕網格
        button_grid = QGridLayout()
        button_grid.setSpacing(10)
        
        # 數字按鈕 1-9
        for i in range(9):
            btn = self._create_number_button(str(i + 1))
            row = i // 3
            col = i % 3
            button_grid.addWidget(btn, row, col)
        
        # 第四行：清除, 0, 退格
        btn_clear = self._create_function_button("C", self._clear_input, "#cc5555")
        button_grid.addWidget(btn_clear, 3, 0)
        
        btn_0 = self._create_number_button("0")
        button_grid.addWidget(btn_0, 3, 1)
        
        btn_bs = self._create_function_button("⌫", self._backspace, "#555555")
        button_grid.addWidget(btn_bs, 3, 2)
        
        # 操作按鈕行
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(50)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #666; }
            QPushButton:pressed { background-color: #444; }
        """)
        btn_cancel.clicked.connect(self._cancel_input)
        
        btn_ok = QPushButton("確定")
        btn_ok.setFixedHeight(50)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #55aa55;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #66bb66; }
            QPushButton:pressed { background-color: #449944; }
        """)
        btn_ok.clicked.connect(self._confirm_input)
        
        action_layout.addWidget(btn_cancel)
        action_layout.addWidget(btn_ok)
        
        right_layout.addLayout(button_grid)
        right_layout.addLayout(action_layout)
        
        layout.addWidget(left_panel, 1)
        layout.addWidget(separator)
        layout.addWidget(right_panel, 1)
        
        return page
    
    def _create_number_button(self, text):
        """創建數字按鈕"""
        btn = QPushButton(text)
        btn.setFixedSize(95, 55)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a45;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 26px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4a4a55; }
            QPushButton:pressed { background-color: #2a2a35; }
        """)
        btn.clicked.connect(lambda: self._append_digit(text))
        return btn
    
    def _create_function_button(self, text, callback, color="#6a5acd"):
        """創建功能按鈕"""
        btn = QPushButton(text)
        btn.setFixedSize(95, 55)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 22px;
                font-weight: bold;
            }}
            QPushButton:hover {{ opacity: 0.8; }}
            QPushButton:pressed {{ opacity: 0.6; }}
        """)
        btn.clicked.connect(callback)
        return btn
    
    def _show_keypad(self):
        """顯示虛擬鍵盤"""
        self.current_input = ""
        self.current_odo_label.setText(f"{int(self.total_distance)} km")
        self._update_input_display()
        self.is_editing = True
        self.stack.setCurrentWidget(self.input_page)
        
        # 通知 Dashboard 禁用滑動
        dashboard = self._get_dashboard()
        if dashboard:
            dashboard.set_swipe_enabled(False)
    
    def _hide_keypad(self):
        """隱藏虛擬鍵盤"""
        self.is_editing = False
        self.stack.setCurrentWidget(self.display_page)
        
        # 通知 Dashboard 恢復滑動
        dashboard = self._get_dashboard()
        if dashboard:
            dashboard.set_swipe_enabled(True)
    
    def _append_digit(self, digit):
        """追加數字"""
        if len(self.current_input) < 7:
            self.current_input += digit
            self._update_input_display()
    
    def _backspace(self):
        """刪除最後一位"""
        if self.current_input:
            self.current_input = self.current_input[:-1]
            self._update_input_display()
    
    def _clear_input(self):
        """清除輸入"""
        self.current_input = ""
        self._update_input_display()
    
    def _update_input_display(self):
        """更新輸入顯示"""
        if self.current_input:
            self.input_display.setText(f"{self.current_input} km")
        else:
            self.input_display.setText("_ _ _ _ _ _")
    
    def _confirm_input(self):
        """確認輸入"""
        if self.current_input:
            try:
                self.total_distance = float(self.current_input)
            except ValueError:
                self.total_distance = 0.0
            
            self.odo_distance_label.setText(f"{int(self.total_distance)}")
            self.last_sync_time = time.time()
            self._update_sync_time_display()
            print(f"里程表已同步: {int(self.total_distance)} km")
        
        self._hide_keypad()
    
    def _cancel_input(self):
        """取消輸入"""
        self._hide_keypad()
    
    def _get_dashboard(self):
        """獲取 Dashboard 實例"""
        parent = self.parent()
        while parent:
            if isinstance(parent, Dashboard):
                return parent
            parent = parent.parent()
        return None
    
    def add_distance(self, distance_km):
        """由 Dashboard 物理心跳呼叫，累加里程"""
        self.total_distance += distance_km
        self.odo_distance_label.setText(f"{int(self.total_distance)}")
        # 每累加一次就儲存（實際上 Dashboard 每秒呼叫一次）
        self.storage.update_odo(self.total_distance)
    
    def _update_sync_time_display(self):
        """更新同步時間顯示"""
        from datetime import datetime
        
        if self.last_sync_time:
            sync_dt = datetime.fromtimestamp(self.last_sync_time)
            time_str = sync_dt.strftime("%Y-%m-%d %H:%M")
            self.sync_time_label.setText(f"同步: {time_str}")
        else:
            self.sync_time_label.setText("未同步")


class TripCard(QWidget):
    """Trip 里程卡片 - 顯示 Trip 1 和 Trip 2 的里程數、reset按鈕和reset時間"""
    
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
        
        # Trip 數據
        self.trip1_distance = 0.0  # km
        self.trip2_distance = 0.0  # km
        self.trip1_reset_time = None
        self.trip2_reset_time = None
        
        # 當前速度（由 Dashboard 物理心跳驅動里程計算）
        self.current_speed = 0.0
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 標題
        title_label = QLabel("Trip Computer")
        title_label.setStyleSheet("""
            color: #6af;
            font-size: 18px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # === Trip 1 區域 ===
        trip1_container = self.create_trip_widget(
            "Trip 1", 
            is_trip1=True
        )
        
        # === Trip 2 區域 ===
        trip2_container = self.create_trip_widget(
            "Trip 2", 
            is_trip1=False
        )
        
        # 組合佈局
        layout.addWidget(title_label)
        layout.addSpacing(10)
        layout.addWidget(trip1_container)
        layout.addSpacing(5)
        layout.addWidget(trip2_container)
        layout.addStretch()
    
    def create_trip_widget(self, title, is_trip1=True):
        """創建單個Trip顯示區域"""
        container = QWidget()
        container.setFixedHeight(140)
        container.setStyleSheet("""
            QWidget {
                background: rgba(30, 30, 40, 0.5);
                border-radius: 15px;
                border: 2px solid #2a2a35;
            }
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(5)
        
        # 標題和Reset按鈕行
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        
        trip_title = QLabel(title)
        trip_title.setStyleSheet("""
            color: #6af;
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        
        reset_btn = QPushButton("Reset")
        reset_btn.setFixedSize(70, 28)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 150, 255, 0.3);
                color: #6af;
                border: 1px solid #6af;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(100, 150, 255, 0.5);
            }
            QPushButton:pressed {
                background-color: rgba(100, 150, 255, 0.7);
            }
        """)
        
        if is_trip1:
            reset_btn.clicked.connect(self.reset_trip1)
        else:
            reset_btn.clicked.connect(self.reset_trip2)
        
        header_layout.addWidget(trip_title)
        header_layout.addStretch()
        header_layout.addWidget(reset_btn)
        
        # 里程顯示
        distance_layout = QHBoxLayout()
        distance_layout.setSpacing(5)
        
        if is_trip1:
            self.trip1_distance_label = QLabel("0.0")
            distance_label = self.trip1_distance_label
        else:
            self.trip2_distance_label = QLabel("0.0")
            distance_label = self.trip2_distance_label
            
        distance_label.setStyleSheet("""
            color: white;
            font-size: 48px;
            font-weight: bold;
            background: transparent;
        """)
        distance_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        unit_label = QLabel("km")
        unit_label.setStyleSheet("""
            color: #888;
            font-size: 20px;
            background: transparent;
        """)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        
        distance_layout.addStretch()
        distance_layout.addWidget(distance_label)
        distance_layout.addWidget(unit_label)
        distance_layout.addSpacing(10)
        
        # Reset時間顯示
        if is_trip1:
            self.trip1_reset_label = QLabel("Never reset")
            reset_time_label = self.trip1_reset_label
        else:
            self.trip2_reset_label = QLabel("Never reset")
            reset_time_label = self.trip2_reset_label
            
        reset_time_label.setStyleSheet("""
            color: #666;
            font-size: 24px;
            background: transparent;
        """)
        reset_time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        # 組合佈局
        layout.addLayout(header_layout)
        layout.addSpacing(5)
        layout.addLayout(distance_layout)
        layout.addWidget(reset_time_label)
        
        return container
    
    def add_distance(self, distance_km):
        """由 Dashboard 物理心跳呼叫，累加里程"""
        self.trip1_distance += distance_km
        self.trip2_distance += distance_km
        
        # 更新顯示
        self.trip1_distance_label.setText(f"{self.trip1_distance:.1f}")
        self.trip2_distance_label.setText(f"{self.trip2_distance:.1f}")
    
    def reset_trip1(self):
        """重置 Trip 1"""
        self.trip1_distance = 0.0
        self.trip1_distance_label.setText("0.0")
        self.trip1_reset_time = time.time()
        self.update_reset_time_display(True)
        print("Trip 1 已重置")
    
    def reset_trip2(self):
        """重置 Trip 2"""
        self.trip2_distance = 0.0
        self.trip2_distance_label.setText("0.0")
        self.trip2_reset_time = time.time()
        self.update_reset_time_display(False)
        print("Trip 2 已重置")
    
    def update_reset_time_display(self, is_trip1=True):
        """更新reset時間顯示"""
        from datetime import datetime
        
        if is_trip1:
            if self.trip1_reset_time:
                reset_dt = datetime.fromtimestamp(self.trip1_reset_time)
                time_str = reset_dt.strftime("%Y-%m-%d %H:%M")
                self.trip1_reset_label.setText(f"Reset: {time_str}")
            else:
                self.trip1_reset_label.setText("Never reset")
        else:
            if self.trip2_reset_time:
                reset_dt = datetime.fromtimestamp(self.trip2_reset_time)
                time_str = reset_dt.strftime("%Y-%m-%d %H:%M")
                self.trip2_reset_label.setText(f"Reset: {time_str}")
            else:
                self.trip2_reset_label.setText("Never reset")


class TripCardWide(QWidget):
    """Trip 里程卡片（寬版 800x380）- 左右並排顯示 Trip 1 和 Trip 2，支援焦點選擇"""
    
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
        
        # 持久化存儲
        self.storage = OdometerStorage()
        
        # Trip 數據（從存儲載入）
        self.trip1_distance, self.trip1_reset_time = self.storage.get_trip1()
        self.trip2_distance, self.trip2_reset_time = self.storage.get_trip2()
        
        # 焦點狀態：0=無焦點, 1=Trip1, 2=Trip2
        self.focus_index = 0
        
        # Main layout - 水平排列
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(30)
        
        # === 左側 Trip 1 ===
        self.trip1_panel = self._create_trip_panel("Trip 1", is_trip1=True)
        
        # 中央分隔線
        separator = QWidget()
        separator.setFixedWidth(2)
        separator.setStyleSheet("background: #333;")
        
        # === 右側 Trip 2 ===
        self.trip2_panel = self._create_trip_panel("Trip 2", is_trip1=False)
        
        main_layout.addWidget(self.trip1_panel, 1)
        main_layout.addWidget(separator)
        main_layout.addWidget(self.trip2_panel, 1)
        
        # 初始化顯示（載入的值）
        self.trip1_distance_label.setText(f"{self.trip1_distance:.1f}")
        self.trip2_distance_label.setText(f"{self.trip2_distance:.1f}")
        self._update_reset_time_display(True)
        self._update_reset_time_display(False)
    
    def _create_trip_panel(self, title, is_trip1=True):
        """創建單個 Trip 面板"""
        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # 標題行（標題 + Reset 按鈕）
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            color: #6af;
            font-size: 28px;
            font-weight: bold;
            background: transparent;
        """)
        
        reset_btn = QPushButton("Reset")
        reset_btn.setFixedSize(80, 36)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 150, 255, 0.3);
                color: #6af;
                border: 1px solid #6af;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(100, 150, 255, 0.5);
            }
            QPushButton:pressed {
                background-color: rgba(100, 150, 255, 0.7);
            }
        """)
        
        if is_trip1:
            reset_btn.clicked.connect(self.reset_trip1)
        else:
            reset_btn.clicked.connect(self.reset_trip2)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(reset_btn)
        
        # 里程顯示區域（作為焦點容器）
        distance_container = QWidget()
        if is_trip1:
            self.trip1_container = distance_container
        else:
            self.trip2_container = distance_container
        distance_container.setStyleSheet("""
            background: rgba(30, 30, 40, 0.5);
            border-radius: 15px;
            border: 2px solid #2a2a35;
        """)
        distance_layout = QVBoxLayout(distance_container)
        distance_layout.setContentsMargins(20, 25, 20, 25)
        distance_layout.setSpacing(10)
        
        # 里程數字 + 單位
        value_layout = QHBoxLayout()
        value_layout.setSpacing(8)
        
        if is_trip1:
            self.trip1_distance_label = QLabel("0.0")
            distance_label = self.trip1_distance_label
        else:
            self.trip2_distance_label = QLabel("0.0")
            distance_label = self.trip2_distance_label
        
        distance_label.setStyleSheet("""
            color: white;
            font-size: 72px;
            font-weight: bold;
            background: transparent;
        """)
        distance_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        unit_label = QLabel("km")
        unit_label.setStyleSheet("""
            color: #888;
            font-size: 28px;
            background: transparent;
        """)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        
        value_layout.addStretch()
        value_layout.addWidget(distance_label)
        value_layout.addWidget(unit_label)
        value_layout.addSpacing(10)
        
        # Reset 時間
        if is_trip1:
            self.trip1_reset_label = QLabel("Never reset")
            reset_time_label = self.trip1_reset_label
        else:
            self.trip2_reset_label = QLabel("Never reset")
            reset_time_label = self.trip2_reset_label
        
        reset_time_label.setStyleSheet("""
            color: #666;
            font-size: 24px;
            background: transparent;
        """)
        reset_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        distance_layout.addLayout(value_layout)
        distance_layout.addWidget(reset_time_label)
        
        # 組合佈局
        layout.addLayout(header_layout)
        layout.addWidget(distance_container, 1)
        
        return panel
    
    def add_distance(self, distance_km):
        """由 Dashboard 物理心跳呼叫，累加里程"""
        self.trip1_distance += distance_km
        self.trip2_distance += distance_km
        
        # 更新顯示
        self.trip1_distance_label.setText(f"{self.trip1_distance:.1f}")
        self.trip2_distance_label.setText(f"{self.trip2_distance:.1f}")
        
        # 儲存到檔案
        self.storage.update_trip1(self.trip1_distance)
        self.storage.update_trip2(self.trip2_distance)
    
    def reset_trip1(self):
        """重置 Trip 1"""
        self.trip1_distance = 0.0
        self.trip1_distance_label.setText("0.0")
        self.trip1_reset_time = time.time()
        self._update_reset_time_display(True)
        # 儲存到檔案（包含 reset 時間）
        self.storage.update_trip1(self.trip1_distance, self.trip1_reset_time)
        print("Trip 1 已重置")
    
    def reset_trip2(self):
        """重置 Trip 2"""
        self.trip2_distance = 0.0
        self.trip2_distance_label.setText("0.0")
        self.trip2_reset_time = time.time()
        self._update_reset_time_display(False)
        # 儲存到檔案（包含 reset 時間）
        self.storage.update_trip2(self.trip2_distance, self.trip2_reset_time)
        print("Trip 2 已重置")
    
    def _update_reset_time_display(self, is_trip1=True):
        """更新 reset 時間顯示"""
        from datetime import datetime
        
        if is_trip1:
            if self.trip1_reset_time:
                reset_dt = datetime.fromtimestamp(self.trip1_reset_time)
                time_str = reset_dt.strftime("%Y-%m-%d %H:%M")
                self.trip1_reset_label.setText(f"Reset: {time_str}")
            else:
                self.trip1_reset_label.setText("Never reset")
        else:
            if self.trip2_reset_time:
                reset_dt = datetime.fromtimestamp(self.trip2_reset_time)
                time_str = reset_dt.strftime("%Y-%m-%d %H:%M")
                self.trip2_reset_label.setText(f"Reset: {time_str}")
            else:
                self.trip2_reset_label.setText("Never reset")
    
    def set_focus(self, focus_index):
        """
        設置焦點狀態
        
        Args:
            focus_index: 0=無焦點, 1=Trip1有焦點, 2=Trip2有焦點
        """
        self.focus_index = focus_index
        self._update_focus_style()
    
    def get_focus(self):
        """獲取當前焦點狀態"""
        return self.focus_index
    
    def next_focus(self):
        """
        切換到下一個焦點
        
        Returns:
            bool: True=還在 Trip 卡片內, False=應該離開到下一張卡片
        """
        if self.focus_index == 0:
            # 無焦點 -> Trip 1
            self.focus_index = 1
            self._update_focus_style()
            return True
        elif self.focus_index == 1:
            # Trip 1 -> Trip 2
            self.focus_index = 2
            self._update_focus_style()
            return True
        else:
            # Trip 2 -> 離開（清除焦點）
            self.focus_index = 0
            self._update_focus_style()
            return False
    
    def clear_focus(self):
        """清除焦點"""
        self.focus_index = 0
        self._update_focus_style()
    
    def reset_focused_trip(self):
        """
        重置當前有焦點的 Trip
        
        Returns:
            bool: True=成功重置, False=沒有焦點
        """
        if self.focus_index == 1:
            self.reset_trip1()
            return True
        elif self.focus_index == 2:
            self.reset_trip2()
            return True
        return False
    
    def _update_focus_style(self):
        """更新焦點視覺樣式"""
        # Trip 1 容器樣式
        if self.focus_index == 1:
            self.trip1_container.setStyleSheet("""
                background: rgba(100, 170, 255, 0.15);
                border-radius: 15px;
                border: 3px solid #6af;
            """)
        else:
            self.trip1_container.setStyleSheet("""
                background: rgba(30, 30, 40, 0.5);
                border-radius: 15px;
                border: 2px solid #2a2a35;
            """)
        
        # Trip 2 容器樣式
        if self.focus_index == 2:
            self.trip2_container.setStyleSheet("""
                background: rgba(100, 170, 255, 0.15);
                border-radius: 15px;
                border: 3px solid #6af;
            """)
        else:
            self.trip2_container.setStyleSheet("""
                background: rgba(30, 30, 40, 0.5);
                border-radius: 15px;
                border: 2px solid #2a2a35;
            """)


class MarqueeLabel(QLabel):
    """跑馬燈標籤：當文字過長時自動捲動，全部回到定點後暫停再重新開始"""
    # 類別變數：用於同步所有 MarqueeLabel 實例
    _global_pause_counter = 0
    _global_pause_threshold = 166  # 約 5 秒 (166 * 30ms ≈ 5000ms)
    _instances = []  # 追蹤所有實例
    _waiting_for_sync = False  # 是否在等待其他標籤回到起點
    
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._scroll_pos = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timeout)
        self._timer.setInterval(30)
        self._is_scrollable = False
        self._at_home = True  # 是否在起始位置
        self._is_active = False  # 是否處於活躍狀態（可見且應該運作）
        
        # 註冊實例
        MarqueeLabel._instances.append(self)

    def setText(self, text): # type: ignore
        if text == self.text():
            return
        super().setText(text)
        self._scroll_pos = 0
        self._at_home = True
        self._check_scrollable()
        
        # 只有在活躍狀態時才啟動計時器和設置暫停
        if self._is_active:
            MarqueeLabel._waiting_for_sync = False
            MarqueeLabel._global_pause_counter = MarqueeLabel._global_pause_threshold
            if not self._timer.isActive():
                self._timer.start()
        
        self.update()
    
    def showEvent(self, event):  # type: ignore
        """當標籤變為可見時"""
        super().showEvent(event)
        self._activate()
    
    def hideEvent(self, event):  # type: ignore
        """當標籤被隱藏時"""
        super().hideEvent(event)
        self._deactivate()
    
    def _activate(self):
        """啟動跑馬燈"""
        if self._is_active:
            return
        self._is_active = True
        # 重置到起始位置
        self._scroll_pos = 0
        self._at_home = True
        self._check_scrollable()
        # 重置全域暫停計數器，讓文字先暫停一下再開始捲動
        MarqueeLabel._global_pause_counter = MarqueeLabel._global_pause_threshold
        MarqueeLabel._waiting_for_sync = False
        # 啟動計時器
        if self._is_scrollable and not self._timer.isActive():
            self._timer.start()
        self.update()
    
    def _deactivate(self):
        """停止跑馬燈"""
        if not self._is_active:
            return
        self._is_active = False
        # 停止計時器
        if self._timer.isActive():
            self._timer.stop()
        # 重置位置
        self._scroll_pos = 0
        self._at_home = True

    def _check_scrollable(self):
        """檢查文字是否需要捲動"""
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self.text())
        self._is_scrollable = text_width > self.width()
        
    def paintEvent(self, a0):
        painter = QPainter(self)
        
        # 獲取樣式表設定的顏色
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self.text())
        
        # 如果文字寬度小於元件寬度，使用設定的對齊方式顯示且不捲動
        if text_width <= self.width():
            if self._timer.isActive():
                self._timer.stop()
            self._is_scrollable = False
            # 使用元件設定的對齊方式
            painter.drawText(self.rect(), int(self.alignment()), self.text())
            return

        # 標記為需要捲動
        self._is_scrollable = True
        
        # 只有在活躍狀態時才啟動計時器
        if self._is_active and not self._timer.isActive():
            self._timer.start()

        painter.save()
        painter.setClipRect(self.rect())
        
        # 繪製文字
        x = -self._scroll_pos
        y = (self.height() + fm.ascent() - fm.descent()) / 2
        
        painter.drawText(int(x), int(y), self.text())
        
        # 如果文字已經開始移出視野，在右側繼續繪製以實現無縫循環
        if self._scroll_pos > 0:
            painter.drawText(int(x + text_width + 20), int(y), self.text())
        
        painter.restore()

    def _on_timeout(self):
        # 如果不在活躍狀態，停止計時器
        if not self._is_active:
            if self._timer.isActive():
                self._timer.stop()
            return
        
        # 檢查是否在全域暫停中
        if MarqueeLabel._global_pause_counter > 0:
            MarqueeLabel._global_pause_counter -= 1
            if MarqueeLabel._global_pause_counter == 0:
                MarqueeLabel._waiting_for_sync = False  # 重置等待狀態
            self.update()
            return
        
        # 如果不需要捲動，保持在起始位置
        if not self._is_scrollable:
            self._at_home = True
            return
        
        # 如果在等待同步狀態，只有還沒到起點的才能繼續捲動
        if MarqueeLabel._waiting_for_sync:
            if self._scroll_pos == 0:
                # 已經在起點了，停止捲動
                self._at_home = True
                self.update()
                return
            else:
                # 還沒到起點，繼續捲動
                self._scroll_pos += 1
                fm = self.fontMetrics()
                text_width = fm.horizontalAdvance(self.text())
                
                if self._scroll_pos >= text_width + 20:
                    self._scroll_pos = 0
                    self._at_home = True
                    
                    # 檢查是否所有活躍標籤都到起點了
                    all_at_home = all(
                        inst._at_home for inst in MarqueeLabel._instances
                        if inst._is_active
                    )
                    
                    if all_at_home:
                        MarqueeLabel._global_pause_counter = MarqueeLabel._global_pause_threshold
                        MarqueeLabel._waiting_for_sync = False
                
                self.update()
                return
        
        # 正常捲動
        self._at_home = False
        self._scroll_pos += 1
        
        # 計算是否完成一次循環
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self.text())
        
        # 當文字完全移出並回到起始位置時
        if self._scroll_pos >= text_width + 20:
            self._scroll_pos = 0
            self._at_home = True
            
            # 檢查是否所有活躍標籤都已經在起點
            all_at_home = all(
                inst._at_home for inst in MarqueeLabel._instances
                if inst._is_active
            )
            
            if all_at_home:
                # 所有標籤都在起點了，直接開始暫停
                MarqueeLabel._global_pause_counter = MarqueeLabel._global_pause_threshold
                MarqueeLabel._waiting_for_sync = False
            elif not MarqueeLabel._waiting_for_sync:
                # 還有其他標籤沒到起點，進入等待同步狀態
                MarqueeLabel._waiting_for_sync = True
            
        self.update()
    
    def __del__(self):
        """清理實例"""
        try:
            if self in MarqueeLabel._instances:
                MarqueeLabel._instances.remove(self)
        except:
            pass


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
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(5)
        
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
        
        # 文字資訊容器
        info_container = QWidget()
        info_container.setStyleSheet("background: transparent;")
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        
        # 歌曲名稱
        self.song_title = MarqueeLabel("Waiting for music...")
        self.song_title.setStyleSheet("""
            color: white;
            font-size: 18px;
            font-weight: bold;
            background: transparent;
        """)
        self.song_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.song_title.setFixedHeight(30)  # 固定高度避免跳動
        
        # 演出者
        self.artist_name = MarqueeLabel("-")
        self.artist_name.setStyleSheet("""
            color: #aaa;
            font-size: 14px;
            background: transparent;
        """)
        self.artist_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artist_name.setFixedHeight(25)
        
        # 專輯名稱
        self.album_name = MarqueeLabel("-")
        self.album_name.setStyleSheet("""
            color: #888;
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
        text_label.setStyleSheet("color: white; font-size: 32px; font-weight: bold; background: transparent;")
        
        desc_label = QLabel("請點擊下方按鈕進行綁定，以顯示您的 Spotify 播放資訊")
        desc_label.setStyleSheet("color: #aaa; font-size: 18px; background: transparent;")
        desc_label.setWordWrap(True)
        
        self.bind_btn = QPushButton("綁定 Spotify")
        self.bind_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bind_btn.setFixedSize(250, 60)
        self.bind_btn.setStyleSheet("""
            QPushButton {
                background-color: #1DB954;
                color: white;
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
            color: #6af;
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
            color: #6af;
            font-size: 16px;
            font-weight: bold;
            background: transparent;
            letter-spacing: 2px;
        """)
        
        # 歌曲名稱（大字）
        self.song_title = MarqueeLabel("Waiting for music...")
        self.song_title.setStyleSheet("""
            color: white;
            font-size: 32px;
            font-weight: bold;
            background: transparent;
        """)
        self.song_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.song_title.setFixedHeight(50)
        
        # 演出者
        self.artist_name = MarqueeLabel("-")
        self.artist_name.setStyleSheet("""
            color: #ccc;
            font-size: 22px;
            background: transparent;
        """)
        self.artist_name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.artist_name.setFixedHeight(35)
        
        # 專輯名稱
        self.album_name = MarqueeLabel("-")
        self.album_name.setStyleSheet("""
            color: #888;
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
            color: #aaa;
            font-size: 16px;
            background: transparent;
        """)
        
        self.total_time = QLabel("0:00")
        self.total_time.setStyleSheet("""
            color: #aaa;
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
        """從 PIL Image 設置專輯封面"""
        try:
            from PIL.ImageQt import ImageQt
            qim = ImageQt(pil_image)
            pixmap = QPixmap.fromImage(qim)
            self.set_album_art(pixmap)
        except Exception as e:
            import logging
            logging.error(f"設置專輯封面失敗: {e}")


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
        button_configs = [
            ("WiFi", "📶", "#1DB954"),
            ("藍牙", "🔵", "#4285F4"),
            ("亮度", "☀", "#FF9800")
        ]
        
        for title, icon, color in button_configs:
            btn = self.create_control_button(title, icon, color)
            self.buttons.append(btn)
            button_layout.addWidget(btn)
        
        content_layout.addLayout(button_layout)
        content_layout.addStretch()
        
        # === 右側：系統狀態資訊（水平排列兩個卡片）===
        status_layout = QHBoxLayout()
        status_layout.setSpacing(20)
        
        # WiFi 狀態卡片
        wifi_card = QWidget()
        wifi_card.setFixedSize(280, 80)
        wifi_card.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
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
        self.wifi_status_label.setStyleSheet("""
            color: white;
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        
        self.wifi_detail_label = QLabel("取得連線資訊")
        self.wifi_detail_label.setStyleSheet("""
            color: #aaa;
            font-size: 12px;
            background: transparent;
        """)
        
        wifi_info_layout.addWidget(self.wifi_status_label)
        wifi_info_layout.addWidget(self.wifi_detail_label)
        wifi_card_layout.addLayout(wifi_info_layout)
        wifi_card_layout.addStretch()
        
        # WiFi 信號強度指示
        self.wifi_signal_label = QLabel("")
        self.wifi_signal_label.setStyleSheet("""
            color: #6f6;
            font-size: 18px;
            font-weight: bold;
            background: transparent;
        """)
        wifi_card_layout.addWidget(self.wifi_signal_label)
        
        status_layout.addWidget(wifi_card)
        
        # 日期時間卡片
        datetime_card = QWidget()
        datetime_card.setFixedSize(220, 80)
        datetime_card.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
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
        self.date_label.setStyleSheet("""
            color: white;
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        
        self.weekday_label = QLabel("")
        self.weekday_label.setStyleSheet("""
            color: #aaa;
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
        hint_label.setStyleSheet("""
            color: #888;
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
        """更新 WiFi 狀態 - 使用 /proc/net/wireless + iw（輕量快速）"""
        import random
        
        # 檢查是否在 Linux 環境
        if platform.system() != 'Linux':
            # macOS/Windows: 顯示模擬資料
            dummy_networks = ["Home-WiFi", "Office-5G", "Starbucks_Free", "iPhone 熱點"]
            ssid = random.choice(dummy_networks)
            signal = random.randint(60, 95)
            
            self.wifi_ssid = ssid
            self.wifi_signal = signal
            self.wifi_status_label.setText(ssid)
            
            if signal >= 80:
                signal_text = "信號極佳"
                signal_color = "#6f6"
            elif signal >= 60:
                signal_text = "信號良好"
                signal_color = "#6f6"
            else:
                signal_text = "信號普通"
                signal_color = "#fa0"
            
            self.wifi_detail_label.setText(signal_text)
            self.wifi_signal_label.setText(f"{signal}%")
            self.wifi_signal_label.setStyleSheet(f"""
                color: {signal_color};
                font-size: 18px;
                font-weight: bold;
                background: transparent;
            """)
            return
        
        # Linux: 使用 /proc/net/wireless 讀取信號強度（超快，<1ms）
        try:
            ssid = None
            signal = 0
            interface = None
            
            # 1. 從 /proc/net/wireless 讀取信號強度和介面名稱
            # 格式：Inter-| sta-|   Quality        |   Discarded packets
            #        face | tus | link level noise |  nwid  crypt   frag  retry   misc
            #       wlp6s0: 0000   57.  -53.  -256        0      0      0      0    578
            if os.path.exists('/proc/net/wireless'):
                with open('/proc/net/wireless', 'r') as f:
                    lines = f.readlines()
                    for line in lines[2:]:  # 跳過標題行
                        line = line.strip()
                        if ':' in line:
                            parts = line.split()
                            if len(parts) >= 3:
                                interface = parts[0].rstrip(':')
                                # link quality 通常是 0-70，轉換為百分比
                                try:
                                    link_quality = float(parts[2].rstrip('.'))
                                    signal = min(100, int(link_quality * 100 / 70))
                                except (ValueError, IndexError):
                                    signal = 0
                                break
            
            # 2. 使用 iw 取得 SSID（比 iwgetid 更常見，不會觸發掃描）
            if interface and signal > 0:
                import subprocess
                try:
                    # iw dev <interface> link 可以取得當前連接的 SSID
                    result = subprocess.run(
                        ['iw', 'dev', interface, 'link'],
                        capture_output=True,
                        text=True,
                        timeout=1  # 1秒超時
                    )
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            line = line.strip()
                            if line.startswith('SSID:'):
                                ssid = line[5:].strip()
                                break
                except FileNotFoundError:
                    # iw 不存在，嘗試使用 nmcli（只查詢當前連接，不掃描）
                    try:
                        result = subprocess.run(
                            ['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
                            capture_output=True,
                            text=True,
                            timeout=1
                        )
                        if result.returncode == 0:
                            for line in result.stdout.strip().split('\n'):
                                # 格式: 是:SSID 或 yes:SSID
                                if line.startswith('是:') or line.lower().startswith('yes:'):
                                    ssid = line.split(':', 1)[1]
                                    break
                    except Exception:
                        ssid = None
                except Exception:
                    ssid = None
            
            # 3. 更新 UI
            if ssid and signal > 0:
                self.wifi_ssid = ssid
                self.wifi_signal = signal
                self.wifi_status_label.setText(ssid)
                
                if signal >= 80:
                    signal_text = "信號極佳"
                    signal_color = "#6f6"
                elif signal >= 60:
                    signal_text = "信號良好"
                    signal_color = "#6f6"
                elif signal >= 40:
                    signal_text = "信號普通"
                    signal_color = "#fa0"
                else:
                    signal_text = "信號較弱"
                    signal_color = "#f66"
                
                self.wifi_detail_label.setText(signal_text)
                self.wifi_signal_label.setText(f"{signal}%")
                self.wifi_signal_label.setStyleSheet(f"""
                    color: {signal_color};
                    font-size: 16px;
                    font-weight: bold;
                    background: transparent;
                """)
            else:
                # 未連線或無法取得
                self.wifi_ssid = None
                self.wifi_signal = 0
                self.wifi_status_label.setText("未連線")
                self.wifi_detail_label.setText("點擊 WiFi 按鈕進行連線")
                self.wifi_signal_label.setText("")
                self.wifi_detail_label.setStyleSheet("""
                    color: #f66;
                    font-size: 14px;
                    background: transparent;
                """)
                
        except Exception as e:
            self.wifi_status_label.setText("無法取得狀態")
            self.wifi_detail_label.setText(str(e)[:30])
            self.wifi_signal_label.setText("")
        
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
        btn.clicked.connect(lambda: self.on_button_clicked(title))
        
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
    
    def adjust_color(self, hex_color, factor):
        """調整顏色亮度"""
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))
        return f'#{r:02x}{g:02x}{b:02x}'
    
    def on_button_clicked(self, title):
        """按鈕點擊處理"""
        print(f"控制面板按鈕被點擊: {title}")
        # 這裡可以添加具體功能
        if title == "WiFi":
            # 可以觸發 WiFi 管理器
            parent = self.parent()
            if parent and hasattr(parent, 'show_wifi_manager'):
                parent.show_wifi_manager()  # type: ignore
        elif title == "藍牙":
            print("藍牙功能待實現")
        elif title == "亮度":
            print("亮度調整待實現")
    
    def hide_panel(self):
        """隱藏面板"""
        parent = self.parent()
        if parent and hasattr(parent, 'hide_control_panel'):
            parent.hide_control_panel()  # type: ignore


class Dashboard(QWidget):
    # 定義 Qt Signals，用於從背景執行緒安全地更新 UI
    signal_update_rpm = pyqtSignal(float)
    signal_update_speed = pyqtSignal(float)
    signal_update_temperature = pyqtSignal(float)
    signal_update_fuel = pyqtSignal(float)
    signal_update_gear = pyqtSignal(str)
    signal_update_turn_signal = pyqtSignal(str)  # "left", "right", "both", "off"
    
    # Spotify 相關 Signals
    signal_update_spotify_track = pyqtSignal(str, str, str)
    signal_update_spotify_progress = pyqtSignal(float, float, bool)  # current, total, is_playing
    signal_update_spotify_art = pyqtSignal(object)  # 傳遞 PIL Image 物件

    def __init__(self):
        super().__init__()
        self.setWindowTitle("儀表板 - F1:翻左卡片/焦點 Shift+F1:詳細視圖 F2:翻右卡片 Shift+F2:重置Trip")
        
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
        
        # 下拉面板相關
        self.control_panel = None
        self.panel_animation = None
        self.panel_visible = False
        self.panel_touch_start = None
        self.panel_drag_active = False

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
        # Timer 啟動延遲到 start_dashboard() 調用時
        # self.time_timer.start(1000)
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
        # Timer 啟動延遲到 start_dashboard() 調用時
        # self.animation_timer.start(16)  # 約 60 FPS
        
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
        
        # === 創建下拉控制面板（初始隱藏在螢幕上方）===
        self.control_panel = ControlPanel(self)
        self.control_panel.setGeometry(0, -300, 1920, 300)
        self.control_panel.raise_()  # 確保在最上層
        
        # === 主儀表板區域（三欄式佈局）===
        dashboard_container = QWidget()
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.setSpacing(15)
        dashboard_container.setLayout(main_layout)
        main_vertical_layout.addWidget(dashboard_container)
        
        # ========================================
        # 左側區域：數位儀表卡片（可左右滑動）
        # ========================================
        left_section = QWidget()
        left_section.setFixedWidth(380)
        left_layout = QVBoxLayout(left_section)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)
        
        # 左側卡片堆疊
        self.left_card_stack = QStackedWidget()
        self.left_card_stack.setFixedSize(380, 380)
        
        # 四宮格儀表卡片（轉速/水溫/渦輪負壓/電瓶電壓）
        self.quad_gauge_card = QuadGaugeCard()
        self.quad_gauge_card.detail_requested.connect(self._show_gauge_detail)
        
        # 四宮格詳細視圖
        self.quad_gauge_detail = QuadGaugeDetailView()
        self.quad_gauge_detail.back_requested.connect(self._hide_gauge_detail)
        
        # 油量數位卡片
        fuel_style = GaugeStyle(
            major_ticks=4, minor_ticks=1,
            start_angle=225, span_angle=270,
            tick_color=QColor(100, 150, 255),
            needle_color=QColor(255, 200, 100),
            text_scale=1.0
        )
        fuel_labels = {0: "E", 50: "½", 100: "F"}
        self.fuel_gauge = AnalogGauge(0, 100, fuel_style, labels=fuel_labels, title="FUEL")
        self.fuel_gauge.setFixedSize(380, 380)
        
        # 詳細視圖狀態
        self._in_detail_view = False
        self._detail_gauge_index = -1
        
        # 左側卡片動畫狀態
        self._left_card_animating = False
        
        # 右側卡片動畫狀態
        self._right_card_animating = False
        self._right_row_animating = False
        
        self.left_card_stack.addWidget(self.quad_gauge_card)    # index 0
        self.left_card_stack.addWidget(self.quad_gauge_detail)  # index 1 (詳細視圖)
        self.left_card_stack.addWidget(self.fuel_gauge)         # index 2
        
        # 左側卡片指示器
        left_indicator_widget = QWidget()
        left_indicator_widget.setFixedHeight(30)
        left_indicator_widget.setStyleSheet("background: transparent;")
        left_indicator_layout = QHBoxLayout(left_indicator_widget)
        left_indicator_layout.setContentsMargins(0, 5, 0, 0)
        left_indicator_layout.setSpacing(8)
        left_indicator_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.left_indicators = []
        for i in range(2):  # 2 張左側卡片（四宮格 + 油量）
            dot = QLabel("●")
            dot.setFixedSize(12, 12)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setStyleSheet("color: #444; font-size: 18px;")
            self.left_indicators.append(dot)
            left_indicator_layout.addWidget(dot)
        self.left_indicators[0].setStyleSheet("color: #6af; font-size: 18px;")
        
        left_layout.addWidget(self.left_card_stack)
        left_layout.addWidget(left_indicator_widget)
        
        # ========================================
        # 中央區域：時速 + 檔位
        # ========================================
        center_section = QWidget()
        center_section.setFixedWidth(480)  # 增加寬度以容納 3 位數時速
        center_layout = QVBoxLayout(center_section)
        center_layout.setSpacing(0)
        center_layout.setContentsMargins(5, 10, 5, 10)
        
        # === 上方：CRUISE 顯示區（預留空間）===
        self.cruise_label = QLabel("")
        self.cruise_label.setFixedHeight(50)
        self.cruise_label.setStyleSheet("""
            color: #4ade80;
            font-size: 40px;
            font-weight: bold;
            font-family: Arial;
            background: transparent;
            letter-spacing: 3px;
        """)
        self.cruise_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # === 中央：檔位(左) + 時速(右) ===
        speed_gear_widget = QWidget()
        speed_gear_widget.setStyleSheet("background: transparent;")
        speed_gear_layout = QHBoxLayout(speed_gear_widget)
        speed_gear_layout.setContentsMargins(0, 0, 0, 0)
        speed_gear_layout.setSpacing(10)
        
        # 檔位顯示（左側）
        self.gear_label = QLabel("P")
        self.gear_label.setStyleSheet("""
            color: #4ade80;
            font-size: 120px;
            font-weight: bold;
            font-family: Arial;
            background: rgba(30, 30, 40, 0.8);
            border: 4px solid #456;
            border-radius: 20px;
        """)
        self.gear_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gear_label.setFixedSize(140, 180)
        
        # 時速區域（右側）
        speed_container = QWidget()
        speed_container.setStyleSheet("background: transparent;")
        speed_layout = QVBoxLayout(speed_container)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(0)
        
        # 速度數字
        self.speed_label = QLabel("0")
        self.speed_label.setStyleSheet("""
            color: white;
            font-size: 140px;
            font-weight: bold;
            font-family: 'Arial', 'Helvetica', sans-serif;
            background: transparent;
        """)
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_label.setFixedWidth(300)  # 固定寬度確保置中穩定
        
        # 單位標籤
        self.unit_label = QLabel("Km/h")
        self.unit_label.setStyleSheet("""
            color: #888;
            font-size: 28px;
            font-family: Arial;
            background: transparent;
        """)
        self.unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_label.setFixedWidth(300)  # 與時速同寬確保置中
        
        speed_layout.addStretch()
        speed_layout.addWidget(self.speed_label)
        speed_layout.addWidget(self.unit_label)
        speed_layout.addStretch()
        
        speed_gear_layout.addWidget(self.gear_label)
        speed_gear_layout.addWidget(speed_container, 1)
        
        # 組合中央區域佈局
        center_layout.addWidget(self.cruise_label)
        center_layout.addWidget(speed_gear_widget, 1)
        center_layout.addSpacing(20)
        
        # ========================================
        # 右側區域：寬卡片（雙層，可左右滑動）
        # ========================================
        right_section = QWidget()
        right_section.setFixedWidth(840)  # 列指示器 + 卡片
        right_layout = QHBoxLayout(right_section)  # 改成水平佈局：[列指示器] [卡片區]
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        
        # 列指示器（垂直排列，放在卡片左側）
        row_indicator_widget = QWidget()
        row_indicator_widget.setFixedWidth(30)
        row_indicator_layout = QVBoxLayout(row_indicator_widget)
        row_indicator_layout.setContentsMargins(0, 0, 0, 0)
        row_indicator_layout.setSpacing(12)
        row_indicator_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.row_indicators = []
        for i in range(2):  # 2 列
            dot = QLabel("●")
            dot.setFixedSize(16, 16)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setStyleSheet("color: #444; font-size: 16px;")
            self.row_indicators.append(dot)
            row_indicator_layout.addWidget(dot)
        self.row_indicators[0].setStyleSheet("color: #6af; font-size: 16px;")
        
        # 右側卡片區（卡片堆疊 + 底部卡片指示器）
        right_cards_section = QWidget()
        right_cards_layout = QVBoxLayout(right_cards_section)
        right_cards_layout.setContentsMargins(0, 0, 0, 0)
        right_cards_layout.setSpacing(5)
        
        # 右側使用雙層架構 - 列 (rows) 包含多個卡片 (cards)
        self.row_stack = QStackedWidget()
        self.row_stack.setFixedSize(800, 380)
        
        # === 第一列：音樂卡片 / 門狀態卡片 ===
        row1_cards = QStackedWidget()
        row1_cards.setFixedSize(800, 380)
        
        # 音樂卡片（寬版）
        self.music_card = MusicCardWide()
        self.music_card.request_bind.connect(self.start_spotify_auth)
        
        # 門狀態卡片
        self.door_card = DoorStatusCard()
        self.door_card.setFixedSize(800, 380)
        
        row1_cards.addWidget(self.music_card)  # row1_index 0
        row1_cards.addWidget(self.door_card)   # row1_index 1
        
        # === 第二列：Trip 卡片 / ODO 卡片 ===
        row2_cards = QStackedWidget()
        row2_cards.setFixedSize(800, 380)
        
        # Trip 卡片（寬版）
        self.trip_card = TripCardWide()
        row2_cards.addWidget(self.trip_card)  # row2_index 0
        
        # ODO 卡片（寬版）
        self.odo_card = OdometerCardWide()
        row2_cards.addWidget(self.odo_card)  # row2_index 1
        
        # 添加列到列堆疊
        self.row_stack.addWidget(row1_cards)  # row_index 0
        self.row_stack.addWidget(row2_cards)  # row_index 1
        
        # 卡片指示器（底部水平排列）
        card_indicator_container = QWidget()
        card_indicator_container.setFixedHeight(30)
        card_indicator_container.setStyleSheet("background: transparent;")
        card_indicator_layout = QHBoxLayout(card_indicator_container)
        card_indicator_layout.setContentsMargins(0, 5, 0, 0)
        card_indicator_layout.setSpacing(8)
        card_indicator_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.card_indicators = []
        for i in range(2):  # 第一列有 2 張卡片
            dot = QLabel("●")
            dot.setFixedSize(12, 12)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setStyleSheet("color: #444; font-size: 18px;")
            self.card_indicators.append(dot)
            card_indicator_layout.addWidget(dot)
        self.card_indicators[0].setStyleSheet("color: #6af; font-size: 18px;")
        
        right_cards_layout.addWidget(self.row_stack)
        right_cards_layout.addWidget(card_indicator_container)
        
        # 組合右側區域：列指示器 + 卡片區
        right_layout.addWidget(row_indicator_widget)
        right_layout.addWidget(right_cards_section)
        
        # === 狀態變數 ===
        self.current_row_index = 0     # 當前列索引（右側）
        self.current_card_index = 0    # 當前卡片索引（右側）
        self.current_left_index = 0    # 當前左側卡片索引
        self.rows = [row1_cards, row2_cards]  # 列的引用
        self.row_card_counts = [2, 2]  # 每列的卡片數量
        self.left_card_count = 2       # 左側卡片數量（四宮格 + 油量，不含詳細視圖）
        
        # 觸控滑動相關
        self.touch_start_pos = None
        self.touch_start_time = None
        self.swipe_threshold = 50  # 滑動閾值（像素）
        self.is_swiping = False
        self.swipe_direction = None  # 'horizontal' or 'vertical'
        self.swipe_enabled = True  # 滑動是否啟用（輸入時禁用）
        
        # 判斷觸控位置（左側或右側）
        self.swipe_area = None  # 'left' or 'right'

        # 組合主佈局
        # 左側 380px | 彈性空間 | 中央 420px | 右側 850px
        main_layout.addWidget(left_section)
        main_layout.addStretch(1)  # 所有彈性空間都在左邊
        main_layout.addWidget(center_section)
        main_layout.addWidget(right_section)

    def init_data(self):
        """初始化儀表數據，可以從外部數據源更新"""
        self.speed = 0
        self.rpm = 0
        self.temp = 45  # 正常水溫約在 45-50% 位置（對應 85-95°C）
        self.fuel = 60  # 稍微偏上的油量
        self.gear = "P"
        self.turbo = -0.7  # 待速時的進氣歧管負壓 (bar)
        self.battery = 12.6  # 電瓶電壓 (V)
        
        # 定速巡航狀態
        self.cruise_switch = False   # 開關是否開啟（白色）
        self.cruise_engaged = False  # 是否作動中（綠色）
        
        # RPM 動畫平滑 (GUI 端二次平滑)
        self.target_rpm = 0.0  # 目標轉速
        self.rpm_animation_alpha = 0.3  # GUI 端平滑係數
        
        # 門狀態卡片自動切換
        self.door_auto_switch_timer = QTimer()
        self.door_auto_switch_timer.setSingleShot(True)
        self.door_auto_switch_timer.timeout.connect(self._auto_switch_back_from_door)
        self.previous_row_index = 0   # 記錄切換前的列索引
        self.previous_card_index = 0  # 記錄切換前的卡片索引
        
        # 物理心跳 Timer（每 100ms 觸發一次，持續累積里程）
        self.physics_timer = QTimer()
        self.physics_timer.timeout.connect(self._physics_tick)
        # Timer 啟動延遲到 start_dashboard() 調用時
        # self.physics_timer.start(100)  # 100ms = 0.1 秒
        self.last_physics_time = time.time()
        
        self.update_display()
        
        # Spotify 初始化延遲到 start_dashboard() 調用時
        # self.check_spotify_config()

    def start_dashboard(self):
        """開機動畫完成後啟動儀表板的所有邏輯"""
        print("啟動儀表板邏輯...")
        
        # 啟動卡頓偵測器
        self.jank_detector = JankDetector(threshold_ms=50)
        self.jank_detector.start()
        
        # 啟動時間更新 Timer
        self.time_timer.start(1000)
        
        # 啟動方向燈動畫 Timer
        self.animation_timer.start(16)  # 約 60 FPS
        
        # 啟動物理心跳 Timer（里程累積）
        self.last_physics_time = time.time()  # 重設時間基準
        self.physics_timer.start(100)  # 100ms = 0.1 秒
        
        # 初始化 Spotify
        self.check_spotify_config()
        
        print("儀表板邏輯已啟動")

    def check_spotify_config(self):
        """檢查 Spotify 設定並初始化"""
        config_path = "spotify_config.json"
        cache_path = ".spotify_cache"
        
        # 只有當配置檔和快取都存在時才自動初始化
        if os.path.exists(config_path) and os.path.exists(cache_path):
            print("發現 Spotify 設定檔和快取，正在初始化...")
            self.music_card.show_player_ui()
            # 在背景執行緒初始化，避免卡住 UI
            import threading
            def init_spotify():
                result = setup_spotify(self)
                if result:
                    print("Spotify 初始化成功")
                else:
                    print("Spotify 初始化失敗")
            threading.Thread(target=init_spotify, daemon=True).start()
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
        primary_screen = QApplication.primaryScreen()
        if primary_screen:
            screen_geometry = primary_screen.geometry()
            dialog_geometry = self.auth_dialog.geometry()
            x = (screen_geometry.width() - dialog_geometry.width()) // 2
            y = (screen_geometry.height() - dialog_geometry.height()) // 2
            self.auth_dialog.move(x, y)

    def on_auth_completed(self, success):
        """授權完成回調"""
        if success:
            print("Spotify 授權成功！")
            self.music_card.show_player_ui()
            # 在背景執行緒初始化 Spotify，避免阻塞 UI
            def _init_spotify_async():
                try:
                    setup_spotify(self)
                except Exception as e:
                    print(f"Spotify 初始化失敗: {e}")
            
            import threading
            spotify_thread = threading.Thread(target=_init_spotify_async, daemon=True)
            spotify_thread.start()
        else:
            print("Spotify 授權失敗")
            self.music_card.show_bind_ui()
        
        # 關閉對話框 (如果還沒關閉)
        if hasattr(self, 'auth_dialog'):
            self.auth_dialog.close()
            del self.auth_dialog
    
    def show_control_panel(self):
        """顯示下拉控制面板"""
        if self.panel_visible or not self.control_panel:
            return
        
        self.panel_visible = True
        
        # 創建動畫
        self.panel_animation = QPropertyAnimation(self.control_panel, b"geometry")
        self.panel_animation.setDuration(300)  # 300ms
        self.panel_animation.setStartValue(self.control_panel.geometry())
        self.panel_animation.setEndValue(QRectF(0, 50, 1920, 300).toRect())  # 從狀態欄下方滑出
        self.panel_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.panel_animation.start()
        
        self.control_panel.show()
        self.control_panel.raise_()
    
    def hide_control_panel(self):
        """隱藏下拉控制面板"""
        if not self.panel_visible or not self.control_panel:
            return
        
        self.panel_visible = False
        
        # 創建動畫
        self.panel_animation = QPropertyAnimation(self.control_panel, b"geometry")
        self.panel_animation.setDuration(300)
        self.panel_animation.setStartValue(self.control_panel.geometry())
        self.panel_animation.setEndValue(QRectF(0, -300, 1920, 300).toRect())
        self.panel_animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self.panel_animation.finished.connect(self.control_panel.hide)
        self.panel_animation.start()
    
    def show_wifi_manager(self):
        """顯示 WiFi 管理器"""
        try:
            from wifi_manager import WiFiManagerWidget
            
            # 在 Mac 上自動啟用測試模式
            test_mode = platform.system() == 'Darwin'
            
            # 創建 WiFi 管理器對話框
            self.wifi_dialog = WiFiManagerWidget(self, test_mode=test_mode)
            self.wifi_dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
            self.wifi_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            
            # 置中顯示
            self.wifi_dialog.move(
                self.geometry().center() - self.wifi_dialog.rect().center()
            )
            
            self.wifi_dialog.show()
            if test_mode:
                print("WiFi 管理器已開啟 (測試模式)")
            else:
                print("WiFi 管理器已開啟")
            
        except ImportError:
            print("WiFi 管理器模組未找到")
        except Exception as e:
            print(f"開啟 WiFi 管理器錯誤: {e}")

    # === 執行緒安全的公開方法 (從背景執行緒呼叫) ===
    @perf_track
    def set_speed(self, speed):
        """外部數據接口：設置速度 (0-200 km/h)
        執行緒安全：透過 Signal 發送，由主執行緒執行
        """
        self.signal_update_speed.emit(float(speed))
    
    @perf_track
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
    
    def set_door_status(self, door, is_closed):
        """外部數據接口：設置門的狀態
        Args:
            door: "FL", "FR", "RL", "RR", "BK"
            is_closed: True=關閉, False=開啟
        直接在主執行緒中調用（因為通常從主執行緒觸發）
        """
        if not hasattr(self, 'door_card'):
            return
        
        # 檢查門狀態是否真的改變
        door_upper = door.upper()
        current_state = None
        if door_upper == "FL":
            current_state = self.door_card.door_fl_closed
        elif door_upper == "FR":
            current_state = self.door_card.door_fr_closed
        elif door_upper == "RL":
            current_state = self.door_card.door_rl_closed
        elif door_upper == "RR":
            current_state = self.door_card.door_rr_closed
        elif door_upper == "BK":
            current_state = self.door_card.door_bk_closed
        
        # 如果門狀態沒有改變，直接返回（避免 CAN 訊息瘋狂觸發）
        if current_state is not None and current_state == is_closed:
            return
        
        # 門狀態有改變，收起控制面板
        if self.panel_visible:
            self.hide_control_panel()
        
        # 更新門狀態
        self.door_card.set_door_status(door, is_closed)
        
        # 門卡片位於第一列的第二張 (row=0, card=1)
        DOOR_ROW_INDEX = 0
        DOOR_CARD_INDEX = 1  # 音樂=0, 門=1
        
        # 當有門狀態變更時，自動切換到門狀態卡片
        if not (self.current_row_index == DOOR_ROW_INDEX and self.current_card_index == DOOR_CARD_INDEX):
            # 記錄切換前的位置
            self.previous_row_index = self.current_row_index
            self.previous_card_index = self.current_card_index
            
            # 切換到門狀態卡片
            self.current_row_index = DOOR_ROW_INDEX
            self.current_card_index = DOOR_CARD_INDEX
            self.row_stack.setCurrentIndex(DOOR_ROW_INDEX)
            self.rows[DOOR_ROW_INDEX].setCurrentIndex(DOOR_CARD_INDEX)
            
            # 更新指示器
            self.update_indicators()
            
            print(f"檢測到門狀態變更 ({door} = {'關閉' if is_closed else '開啟'})，自動切換到門狀態卡片")
        
        # 重置自動回退計時器
        # 如果所有門都關閉，5秒後自動切回
        if (self.door_card.door_fl_closed and 
            self.door_card.door_fr_closed and 
            self.door_card.door_rl_closed and 
            self.door_card.door_rr_closed and 
            self.door_card.door_bk_closed):
            # 所有門都關閉，啟動計時器
            if hasattr(self, 'door_auto_switch_timer'):
                self.door_auto_switch_timer.start(5000)  # 5秒後切回
                print("所有門已關閉，5秒後將自動切回")
        else:
            # 有門開啟，停止計時器
            if hasattr(self, 'door_auto_switch_timer'):
                self.door_auto_switch_timer.stop()
    
    def _auto_switch_back_from_door(self):
        """自動從門狀態卡片切回之前的卡片"""
        DOOR_ROW_INDEX = 0
        DOOR_CARD_INDEX = 1  # 音樂=0, 門=1
        
        if self.current_row_index == DOOR_ROW_INDEX and self.current_card_index == DOOR_CARD_INDEX:
            # 切回之前的位置
            self.current_row_index = self.previous_row_index
            self.current_card_index = self.previous_card_index
            self.row_stack.setCurrentIndex(self.previous_row_index)
            self.rows[self.previous_row_index].setCurrentIndex(self.previous_card_index)
            
            # 更新指示器
            self.update_indicators()
            
            row_names = ["第一列", "第二列"]
            row1_card_names = ["音樂播放器", "門狀態"]
            row2_card_names = ["Trip", "ODO"]
            if self.previous_row_index == 0:
                card_name = row1_card_names[self.previous_card_index] if self.previous_card_index < len(row1_card_names) else "未知"
            else:
                card_name = row2_card_names[self.previous_card_index] if self.previous_card_index < len(row2_card_names) else "未知"
            print(f"所有門已關閉，自動切回 {row_names[self.previous_row_index]} - {card_name}")
    
    # === Spotify 執行緒安全接口 ===
    def update_spotify_track(self, title, artist, album=""):
        """更新 Spotify 歌曲資訊 (執行緒安全)"""
        self.signal_update_spotify_track.emit(title, artist, album)

    def update_spotify_progress(self, current, total, is_playing=True):
        """更新 Spotify 播放進度 (執行緒安全)"""
        self.signal_update_spotify_progress.emit(float(current), float(total), bool(is_playing))

    def update_spotify_art(self, pil_image):
        """更新 Spotify 專輯封面 (執行緒安全)"""
        self.signal_update_spotify_art.emit(pil_image)

    # === 實際執行 UI 更新的 Slot 方法 (在主執行緒中執行) ===
    @pyqtSlot(float)
    @perf_track
    def _slot_set_speed(self, speed):
        """Slot: 在主執行緒中更新速度顯示"""
        self.speed = max(0, min(200, speed))
        # 里程計算已改由 _physics_tick() 驅動，這裡只需記錄速度
        self.trip_card.current_speed = speed
        self.odo_card.current_speed = speed
        self.update_display()
    
    def _physics_tick(self):
        """物理心跳：每 100ms 根據當前速度累積里程"""
        current_time = time.time()
        time_delta = current_time - self.last_physics_time
        self.last_physics_time = current_time
        
        # 安全檢查：忽略異常的時間間隔（例如系統休眠後喚醒）
        if time_delta <= 0 or time_delta > 1.0:
            return
        
        # 使用當前速度計算里程
        current_speed = self.speed
        if current_speed > 0:
            # 距離 = 速度 * 時間 (km/h * hours = km)
            distance_increment = (current_speed / 3600.0) * time_delta
            
            # 更新 Trip 卡片里程
            self.trip_card.add_distance(distance_increment)
            # 更新 ODO 卡片里程
            self.odo_card.add_distance(distance_increment)
    
    @pyqtSlot(float)
    @perf_track
    def _slot_set_rpm(self, rpm):
        """Slot: 在主執行緒中更新轉速顯示 (含 GUI 端平滑)"""
        target = max(0, min(8, rpm))
        
        # GUI 端二次平滑：使用 EMA 讓指針移動更絲滑
        if self.rpm == 0:
            self.rpm = target  # 首次直接設定
        else:
            # 平滑插值：越接近目標越慢
            self.rpm = self.rpm * (1 - self.rpm_animation_alpha) + target * self.rpm_animation_alpha
        
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
        # 只在檔位真正改變時才收起控制面板
        if gear != self.gear and self.panel_visible:
            self.hide_control_panel()
        
        self.gear = gear
        self.update_display()
    
    @pyqtSlot(str)
    def _slot_update_turn_signal(self, state):
        """Slot: 在主執行緒中更新方向燈狀態（從 CAN 訊號）
        Args:
            state: "left_on", "left_off", "right_on", "right_off", "both_on", "both_off", "off"
        """
        # 方向燈剛啟動時收起控制面板（狀態從 off 變成 on）
        # 注意：雙閃燈 (both_on) 不收起控制面板，因為通常是停車時使用
        prev_left = self.left_turn_on
        prev_right = self.right_turn_on
        
        if state == "left_on" and not prev_left and self.panel_visible:
            self.hide_control_panel()
        elif state == "right_on" and not prev_right and self.panel_visible:
            self.hide_control_panel()
        # 雙閃燈 (both_on) 不收起控制面板
        
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
    @pyqtSlot(str, str, str)
    def _slot_update_spotify_track(self, title, artist, album):
        print(f"DEBUG: UI Received - Title: {title}, Artist: {artist}, Album: '{album}'")
        if hasattr(self, 'music_card'):
            self.music_card.set_song(title, artist, album)

    @pyqtSlot(float, float, bool)
    def _slot_update_spotify_progress(self, current, total, is_playing):
        if hasattr(self, 'music_card'):
            self.music_card.set_progress(current, total, is_playing)

    @pyqtSlot(object)
    def _slot_update_spotify_art(self, pil_image):
        if hasattr(self, 'music_card'):
            self.music_card.set_album_art_from_pil(pil_image)

    @perf_track
    def update_indicators(self):
        """更新所有指示器的狀態"""
        # 更新左側卡片指示器
        for i, indicator in enumerate(self.left_indicators):
            if i == self.current_left_index:
                indicator.setStyleSheet("color: #6af; font-size: 18px;")
            else:
                indicator.setStyleSheet("color: #444; font-size: 18px;")
        
        # 更新右側列指示器
        for i, indicator in enumerate(self.row_indicators):
            if i == self.current_row_index:
                indicator.setStyleSheet("color: #6af; font-size: 16px;")
            else:
                indicator.setStyleSheet("color: #444; font-size: 16px;")
        
        # 更新右側卡片指示器（根據當前列的卡片數量）
        card_count = self.row_card_counts[self.current_row_index]
        for i, indicator in enumerate(self.card_indicators):
            if i < card_count:
                indicator.show()
                if i == self.current_card_index:
                    indicator.setStyleSheet("color: #6af; font-size: 18px;")
                else:
                    indicator.setStyleSheet("color: #444; font-size: 18px;")
            else:
                indicator.hide()  # 隱藏多餘的指示器
    
    @perf_track
    def mousePressEvent(self, a0):  # type: ignore
        """觸控/滑鼠按下事件"""
        if a0 is None:
            return
        pos = a0.position().toPoint()
        
        # 如果滑動被禁用，只處理控制面板
        if not self.swipe_enabled:
            # 面板展開時，任何位置都可以開始拖拽收回
            if self.panel_visible:
                self.panel_touch_start = pos
                self.panel_drag_active = True
                import time
                self.panel_touch_time = time.time()
            return
        
        # 面板展開時，整個畫面任何位置都可以操作收回
        if self.panel_visible:
            self.panel_touch_start = pos
            self.panel_drag_active = True
            import time
            self.panel_touch_time = time.time()
            return
        
        # 檢查是否在頂部觸發區域（狀態欄高度 + 額外的觸控緩衝區）
        # 監聽範圍：頂部 80 像素（狀態欄 50px + 緩衝 30px）
        if pos.y() <= 80 and not self.panel_visible:
            self.panel_touch_start = pos
            self.panel_drag_active = True
            import time
            self.panel_touch_time = time.time()
            return
        
        # 檢查是否在左側區域（左側卡片切換）
        left_stack_global = self.left_card_stack.mapToGlobal(QPoint(0, 0))
        left_stack_rect = self.left_card_stack.geometry()
        left_stack_rect.moveTopLeft(left_stack_global)
        
        if left_stack_rect.contains(a0.globalPosition().toPoint()):
            self.touch_start_pos = a0.position().toPoint()
            self.is_swiping = True
            self.swipe_direction = None
            self.swipe_area = 'left'
            import time
            self.touch_start_time = time.time()
            return
        
        # 檢查是否在右側區域（卡片切換）
        row_stack_global = self.row_stack.mapToGlobal(QPoint(0, 0))
        row_stack_rect = self.row_stack.geometry()
        row_stack_rect.moveTopLeft(row_stack_global)
        
        if row_stack_rect.contains(a0.globalPosition().toPoint()):
            self.touch_start_pos = a0.position().toPoint()
            self.is_swiping = True
            self.swipe_direction = None
            self.swipe_area = 'right'
            import time
            self.touch_start_time = time.time()
    
    def mouseMoveEvent(self, a0):  # type: ignore
        """觸控/滑鼠移動事件"""
        if a0 is None:
            return
        # 處理控制面板拖拽
        if self.panel_drag_active and self.panel_touch_start is not None:
            pos = a0.position().toPoint()
            delta_y = pos.y() - self.panel_touch_start.y()
            
            if self.panel_visible:
                # 面板已展開，處理向上拖拽關閉
                if delta_y < 0 and self.control_panel:
                    # 限制拖拽範圍
                    new_y = max(-300, 50 + delta_y)
                    self.control_panel.setGeometry(0, int(new_y), 1920, 300)
            else:
                # 面板未展開，處理向下拖拽開啟
                if delta_y > 0 and self.control_panel:
                    # 限制拖拽範圍
                    new_y = min(50, -300 + delta_y)
                    self.control_panel.setGeometry(0, int(new_y), 1920, 300)
                    if not self.control_panel.isVisible():
                        self.control_panel.show()
                        self.control_panel.raise_()
            return
        
        # 處理卡片切換滑動
        if self.is_swiping and self.touch_start_pos is not None:
            # 計算滑動距離
            delta = a0.position().toPoint() - self.touch_start_pos
            
            # 判斷滑動方向（只在第一次超過閾值時決定）
            if self.swipe_direction is None:
                if abs(delta.x()) > 15 or abs(delta.y()) > 15:
                    if abs(delta.x()) > abs(delta.y()):
                        self.swipe_direction = 'horizontal'
                    else:
                        self.swipe_direction = 'vertical'
    
    def set_swipe_enabled(self, enabled):
        """設置滑動是否啟用"""
        self.swipe_enabled = enabled
        if not enabled:
            # 禁用滑動時重置狀態
            self.touch_start_pos = None
            self.is_swiping = False
    
    @perf_track
    def mouseReleaseEvent(self, a0):  # type: ignore
        """觸控/滑鼠釋放事件"""
        if a0 is None:
            return
        # 如果滑動被禁用，忽略事件
        if not self.swipe_enabled:
            return
        
        # 處理控制面板拖拽結束
        if self.panel_drag_active and self.panel_touch_start is not None:
            pos = a0.position().toPoint()
            delta_y = pos.y() - self.panel_touch_start.y()
            delta_x = abs(pos.x() - self.panel_touch_start.x())
            
            # 計算滑動速度（像素/秒）
            import time
            elapsed = time.time() - getattr(self, 'panel_touch_time', time.time())
            velocity = abs(delta_y) / max(elapsed, 0.01)  # 避免除以零
            
            # 計算總移動距離
            total_move = abs(delta_y) + delta_x
            
            # 寬鬆的判定條件：
            # 1. 距離閾值降低到 40 像素（原本 80）
            # 2. 或者速度超過 300 像素/秒（快速滑動）
            # 3. 點擊面板外區域直接收回（幾乎沒移動 = 點擊）
            distance_threshold = 40
            velocity_threshold = 300
            tap_threshold = 15  # 移動少於 15 像素視為點擊
            
            if self.panel_visible:
                # 面板已展開
                # 檢查是否點擊面板外區域（直接收回）
                is_tap = total_move < tap_threshold
                is_outside_panel = not (self.control_panel and self.control_panel.geometry().contains(pos))
                
                if is_tap and is_outside_panel:
                    # 點擊面板外區域，直接收回
                    self.hide_control_panel()
                elif (delta_y < -distance_threshold) or (delta_y < -20 and velocity > velocity_threshold):
                    # 向上滑動收起
                    self.hide_control_panel()
                else:
                    # 未達到閾值，回彈到展開位置
                    self.show_control_panel()
            else:
                # 面板未展開 - 向下拉出
                should_show = (delta_y > distance_threshold) or (delta_y > 20 and velocity > velocity_threshold)
                if should_show:
                    self.show_control_panel()
                else:
                    # 未達到閾值，回彈到關閉位置
                    self.hide_control_panel()
            
            # 重置狀態
            self.panel_touch_start = None
            self.panel_drag_active = False
            return
        
        # 處理卡片切換滑動
        if self.is_swiping and self.touch_start_pos is not None:
            # 計算滑動距離和方向
            end_pos = a0.position().toPoint()
            delta = end_pos - self.touch_start_pos
            
            # 根據滑動方向和區域處理
            if self.swipe_area == 'left':
                # 左側區域：只支援左右滑動切換卡片
                if self.swipe_direction == 'horizontal' and abs(delta.x()) > self.swipe_threshold:
                    if delta.x() > 0:
                        # 向右滑動 - 切換到上一張卡片
                        self.switch_left_card(-1)
                    else:
                        # 向左滑動 - 切換到下一張卡片
                        self.switch_left_card(1)
            elif self.swipe_area == 'right':
                # 右側區域：支援左右滑動切換卡片，上下滑動切換列
                if self.swipe_direction == 'horizontal':
                    # 左右滑動 - 切換卡片
                    if abs(delta.x()) > self.swipe_threshold:
                        if delta.x() > 0:
                            # 向右滑動 - 切換到上一張卡片
                            self.switch_card(-1)
                        else:
                            # 向左滑動 - 切換到下一張卡片
                            self.switch_card(1)
                elif self.swipe_direction == 'vertical':
                    # 上下滑動 - 切換列
                    if abs(delta.y()) > self.swipe_threshold:
                        if delta.y() > 0:
                            # 向下滑動 - 切換到上一列
                            self.switch_row(-1)
                        else:
                            # 向上滑動 - 切換到下一列
                            self.switch_row(1)
            
            # 重置狀態
            self.touch_start_pos = None
            self.is_swiping = False
            self.swipe_direction = None
            self.swipe_area = None
    
    @perf_track
    def switch_row(self, direction):
        """切換列（右側卡片區域）
        Args:
            direction: 1 為下一列，-1 為上一列
        """
        # 如果動畫中，不處理
        if self._right_row_animating:
            return
        
        # 停止門狀態自動回退計時器（因為使用者手動切換）
        if hasattr(self, 'door_auto_switch_timer'):
            self.door_auto_switch_timer.stop()
        
        total_rows = len(self.rows)
        old_row_index = self.current_row_index
        new_row_index = (self.current_row_index + direction) % total_rows
        
        if old_row_index == new_row_index:
            return
        
        # 使用動畫切換列
        self._animate_row_switch(old_row_index, new_row_index, direction)
        
        # 顯示提示
        row_names = ["第一列 (音樂/門)", "第二列 (Trip/ODO)"]
        print(f"切換到: {row_names[new_row_index]}")
    
    @perf_track
    def switch_card(self, direction):
        """切換當前列的卡片（右側）
        Args:
            direction: 1 為下一張，-1 為上一張
        """
        # 如果動畫中，不處理
        if self._right_card_animating:
            return
        
        # 停止門狀態自動回退計時器（因為使用者手動切換）
        if hasattr(self, 'door_auto_switch_timer'):
            self.door_auto_switch_timer.stop()
        
        # 獲取當前列的卡片總數
        current_row_cards = self.row_card_counts[self.current_row_index]
        old_card_index = self.current_card_index
        new_card_index = (self.current_card_index + direction) % current_row_cards
        
        if old_card_index == new_card_index:
            return
        
        # 使用動畫切換卡片
        self._animate_card_switch(old_card_index, new_card_index, direction)
        
        # 顯示提示
        row1_card_names = ["音樂播放器", "門狀態"]
        row2_card_names = ["Trip卡片", "ODO卡片"]
        all_card_names = [row1_card_names, row2_card_names]
        
        card_name = all_card_names[self.current_row_index][new_card_index]
        print(f"切換到: {card_name}")
    
    def _switch_left_card_forward(self):
        """向前切換左側卡片（跳過詳細視圖）"""
        # 如果在詳細視圖中或動畫中，不處理
        if self._in_detail_view or self._left_card_animating:
            return
        
        current = self.left_card_stack.currentIndex()
        # 左側卡片只有兩張可切換：0=四宮格, 2=油量（1=詳細視圖跳過）
        if current == 0:
            next_index = 2
        else:
            next_index = 0
        
        # 使用動畫切換
        self._animate_left_card_switch(current, next_index, direction=1)
        
        left_card_names = {0: "引擎監控", 2: "油量"}
        print(f"左側切換到: {left_card_names.get(next_index, '未知')}")
    
    @perf_track
    def switch_left_card(self, direction):
        """切換左側卡片（四宮格/油量）
        Args:
            direction: 1 為下一張，-1 為上一張
        """
        # 如果在詳細視圖中或動畫中，不處理
        if self._in_detail_view or self._left_card_animating:
            return
        
        # 清除四宮格焦點
        if hasattr(self, 'quad_gauge_card'):
            self.quad_gauge_card.clear_focus()
        
        current = self.left_card_stack.currentIndex()
        # 左側卡片只有兩張可切換：0=四宮格, 2=油量（1=詳細視圖跳過）
        valid_indices = [0, 2]
        try:
            current_pos = valid_indices.index(current)
        except ValueError:
            current_pos = 0
        
        next_pos = (current_pos + direction) % len(valid_indices)
        next_index = valid_indices[next_pos]
        
        # 使用動畫切換
        self._animate_left_card_switch(current, next_index, direction)
        
        left_card_names = {0: "引擎監控", 2: "油量"}
        print(f"左側切換到: {left_card_names.get(next_index, '未知')}")
    
    def _animate_left_card_switch(self, from_index, to_index, direction):
        """動畫切換左側卡片
        Args:
            from_index: 當前卡片索引
            to_index: 目標卡片索引
            direction: 1 向下/向左滑出，-1 向上/向右滑出
        """
        if from_index == to_index:
            return
        
        self._left_card_animating = True
        
        # 獲取卡片 widget
        from_widget = self.left_card_stack.widget(from_index)
        to_widget = self.left_card_stack.widget(to_index)
        
        stack_width = self.left_card_stack.width()
        
        # 設定動畫方向：direction=1 向左滑出，direction=-1 向右滑出
        slide_offset = stack_width if direction > 0 else -stack_width
        
        # 準備目標卡片
        to_widget.setGeometry(0, 0, stack_width, self.left_card_stack.height())
        to_widget.move(slide_offset, 0)  # 從螢幕外開始
        to_widget.show()
        to_widget.raise_()
        
        # 當前卡片滑出動畫
        self._left_out_anim = QPropertyAnimation(from_widget, b"pos")
        self._left_out_anim.setDuration(200)
        self._left_out_anim.setStartValue(from_widget.pos())
        self._left_out_anim.setEndValue(QPoint(-slide_offset, 0))
        self._left_out_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # 目標卡片滑入動畫
        self._left_in_anim = QPropertyAnimation(to_widget, b"pos")
        self._left_in_anim.setDuration(200)
        self._left_in_anim.setStartValue(QPoint(slide_offset, 0))
        self._left_in_anim.setEndValue(QPoint(0, 0))
        self._left_in_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # 動畫完成後切換
        def on_animation_finished():
            self.left_card_stack.setCurrentIndex(to_index)
            self.current_left_index = to_index
            self._update_left_indicators()
            # 重設位置
            from_widget.move(0, 0)
            to_widget.move(0, 0)
            self._left_card_animating = False
        
        self._left_in_anim.finished.connect(on_animation_finished)
        
        # 啟動動畫
        self._left_out_anim.start()
        self._left_in_anim.start()
    
    def _animate_card_switch(self, from_index, to_index, direction):
        """動畫切換右側列內的卡片（左右滑動）
        Args:
            from_index: 當前卡片索引
            to_index: 目標卡片索引
            direction: 1 向左滑出，-1 向右滑出
        """
        if from_index == to_index:
            return
        
        self._right_card_animating = True
        
        current_row = self.rows[self.current_row_index]
        from_widget = current_row.widget(from_index)
        to_widget = current_row.widget(to_index)
        
        stack_width = current_row.width()
        
        # 設定動畫方向：direction=1 向左滑出，direction=-1 向右滑出
        slide_offset = stack_width if direction > 0 else -stack_width
        
        # 準備目標卡片
        to_widget.setGeometry(0, 0, stack_width, current_row.height())
        to_widget.move(slide_offset, 0)
        to_widget.show()
        to_widget.raise_()
        
        # 當前卡片滑出動畫
        self._card_out_anim = QPropertyAnimation(from_widget, b"pos")
        self._card_out_anim.setDuration(200)
        self._card_out_anim.setStartValue(from_widget.pos())
        self._card_out_anim.setEndValue(QPoint(-slide_offset, 0))
        self._card_out_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # 目標卡片滑入動畫
        self._card_in_anim = QPropertyAnimation(to_widget, b"pos")
        self._card_in_anim.setDuration(200)
        self._card_in_anim.setStartValue(QPoint(slide_offset, 0))
        self._card_in_anim.setEndValue(QPoint(0, 0))
        self._card_in_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # 動畫完成後切換
        def on_card_animation_finished():
            self.current_card_index = to_index
            current_row.setCurrentIndex(to_index)
            self.update_indicators()
            # 重設位置
            from_widget.move(0, 0)
            to_widget.move(0, 0)
            self._right_card_animating = False
        
        self._card_in_anim.finished.connect(on_card_animation_finished)
        
        # 啟動動畫
        self._card_out_anim.start()
        self._card_in_anim.start()
    
    def _animate_row_switch(self, from_row, to_row, direction):
        """動畫切換右側的列（上下滑動）
        Args:
            from_row: 當前列索引
            to_row: 目標列索引
            direction: 1 向上滑出，-1 向下滑出
        """
        if from_row == to_row:
            return
        
        self._right_row_animating = True
        
        from_widget = self.row_stack.widget(from_row)
        to_widget = self.row_stack.widget(to_row)
        
        # 在動畫開始前，先將目標列設為第一張卡片（避免閃現問題）
        self.rows[to_row].setCurrentIndex(0)
        
        stack_height = self.row_stack.height()
        
        # 設定動畫方向：direction=1 向上滑出，direction=-1 向下滑出
        slide_offset = stack_height if direction > 0 else -stack_height
        
        # 準備目標列
        to_widget.setGeometry(0, 0, self.row_stack.width(), stack_height)
        to_widget.move(0, slide_offset)
        to_widget.show()
        to_widget.raise_()
        
        # 當前列滑出動畫
        self._row_out_anim = QPropertyAnimation(from_widget, b"pos")
        self._row_out_anim.setDuration(200)
        self._row_out_anim.setStartValue(from_widget.pos())
        self._row_out_anim.setEndValue(QPoint(0, -slide_offset))
        self._row_out_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # 目標列滑入動畫
        self._row_in_anim = QPropertyAnimation(to_widget, b"pos")
        self._row_in_anim.setDuration(200)
        self._row_in_anim.setStartValue(QPoint(0, slide_offset))
        self._row_in_anim.setEndValue(QPoint(0, 0))
        self._row_in_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # 動畫完成後切換
        def on_row_animation_finished():
            self.current_row_index = to_row
            self.row_stack.setCurrentIndex(to_row)
            # 切換列時，重置卡片索引為該列的第一張
            self.current_card_index = 0
            self.rows[to_row].setCurrentIndex(0)
            self.update_indicators()
            # 重設位置
            from_widget.move(0, 0)
            to_widget.move(0, 0)
            self._right_row_animating = False
        
        self._row_in_anim.finished.connect(on_row_animation_finished)
        
        # 啟動動畫
        self._row_out_anim.start()
        self._row_in_anim.start()
    
    def wheelEvent(self, a0):  # type: ignore
        """滑鼠滾輪切換卡片（桌面使用）"""
        if a0 is None:
            return
        pos = a0.position().toPoint()
        delta = a0.angleDelta().y()
        modifiers = a0.modifiers()
        
        # 檢查滑鼠是否在左側區域
        if self.left_card_stack.geometry().contains(pos):
            # 滾輪切換左側卡片
            if delta > 0:  # 向上滾動
                self.switch_left_card(-1)
            else:  # 向下滾動
                self.switch_left_card(1)
            return
        
        # 檢查滑鼠是否在右側區域
        if self.row_stack.geometry().contains(pos):
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                # Shift + 滾輪：切換列
                if delta > 0:  # 向上滾動
                    self.switch_row(-1)
                else:  # 向下滾動
                    self.switch_row(1)
            else:
                # 普通滾輪：切換卡片
                if delta > 0:  # 向上滾動
                    self.switch_card(-1)
                else:  # 向下滾動
                    self.switch_card(1)
    
    # === 四宮格詳細視圖管理 ===
    def _show_gauge_detail(self, gauge_index):
        """顯示四宮格的詳細視圖（帶滑入動畫）"""
        self._in_detail_view = True
        self._detail_gauge_index = gauge_index
        
        # 獲取儀表數據並設置到詳細視圖
        data = self.quad_gauge_card.get_gauge_data(gauge_index)
        self.quad_gauge_detail.set_gauge_data(data)
        
        # 準備動畫：詳細視圖從右側滑入
        self.quad_gauge_detail.setGeometry(380, 0, 380, 380)  # 起始位置在右側
        self.left_card_stack.setCurrentWidget(self.quad_gauge_detail)
        
        # 創建滑入動畫
        self._detail_anim = QPropertyAnimation(self.quad_gauge_detail, b"geometry")
        self._detail_anim.setDuration(200)  # 200ms
        self._detail_anim.setStartValue(QRectF(380, 0, 380, 380))
        self._detail_anim.setEndValue(QRectF(0, 0, 380, 380))
        self._detail_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._detail_anim.start()
        
        # 隱藏指示器（因為在詳細視圖中）
        for indicator in self.left_indicators:
            indicator.setVisible(False)
        
        # 禁用滑動
        self.set_swipe_enabled(False)
        
        gauge_names = ["轉速", "水溫", "渦輪負壓", "電瓶電壓"]
        print(f"進入 {gauge_names[gauge_index]} 詳細視圖")
    
    def _hide_gauge_detail(self):
        """隱藏詳細視圖，返回四宮格（帶滑出動畫）"""
        # 創建滑出動畫：詳細視圖滑向右側
        self._detail_anim = QPropertyAnimation(self.quad_gauge_detail, b"geometry")
        self._detail_anim.setDuration(200)  # 200ms
        self._detail_anim.setStartValue(QRectF(0, 0, 380, 380))
        self._detail_anim.setEndValue(QRectF(380, 0, 380, 380))
        self._detail_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # 動畫結束後切換回四宮格
        self._detail_anim.finished.connect(self._on_hide_detail_finished)
        self._detail_anim.start()
    
    def _on_hide_detail_finished(self):
        """詳細視圖滑出動畫完成"""
        self._in_detail_view = False
        self._detail_gauge_index = -1
        
        # 清除四宮格焦點
        self.quad_gauge_card.clear_focus()
        
        # 切換回四宮格
        self.left_card_stack.setCurrentWidget(self.quad_gauge_card)
        
        # 恢復詳細視圖位置（為下次動畫準備）
        self.quad_gauge_detail.setGeometry(0, 0, 380, 380)
        
        # 恢復指示器
        for indicator in self.left_indicators:
            indicator.setVisible(True)
        self._update_left_indicators()
        
        # 恢復滑動
        self.set_swipe_enabled(True)
        
        print("返回四宮格視圖")
    
    def _update_left_indicators(self):
        """更新左側卡片指示器"""
        current_index = self.left_card_stack.currentIndex()
        # 詳細視圖(index 1)時不更新指示器
        if current_index == 1:  # 詳細視圖
            return
        
        # index 0 = 四宮格, index 2 = 油量
        # 映射: 0 -> 0, 2 -> 1
        indicator_index = 0 if current_index == 0 else 1
        
        for i, indicator in enumerate(self.left_indicators):
            if i == indicator_index:
                indicator.setStyleSheet("color: #6af; font-size: 18px;")
            else:
                indicator.setStyleSheet("color: #444; font-size: 18px;")
    
    # === GPIO 按鈕接口（預留給樹莓派 GPIO）===
    def on_button_a_pressed(self):
        """
        按鈕 A 被按下 - 切換左側卡片或焦點
        
        用途：
        - 在四宮格卡片時：切換焦點（轉速 -> 水溫 -> 渦輪 -> 電瓶 -> 下一張卡片）
        - 其他卡片：直接切換
        - 在詳細視圖時：不做任何事
        
        接口預留：
        - 可從 GPIO 按鈕回調呼叫此方法
        - 也可從鍵盤（F1 鍵）觸發
        """
        # 如果在詳細視圖中，不處理
        if self._in_detail_view:
            print("在詳細視圖中，按鈕A不作用")
            return
        
        # 檢查是否在四宮格卡片上（左側卡片的 index 0）
        if self.left_card_stack.currentIndex() == 0:
            # 在四宮格卡片上，使用焦點機制
            if self.quad_gauge_card.next_focus():
                # 還在四宮格卡片內
                gauge_names = ["", "轉速", "水溫", "渦輪負壓", "電瓶電壓"]
                focus = self.quad_gauge_card.get_focus()
                print(f"按鈕A切換焦點到: {gauge_names[focus]}")
                return
            # 焦點循環完畢，切換到下一張卡片
        
        # 清除四宮格焦點
        if hasattr(self, 'quad_gauge_card'):
            self.quad_gauge_card.clear_focus()
        
        # 切換左側卡片
        self._switch_left_card_forward()
    
    def on_button_a_long_pressed(self):
        """
        按鈕 A 長按 - 進入/退出四宮格詳細視圖
        
        用途：
        - 在四宮格有焦點時：進入該儀表的詳細視圖
        - 在詳細視圖時：退出返回四宮格
        
        接口預留：
        - 可從 GPIO 按鈕長按回調呼叫此方法
        - 也可從鍵盤（Shift+F1）觸發
        """
        # 如果在詳細視圖中，長按返回
        if self._in_detail_view:
            self._hide_gauge_detail()
            return
        
        # 如果在四宮格卡片上且有焦點，進入詳細視圖
        if self.left_card_stack.currentIndex() == 0:
            if self.quad_gauge_card.get_focus() > 0:
                self.quad_gauge_card.enter_detail_view()
                return
        
        print("長按按鈕A: 不在四宮格焦點狀態，忽略")
    
    def on_button_b_pressed(self):
        """
        按鈕 B 短按 - 翻右邊卡片頁面（跨列循環，支援 Trip 焦點）
        
        用途：
        - 在 Trip 卡片時：Trip 1 -> Trip 2 -> 下一張卡片
        - 其他卡片：直接跳到下一張
        - 循環順序：音樂 -> 門狀態 -> Trip(1) -> Trip(2) -> ODO -> 音樂...
        
        接口預留：
        - 可從 GPIO 按鈕回調呼叫此方法
        - 也可從鍵盤（F2 鍵）觸發
        """
        # 如果動畫中，不處理
        if self._right_card_animating or self._right_row_animating:
            return
        
        # 停止門狀態自動回退計時器（因為使用者手動切換）
        if hasattr(self, 'door_auto_switch_timer'):
            self.door_auto_switch_timer.stop()
        
        # 檢查是否在 Trip 卡片上（第二列的第一張）
        TRIP_ROW_INDEX = 1
        TRIP_CARD_INDEX = 0
        
        if self.current_row_index == TRIP_ROW_INDEX and self.current_card_index == TRIP_CARD_INDEX:
            # 在 Trip 卡片上，使用焦點機制
            if self.trip_card.next_focus():
                # 還在 Trip 卡片內（Trip 1 或 Trip 2）
                focus_names = ["", "Trip 1", "Trip 2"]
                print(f"按鈕B切換焦點到: {focus_names[self.trip_card.get_focus()]}")
                return
            # 否則繼續到下一張卡片
        
        # 離開 Trip 卡片時清除焦點
        if hasattr(self, 'trip_card'):
            self.trip_card.clear_focus()
        
        # 計算下一張卡片的位置
        current_row_card_count = self.row_card_counts[self.current_row_index]
        next_card_index = self.current_card_index + 1
        
        if next_card_index >= current_row_card_count:
            # 當前列已翻完，跳到下一列的第一張（使用動畫）
            next_row_index = (self.current_row_index + 1) % len(self.rows)
            old_row_index = self.current_row_index
            # 使用動畫切換列
            self._animate_row_switch(old_row_index, next_row_index, 1)
        else:
            # 還在當前列，切換到下一張卡片（使用動畫）
            old_card_index = self.current_card_index
            self._animate_card_switch(old_card_index, next_card_index, 1)
        
        # 顯示提示
        row1_card_names = ["音樂播放器", "門狀態"]
        row2_card_names = ["Trip卡片", "ODO卡片"]
        all_card_names = [row1_card_names, row2_card_names]
        # 動畫結束後才會更新索引，所以這裡用計算的值
        if next_card_index >= current_row_card_count:
            next_row = (self.current_row_index + 1) % len(self.rows)
            card_name = all_card_names[next_row][0]
        else:
            card_name = all_card_names[self.current_row_index][next_card_index]
        print(f"按鈕B切換到: {card_name}")
    
    def on_button_b_long_pressed(self):
        """
        按鈕 B 長按 - 重置當前焦點的 Trip
        
        用途：
        - 在 Trip 卡片有焦點時，長按可清空該 Trip
        
        接口預留：
        - 可從 GPIO 按鈕長按回調呼叫此方法
        - 也可從鍵盤（Shift+F2）觸發
        """
        # 檢查是否在 Trip 卡片上且有焦點
        TRIP_ROW_INDEX = 1
        TRIP_CARD_INDEX = 0
        
        if (self.current_row_index == TRIP_ROW_INDEX and 
            self.current_card_index == TRIP_CARD_INDEX and
            hasattr(self, 'trip_card') and
            self.trip_card.get_focus() > 0):
            
            focus_names = ["", "Trip 1", "Trip 2"]
            focus = self.trip_card.get_focus()
            
            if self.trip_card.reset_focused_trip():
                print(f"長按按鈕B: 已重置 {focus_names[focus]}")
            return
        
        print("長按按鈕B: 不在 Trip 焦點狀態，忽略")
    
    def keyPressEvent(self, a0):  # type: ignore
        """鍵盤模擬控制"""
        if a0 is None:
            return
        key = a0.key()
        
        # ESC 或 P 鍵：切換控制面板
        if key == Qt.Key.Key_Escape or key == Qt.Key.Key_P:
            if self.panel_visible:
                self.hide_control_panel()
            else:
                self.show_control_panel()
            return
        
        # F12 或 Ctrl+W：開啟 WiFi 管理器
        if key == Qt.Key.Key_F12 or (a0.key() == Qt.Key.Key_W and 
                                      a0.modifiers() == Qt.KeyboardModifier.ControlModifier):
            self.show_wifi_manager()
            return
        
        # === GPIO 按鈕模擬（F1/F2 鍵）===
        # F1: 翻左邊卡片（對應按鈕 A）
        if key == Qt.Key.Key_F1:
            if a0.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+F1: 長按按鈕 A（進入/退出詳細視圖）
                self.on_button_a_long_pressed()
            else:
                # F1: 短按按鈕 A（切換左側卡片/焦點）
                self.on_button_a_pressed()
            return
        # F2: 翻右邊卡片（對應按鈕 B 短按）
        elif key == Qt.Key.Key_F2:
            if a0.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+F2: 長按按鈕 B（重置 Trip）
                self.on_button_b_long_pressed()
            else:
                # F2: 短按按鈕 B（切換卡片/焦點）
                self.on_button_b_pressed()
            return
        
        # 上下方向鍵切換列
        if key == Qt.Key.Key_Up:
            self.switch_row(-1)
            return
        elif key == Qt.Key.Key_Down:
            self.switch_row(1)
            return
        # 左右方向鍵切換卡片
        elif key == Qt.Key.Key_Left:
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
        
        # 7/8/9/0/-: 門狀態測試
        elif key == Qt.Key.Key_7:
            # 左前門切換
            if hasattr(self, 'door_card'):
                new_state = not self.door_card.door_fl_closed
                self.set_door_status("FL", new_state)
        elif key == Qt.Key.Key_8:
            # 右前門切換
            if hasattr(self, 'door_card'):
                new_state = not self.door_card.door_fr_closed
                self.set_door_status("FR", new_state)
        elif key == Qt.Key.Key_9:
            # 左後門切換
            if hasattr(self, 'door_card'):
                new_state = not self.door_card.door_rl_closed
                self.set_door_status("RL", new_state)
        elif key == Qt.Key.Key_0:
            # 右後門切換
            if hasattr(self, 'door_card'):
                new_state = not self.door_card.door_rr_closed
                self.set_door_status("RR", new_state)
        elif key == Qt.Key.Key_Minus:
            # 尾門切換
            if hasattr(self, 'door_card'):
                new_state = not self.door_card.door_bk_closed
                self.set_door_status("BK", new_state)
        
        # V: 定速巡航開關切換
        elif key == Qt.Key.Key_V:
            self.toggle_cruise_switch()
        # B: 定速巡航作動切換
        elif key == Qt.Key.Key_B:
            self.toggle_cruise_engaged()

        self.update_display()

    def toggle_cruise_switch(self):
        """切換定速巡航開關（V 鍵）"""
        self.cruise_switch = not self.cruise_switch
        if not self.cruise_switch:
            self.cruise_engaged = False
        self.update_cruise_display()
        print(f"定速巡航開關: {'開' if self.cruise_switch else '關'}")
    
    def toggle_cruise_engaged(self):
        """切換定速巡航作動（B 鍵）"""
        if self.cruise_switch:  # 只有開關開啟時才能作動
            self.cruise_engaged = not self.cruise_engaged
            self.update_cruise_display()
            print(f"定速巡航作動: {'是' if self.cruise_engaged else '否'}")
    
    def set_cruise(self, cruise_switch: bool, cruise_engaged: bool):
        """設定巡航狀態（從 CAN 訊號）"""
        self.cruise_switch = cruise_switch
        self.cruise_engaged = cruise_engaged
        self.update_cruise_display()
    
    def set_turbo(self, turbo_bar: float):
        """設定渦輪增壓值（從 OBD 訊號）
        Args:
            turbo_bar: 增壓值 (bar)，負值為真空/負壓，正值為增壓
        """
        self.turbo = turbo_bar
        # 更新四宮格卡片
        if hasattr(self, 'quad_gauge_card'):
            self.quad_gauge_card.set_turbo(turbo_bar)
        # 如果在詳細視圖中且顯示的是 TURBO，也更新
        if self._in_detail_view and self._detail_gauge_index == 2:
            self.quad_gauge_detail.set_value(turbo_bar)
    
    def set_battery(self, voltage: float):
        """設定電瓶電壓（從 OBD 訊號）
        Args:
            voltage: 電壓值 (V)
        """
        self.battery = voltage
        # 更新四宮格卡片
        if hasattr(self, 'quad_gauge_card'):
            self.quad_gauge_card.set_battery(voltage)
        # 如果在詳細視圖中且顯示的是 BATTERY，也更新
        if self._in_detail_view and self._detail_gauge_index == 3:
            self.quad_gauge_detail.set_value(voltage)
    
    def update_cruise_display(self):
        """更新巡航顯示 - 三種狀態"""
        if not self.cruise_switch:
            # 不顯示
            self.cruise_label.setText("")
        elif self.cruise_engaged:
            # 綠色 - 作動中
            self.cruise_label.setText("CRUISE")
            self.cruise_label.setStyleSheet("""
                color: #4ade80;
                font-size: 40px;
                font-weight: bold;
                font-family: Arial;
                background: transparent;
                letter-spacing: 2px;
            """)
        else:
            # 白色 - 待命
            self.cruise_label.setText("CRUISE")
            self.cruise_label.setStyleSheet("""
                color: #ffffff;
                font-size: 40px;
                font-weight: bold;
                font-family: Arial;
                background: transparent;
                letter-spacing: 2px;
            """)

    def update_display(self):
        """更新所有儀表顯示"""
        # 更新四宮格卡片
        # rpm 是以「千轉」為單位 (0-8)，轉換為實際轉速
        self.quad_gauge_card.set_rpm(self.rpm * 1000)
        
        # temp 是百分比 (0-100)，轉換為大約的攝氏溫度
        # 假設 0% = 40°C, 100% = 120°C
        temp_celsius = 40 + (self.temp / 100) * 80
        self.quad_gauge_card.set_coolant_temp(temp_celsius)
        
        # 如果在詳細視圖中，同步更新
        if self._in_detail_view:
            if self._detail_gauge_index == 0:  # RPM
                self.quad_gauge_detail.update_value(self.rpm * 1000)
            elif self._detail_gauge_index == 1:  # 水溫
                self.quad_gauge_detail.update_value(temp_celsius)
        
        self.fuel_gauge.set_value(self.fuel)
        self.speed_label.setText(str(int(self.speed)))
        
        # 更新檔位顯示顏色
        gear_colors = {
            "P": "#6af",   # 藍色
            "R": "#f66",   # 紅色
            "N": "#fa6",   # 橙色
            "D": "#4ade80",  # 綠色
            "S": "#f6f",   # 紫色
            "L": "#ff6",   # 黃色
        }
        color = gear_colors.get(self.gear, "#6af")
        self.gear_label.setStyleSheet(f"""
            color: {color};
            font-size: 120px;
            font-weight: bold;
            font-family: Arial;
            background: rgba(30, 30, 40, 0.8);
            border: 4px solid #456;
            border-radius: 20px;
        """)
        self.gear_label.setText(self.gear)


class ScalableWindow(QMainWindow):
    """
    可縮放的視窗包裝器 - 用於開發環境按比例縮放儀表板
    保持 1920x480 (4:1) 的比例，方便在電腦上預覽 8.8 吋螢幕效果
    視窗本身也鎖定 4:1 比例
    """
    
    ASPECT_RATIO = 1920 / 480  # 4:1
    
    def __init__(self, dashboard):
        super().__init__()
        self.dashboard = dashboard
        self._resizing = False  # 防止遞迴
        
        # 設定視窗屬性
        self.setWindowTitle("儀表板 - 可縮放預覽（拖曳邊框調整大小）")
        self.setMinimumSize(480, 120)  # 最小 1/4 大小
        
        # 使用 QGraphicsView 來實現縮放
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.view.setStyleSheet("background: #0a0a0f;")
        
        # 將 Dashboard 加入場景
        self.proxy = QGraphicsProxyWidget()
        self.proxy.setWidget(dashboard)
        self.scene.addItem(self.proxy)
        
        self.setCentralWidget(self.view)
        
        # 預設大小（約 8.8 吋螢幕的實際像素密度在一般電腦上的顯示大小）
        # 8.8 吋 1920x480 約等於 218 PPI
        # 一般電腦螢幕約 96-110 PPI，所以約縮放到 45-50%
        initial_width = 960  # 約 50% 大小
        initial_height = int(initial_width / self.ASPECT_RATIO)
        self.resize(initial_width, initial_height)
        
        # 顯示比例資訊
        self._update_scale_info()
    
    def resizeEvent(self, event):
        """視窗大小改變時，強制保持 4:1 比例"""
        if self._resizing:
            return
        
        self._resizing = True
        
        # 取得新的視窗大小
        new_width = event.size().width()
        new_height = event.size().height()
        old_width = event.oldSize().width() if event.oldSize().width() > 0 else new_width
        old_height = event.oldSize().height() if event.oldSize().height() > 0 else new_height
        
        # 判斷是寬度還是高度改變較多，以此決定調整方向
        width_changed = abs(new_width - old_width)
        height_changed = abs(new_height - old_height)
        
        if width_changed >= height_changed:
            # 寬度改變較多，根據寬度調整高度
            corrected_height = int(new_width / self.ASPECT_RATIO)
            corrected_width = new_width
        else:
            # 高度改變較多，根據高度調整寬度
            corrected_width = int(new_height * self.ASPECT_RATIO)
            corrected_height = new_height
        
        # 確保不小於最小尺寸
        if corrected_width < 480:
            corrected_width = 480
            corrected_height = 120
        
        # 如果需要調整，重新設定大小
        if corrected_width != new_width or corrected_height != new_height:
            self.resize(corrected_width, corrected_height)
        
        self._resizing = False
        
        # 更新內容縮放
        super().resizeEvent(event)
        
        # 取得可用區域
        view_width = self.view.viewport().width()
        view_height = self.view.viewport().height()
        
        # 計算縮放比例
        scale = view_width / 1920
        
        # 應用縮放
        transform = QTransform()
        transform.scale(scale, scale)
        self.view.setTransform(transform)
        
        # 置中顯示
        self.view.centerOn(self.proxy)
        
        # 更新比例資訊
        self._update_scale_info()
    
    def showEvent(self, event):
        """視窗顯示時強制更新縮放"""
        super().showEvent(event)
        # 使用 QTimer.singleShot 確保在視窗完全顯示後更新縮放
        QTimer.singleShot(0, self._force_update_scale)
    
    def _force_update_scale(self):
        """強制更新縮放比例"""
        view_width = self.view.viewport().width()
        view_height = self.view.viewport().height()
        
        if view_width <= 0 or view_height <= 0:
            return
        
        # 計算縮放比例
        scale = view_width / 1920
        
        # 應用縮放
        transform = QTransform()
        transform.scale(scale, scale)
        self.view.setTransform(transform)
        
        # 置中顯示
        self.view.centerOn(self.proxy)
        
        # 更新比例資訊
        self._update_scale_info()
    
    def _update_scale_info(self):
        """更新視窗標題顯示當前縮放比例"""
        view_width = self.view.viewport().width()
        scale = view_width / 1920 * 100
        
        # 計算等效螢幕尺寸（假設 96 PPI 的電腦螢幕）
        # 8.8 吋螢幕實際寬度約 195mm，1920 像素
        actual_width_mm = view_width / 96 * 25.4  # 轉換為 mm
        equivalent_inches = actual_width_mm / 25.4
        
        title = f"儀表板預覽 - {scale:.0f}% ({view_width}x{self.view.viewport().height()}) ≈ {equivalent_inches:.1f}吋寬"
        self.setWindowTitle(title)


def run_dashboard(
    on_dashboard_ready=None,
    window_title=None,
    setup_data_source=None
):
    """
    統一的儀表板啟動函數 - 所有入口點都應使用此函數
    
    這個函數處理：
    1. QApplication 初始化
    2. Dashboard 建立
    3. SplashScreen 播放（如果有）
    4. 正確的啟動順序（splash 結束後才啟動 dashboard 邏輯）
    5. 資料來源設定
    
    Args:
        on_dashboard_ready: 可選的回調函數，在 dashboard 完全準備好後呼叫
                           簽名: callback(dashboard) -> cleanup_func 或 None
                           返回的 cleanup_func 會在程式結束時被呼叫
        window_title: 可選的視窗標題
        setup_data_source: 可選的資料來源設定函數
                          簽名: setup_func(dashboard) -> cleanup_func 或 None
                          這個會在 splash 結束後、start_dashboard 之前呼叫
    
    Returns:
        不返回（進入 Qt 事件循環）
    
    使用範例:
        # 最簡單的使用方式（等同於直接執行 main.py）
        run_dashboard()
        
        # Demo 模式
        def setup_demo(dashboard):
            timer = QTimer()
            timer.timeout.connect(lambda: update_data(dashboard))
            timer.start(100)
            return lambda: timer.stop()  # 返回清理函數
        
        run_dashboard(
            window_title="Demo Mode",
            setup_data_source=setup_demo
        )
    """
    app = QApplication(sys.argv)
    
    # 檢測環境
    is_production = is_production_environment()
    env_name = "生產環境（樹莓派）" if is_production else "開發環境（Mac/Windows）"
    print(f"檢測到 {env_name}")
    print(f"系統: {platform.system()}, 全螢幕模式: {'是' if is_production else '否'}")
    
    # 建立主儀表板
    dashboard = Dashboard()
    
    # 開發環境：建立可縮放的視窗包裝器
    scalable_window = None
    if not is_production:
        scalable_window = ScalableWindow(dashboard)
        if window_title:
            scalable_window.setWindowTitle(window_title)
    elif window_title:
        dashboard.setWindowTitle(window_title)
    
    # 用於儲存清理函數
    cleanup_funcs = []
    
    def on_splash_finished():
        """Splash 結束後的統一處理流程"""
        # 1. 關閉 splash（如果有）
        if hasattr(on_splash_finished, 'splash'):
            on_splash_finished.splash.close()
        
        # 2. 顯示主視窗
        if is_production:
            dashboard.showFullScreen()
        else:
            # 開發環境：顯示可縮放視窗
            if scalable_window:
                scalable_window.show()
                print("提示: 開發環境使用可縮放視窗，拖曳邊框可按比例縮放")
                print("      8.8吋螢幕 (1920x480) 約等於視窗寬度 800 像素")
            else:
                dashboard.show()
                print("提示: 開發環境使用視窗模式，可設定環境變數 QTDASHBOARD_FULLSCREEN=1 強制全螢幕")
        
        # 3. 設定資料來源（在 start_dashboard 之前）
        if setup_data_source:
            cleanup = setup_data_source(dashboard)
            if cleanup:
                cleanup_funcs.append(cleanup)
        
        # 4. 啟動儀表板邏輯（這會啟動所有內部 Timer）
        dashboard.start_dashboard()
        
        # 5. 呼叫 ready 回調
        if on_dashboard_ready:
            cleanup = on_dashboard_ready(dashboard)
            if cleanup:
                cleanup_funcs.append(cleanup)
    
    # 檢查是否有啟動影片（優先使用短版）
    has_splash = os.path.exists("Splash_short.mp4")
    
    if has_splash:
        splash = SplashScreen("Splash_short.mp4")
        on_splash_finished.splash = splash
        
        splash.finished.connect(on_splash_finished)
        
        if is_production:
            splash.showFullScreen()
        else:
            splash.resize(800, 200)  # 4:1 比例 (1920x480 影片的縮小版)
            splash.show()
    else:
        print("未找到 Splash_short.mp4，跳過啟動畫面")
        # 沒有 splash，直接執行啟動流程
        on_splash_finished()
    
    # 進入事件循環
    try:
        exit_code = app.exec()
    except KeyboardInterrupt:
        print("\n程式結束")
        exit_code = 0
    finally:
        # 輸出效能報告
        monitor = PerformanceMonitor()
        if monitor.enabled:
            monitor.report()
        
        # 儲存里程資料
        try:
            storage = OdometerStorage()
            storage.save_now()
        except Exception as e:
            print(f"儲存里程資料時發生錯誤: {e}")
        
        # 執行所有清理函數
        for cleanup in cleanup_funcs:
            try:
                cleanup()
            except Exception as e:
                print(f"清理時發生錯誤: {e}")
    
    sys.exit(exit_code)


def main():
    """主程式進入點"""
    run_dashboard()


if __name__ == "__main__":
    main()
