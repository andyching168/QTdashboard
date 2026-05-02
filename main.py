import os
import sys
import time
import platform
import gc
import json
import subprocess
from collections import deque

# === 螢幕電源管理設定 ===
try:
    subprocess.run(['xset', 's', 'off'], capture_output=True)        # 關閉螢幕保護
    subprocess.run(['xset', 's', 'noblank'], capture_output=True)  # 關閉黑屏
    subprocess.run(['xset', '-dpms'], capture_output=True)          # 禁用 DPMS
    print("[Display] 螢幕保護已停用")
except Exception as e:
    print(f"[Display] 設定失敗: {e}")

# === 啟動 CAN Bus 介面（必須在最前面）===
try:
    result = subprocess.run(
        ['ip', '-details', 'link', 'show', 'can0'],
        capture_output=True, text=True, timeout=2
    )
    if result.returncode == 0 and 'can0' in result.stdout:
        subprocess.run(
            ['sudo', 'ip', 'link', 'set', 'can0', 'up', 'type', 'can', 'bitrate', '500000'],
            capture_output=True, timeout=5
        )
        print("[CAN] 介面 can0 已啟動")
except Exception as e:
    print(f"[CAN] 啟動失敗: {e}")

# 專案根目錄
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def get_spotify_config_path():
    return os.path.join(PROJECT_ROOT, "spotify", "spotify_config.json")

def get_spotify_cache_path():
    return os.path.join(PROJECT_ROOT, "spotify", ".spotify_cache")

def get_mqtt_config_path():
    return os.path.join(PROJECT_ROOT, "mqtt_config.json")

from PyQt6.QtWidgets import QWidget, QApplication, QStackedWidget, QStackedLayout, QLabel, QGridLayout, QHBoxLayout, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot, QPoint, QPropertyAnimation, QEasingCurve, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath, QLinearGradient, QKeyEvent

from ui.control_panel import TurnSignalBar, ControlPanel
from ui.mqtt_settings import MQTTSettingsSignals, MQTTSettingsDialog
from ui.telegram_settings import TelegramSettingsDialog
from ui.analog_gauge import AnalogGauge
from ui.gauge_card import DigitalGaugeCard, QuadGaugeCard, QuadGaugeDetailView
from ui.common import GaugeStyle, RadarOverlay, ClickableLabel, MarqueeLabel
from ui.splash_screen import SplashScreen
from ui.door_card import DoorStatusCard
from ui.trip_card import OdometerCard, OdometerCardWide, TripCard, TripCardWide, TripInfoCardWide
from ui.music_card import MusicCard, MusicCardWide
from ui.navigation_card import NavigationCard
from ui.threads import GPSMonitorThread, RadarMonitorThread
from ui.scalable_window import ScalableWindow
from ui.numeric_keypad import NumericKeypad
from ui.theme import get_theme_manager, T, reapply_t_function

from spotify.spotify_auth import SpotifyAuthManager
from spotify.spotify_qr_auth import SpotifyQRAuthDialog
from spotify.spotify_integration import setup_spotify

from navigation.speed_limit import get_speed_limit_loader, query_speed_limit

from hardware.gpio_buttons import setup_gpio_buttons, get_gpio_handler

from core.utils import (
    PerformanceMonitor,
    JankDetector,
    perf_track,
    OdometerStorage,
    is_raspberry_pi,
    is_production_environment,
)

from core.shutdown_monitor import get_shutdown_monitor
from core.max_value_logger import get_max_value_logger
from core.startup_progress import StartupProgressWindow


class Dashboard(QWidget):
    # 定義 Qt Signals，用於從背景執行緒安全地更新 UI
    signal_update_rpm = pyqtSignal(float)
    signal_update_speed = pyqtSignal(float)
    signal_update_temperature = pyqtSignal(float)
    signal_update_fuel = pyqtSignal(float)
    signal_update_gear = pyqtSignal(str)
    signal_update_turn_signal = pyqtSignal(str)  # "left", "right", "both", "off"
    signal_update_turbo = pyqtSignal(float)  # 渦輪增壓 (bar)
    
    # Spotify 相關 Signals
    signal_update_spotify_track = pyqtSignal(str, str, str)
    signal_update_spotify_progress = pyqtSignal(float, float, bool)  # current, total, is_playing
    signal_update_spotify_art = pyqtSignal(object)  # 傳遞 PIL Image 物件
    
    # 導航相關 Signal
    signal_update_navigation = pyqtSignal(dict)  # 傳遞導航資料字典
    
    # 網路狀態 Signal
    signal_update_network = pyqtSignal(bool)  # 傳遞網路狀態 (is_connected)
    
    # 手煞車 Signal
    signal_update_parking_brake = pyqtSignal(bool)  # 傳遞手煞車狀態 (is_engaged)
    
    # 雷達 Signal
    signal_update_radar = pyqtSignal(str)  # 傳遞雷達字串
    
    # 油耗 Signal
    signal_update_fuel_consumption = pyqtSignal(float, float)  # 傳遞油耗 (瞬時 L/100km, 平均 L/100km)
    
    # MQTT telemetry Signal (用於跨執行緒啟動 timer)
    signal_start_mqtt_telemetry = pyqtSignal()

    def __init__(self, skip_gps=False):
        super().__init__()
        
        # === 初始化主題系統（載入強調色設定）===
        _ = get_theme_manager()
        
        # === 禁用 Python 自動 GC ===
        # 在桌面環境下，自動 GC 可能會與桌面合成器競爭資源導致凍結
        # 改由 _incremental_gc() 每 5 分鐘在背景手動執行
        gc.disable()
        print("[GC] 已禁用自動垃圾回收，改為手動控制")
        
        self.setWindowTitle("儀表板 - F1:翻左卡片/焦點 Shift+F1:詳細視圖 F2:翻右卡片 Shift+F2:重置Trip")
        
        # GPS 速度優先邏輯變數 (必須在 init_data 之前初始化)
        self.is_gps_fixed = False
        self.is_using_external_gps = False
        self.is_external_gps_fresh = True
        self.current_gps_speed = 0.0
        self.current_speed_limit = None
        self.current_speed_limit_dual = None  # For "N:XX / S:XX" display
        self.current_bearing = None
        self._skip_gps = skip_gps  # 標記是否跳過 GPS 初始化
        self._speed_limit_flashing = False
        self._speed_limit_timer = 0
        
        # 連接 Signals 到 Slots
        self.signal_update_rpm.connect(self._slot_set_rpm)
        self.signal_update_speed.connect(self._slot_set_speed)
        self.signal_update_temperature.connect(self._slot_set_temperature)
        self.signal_update_fuel.connect(self._slot_set_fuel)
        self.signal_update_gear.connect(self._slot_set_gear)
        self.signal_update_fuel_consumption.connect(self._slot_update_fuel_consumption)
        
        # 連接 Spotify Signals
        self.signal_update_spotify_track.connect(self._slot_update_spotify_track)
        self.signal_update_spotify_progress.connect(self._slot_update_spotify_progress)
        self.signal_update_spotify_art.connect(self._slot_update_spotify_art)
        
        # 連接方向燈 Signal
        self.signal_update_turn_signal.connect(self._slot_update_turn_signal)
        
        # 連接導航 Signal
        self.signal_update_navigation.connect(self._slot_update_navigation)
        
        # 連接網路狀態 Signal
        self.signal_update_network.connect(self._update_network_status)
        
        # 連接手煞車 Signal
        self.signal_update_parking_brake.connect(self._slot_update_parking_brake)
        
        # 連接雷達 Signal
        self.signal_update_radar.connect(self._slot_update_radar)
        
        # 連接主題強調色變更 Signal
        get_theme_manager().accent_color_changed.connect(self._on_accent_color_changed)
        self._last_accent_color = get_theme_manager().accent_color
        
        # 注意：油耗由 trip_info_card 直接從 RPM/Speed/Turbo 信號計算，
        # 不需要從 datagrab.py 接收油號 signal
        
        # 連接 MQTT telemetry Signal
        self.signal_start_mqtt_telemetry.connect(self._start_mqtt_telemetry_timer)
        
        # 適配 1920x480 螢幕
        self.setFixedSize(1920, 480)
        
        # Carbon fiber like background
        self.setStyleSheet(f"""
            QWidget {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {T('BG_DARK')}, stop:0.5 #15151a, stop:1 {T('BG_DARK')});
            }}
        """)
        
        # 下拉面板相關
        self.control_panel = None
        self.panel_animation = None
        self.panel_visible = False
        self.panel_touch_start = None
        self.panel_drag_active = False

        # 速度同步模式（calibrated -> fixed -> gps）
        self.speed_sync_modes = ["calibrated", "fixed", "gps"]
        self.speed_sync_mode = "calibrated"
        
        # 亮度控制相關
        self.brightness_level = 0  # 0=100%, 1=75%, 2=50%
        self.brightness_overlay = None

        self.init_ui()
        self.set_speed_sync_mode(self.speed_sync_mode)
        self.init_data()
        
        # 初始化關機監控器
        self._init_shutdown_monitor()
        
        # 初始化 GPS 監控器
        if skip_gps:
            print("[GPS] 跳過 GPS 初始化（Mock 模式）")
            self.gps_monitor_thread = None
            self.gps_device_found = True  # 假設有裝置
            # 直接設定 GPS 狀態為可用
            self._update_gps_status(True)
            self._update_gps_device(True)
        else:
            self.gps_monitor_thread = GPSMonitorThread()
            self.gps_monitor_thread.gps_fixed_changed.connect(self._update_gps_status)
            self.gps_monitor_thread.gps_speed_changed.connect(self._update_gps_speed)
            self.gps_monitor_thread.gps_position_changed.connect(self._update_gps_position)
            self.gps_monitor_thread.gps_source_changed.connect(self._update_gps_source)
            self.gps_monitor_thread.gps_device_status_changed.connect(self._update_gps_device)
            self.gps_monitor_thread.start()
            self.gps_device_found = None  # None=unknown, True=found, False=not found
        
        # 初始化雷達監控器
        self.radar_monitor_thread = RadarMonitorThread()
        self.radar_monitor_thread.radar_message_received.connect(self._slot_update_radar)
        self.radar_monitor_thread.start()
        
        # 創建亮度覆蓋層（必須在 init_ui 之後，確保在最上層）
        self._create_brightness_overlay()
    
    def _update_gps_status(self, is_fixed):
        """更新 GPS 狀態圖示"""
        self.is_gps_fixed = is_fixed
        self._apply_gps_styles()
        
        # GPS 穩定時啟動速限查詢計時器，否則暫停
        if is_fixed:
            if hasattr(self, 'speed_limit_query_timer') and not self.speed_limit_query_timer.isActive():
                self.speed_limit_query_timer.start()
                print("[SpeedLimit] GPS fixed, starting query timer")
        else:
            if hasattr(self, 'speed_limit_query_timer') and self.speed_limit_query_timer.isActive():
                self.speed_limit_query_timer.stop()
                # 立即隱藏速限
                self.current_speed_limit = None
                self.current_speed_limit_dual = None
                self.speed_limit_label.setText("--")
                self.speed_limit_label.setStyleSheet("""
                    QLabel {
                        color: #888;
                        font-size: 48px;
                        font-weight: bold;
                        background: transparent;
                    }
                """)
                print("[SpeedLimit] GPS lost, stopping query timer")
        
    def _update_gps_source(self, is_internal: bool, is_fresh: bool = True):
        """更新 GPS 來源（內部/外部 MQTT）
        
        Args:
            is_internal: True=內部 GPS, False=外部 MQTT GPS
            is_fresh: 是否為即時位置（僅對外部 GPS 有意義）
        """
        self.is_using_external_gps = not is_internal
        self.is_external_gps_fresh = is_fresh if not is_internal else True
        print(f"[GPS] Source changed: {'Internal' if is_internal else 'External (MQTT)'}, fresh={is_fresh}")
        self._apply_gps_styles()
    
    def _update_gps_device(self, found: bool):
        """更新 GPS 裝置狀態"""
        self.gps_device_found = found
        print(f"[GPS] Device status: {'Found' if found else 'Not found'}")
        self._apply_gps_styles()
    
    def _apply_gps_styles(self):
        """根據 GPS 狀態和來源應用樣式"""
        # 優先判斷：無裝置
        if self.gps_device_found == False:
            self.gps_icon_label.setText("GPS!")
            self.gps_icon_label.setStyleSheet(f"color: {T('GPS_NOT_FOUND')}; font-size: 18px; font-weight: bold; background: transparent;")
            self.gps_icon_label.setToolTip("GPS: 未偵測到裝置")
            self.gps_speed_label.setText("--")
            self.gps_speed_label.setStyleSheet(f"color: {T('GPS_NOT_FOUND')}; font-size: 16px; font-weight: bold; background: transparent;")
        elif self.is_gps_fixed:
            if self.is_using_external_gps:
                if self.is_external_gps_fresh:
                    # 黃色 (External GPS - 即時)
                    self.gps_icon_label.setText("GPS*")
                    self.gps_icon_label.setStyleSheet(f"color: {T('GPS_EXTERNAL_FRESH')}; font-size: 18px; font-weight: bold; background: transparent;")
                    self.gps_icon_label.setToolTip("GPS: External (MQTT) - 即時")
                    self.gps_speed_label.setStyleSheet(f"color: {T('GPS_EXTERNAL_FRESH')}; font-size: 16px; font-weight: bold; background: transparent;")
                else:
                    # 灰色 (External GPS - 過時但可用)
                    self.gps_icon_label.setText("GPS*")
                    self.gps_icon_label.setStyleSheet(f"color: {T('GPS_EXTERNAL_STALE')}; font-size: 18px; font-weight: bold; background: transparent;")
                    self.gps_icon_label.setToolTip("GPS: External (MQTT) - 最後位置")
                    self.gps_speed_label.setStyleSheet(f"color: {T('GPS_EXTERNAL_STALE')}; font-size: 16px; font-weight: bold; background: transparent;")
            else:
                # 綠色 (Internal Fix)
                self.gps_icon_label.setText("GPS")
                self.gps_icon_label.setStyleSheet(f"color: {T('GPS_INTERNAL')}; font-size: 18px; font-weight: bold; background: transparent;")
                self.gps_icon_label.setToolTip("GPS: Fixed (3D)")
                self.gps_speed_label.setStyleSheet(f"color: {T('GPS_INTERNAL')}; font-size: 16px; font-weight: bold; background: transparent;")
        else:
            # 灰色 (No Fix - 搜尋中)
            self.gps_icon_label.setText("GPS")
            self.gps_icon_label.setStyleSheet(f"color: {T('TEXT_DISABLED')}; font-size: 18px; font-weight: bold; background: transparent;")
            self.gps_icon_label.setToolTip("GPS: Searching...")
            self.gps_speed_label.setText("--")
            self.gps_speed_label.setStyleSheet(f"color: {T('TEXT_DISABLED')}; font-size: 16px; font-weight: bold; background: transparent;")
        
        # Force Style Update
        self.gps_icon_label.style().unpolish(self.gps_icon_label)
        self.gps_icon_label.style().polish(self.gps_icon_label)
        self.gps_icon_label.update()

    def _update_gps_speed(self, speed_kmh):
        """更新 GPS 速度"""
        self.current_gps_speed = speed_kmh
        
        # 更新左上角的 GPS 速度顯示
        if self.is_gps_fixed:
            # 檢查是否在校正模式
            import vehicle.datagrab as datagrab
            try:
                calibration_enabled = datagrab.is_speed_calibration_enabled()
            except:
                calibration_enabled = False
            
            if calibration_enabled:
                # 校正模式：顯示速度和校正係數
                correction = datagrab.get_speed_correction()
                self.gps_speed_label.setText(f"{int(speed_kmh)}({correction:.2f})")
                self.gps_speed_label.setFixedWidth(90)  # 加寬以容納校正係數
            else:
                # 一般模式：只顯示速度
                self.gps_speed_label.setText(f"{int(speed_kmh)}")
                self.gps_speed_label.setFixedWidth(50)
        else:
            self.gps_speed_label.setText("--")
            self.gps_speed_label.setFixedWidth(50)
        
        # 檢查是否應該顯示 GPS 速度
        # 條件: 速度同步開啟(datagrab.gps_speed_mode) AND GPS 定位完成 AND OBD速度 >= 20
        import vehicle.datagrab as datagrab
        use_gps = (datagrab.gps_speed_mode and 
                   self.is_gps_fixed and 
                   self.speed >= 20.0)
                   
        if use_gps:
            # 直接更新顯示，覆蓋 CAN 速度
            self.speed_label.setText(f"{int(speed_kmh)}")
    
    def _update_gps_position(self, lat, lon):
        """更新 GPS 座標（速限由計時器每 5 秒查詢一次）"""
        self.gps_lat = lat
        self.gps_lon = lon
    
    def _update_speed_limit(self):
        """根據 GPS 座標更新速限（計時器控制，GPS 不可靠時計時器會停止）"""
        if self.gps_lat is None or self.gps_lon is None:
            return
        
        limit, direction, dual_limits = query_speed_limit(self.gps_lat, self.gps_lon, self.current_bearing)
        
        if limit != self.current_speed_limit or dual_limits != self.current_speed_limit_dual:
            self.current_speed_limit = limit
            self.current_speed_limit_dual = dual_limits
            print(f"[SpeedLimit] 更新速限: {limit} km/h, direction={direction}, dual={dual_limits}")
            self._apply_speed_limit_style()
    
    def _apply_speed_limit_style(self):
        """應用速限標籤樣式"""
        limit = self.current_speed_limit
        dual_limits = self.current_speed_limit_dual
        
        # "--" 或無速限：不顯示
        if limit is None and not dual_limits:
            self.speed_limit_label.hide()
            self.speed_limit_container.hide()
            self._speed_limit_flashing = False
            return
        
        # 處理雙向速限顯示 (N:XX / S:XX)：顯示紅邊白底黑字
        if dual_limits:
            n_speed = dual_limits.get('N', '-')
            s_speed = dual_limits.get('S', '-')
            self.speed_limit_label.setText(f"N:{n_speed} S:{s_speed}")
            self.speed_limit_label.setStyleSheet(f"""
                color: {T('SPEED_LIMIT_TEXT')};
                font-size: 32px;
                font-weight: bold;
                font-family: Arial;
                background: {T('SPEED_LIMIT_BG')};
                border: 4px solid {T('SPEED_LIMIT_BORDER')};
                border-radius: 8px;
                padding: 8px 16px;
            """)
            self.speed_limit_label.show()
            self.speed_limit_container.hide()
            self._speed_limit_flashing = False
            return
        
        # 一般單一速限：顯示圓形
        if limit is None:
            self.speed_limit_label.show()
            self.speed_limit_container.hide()
            self._speed_limit_flashing = False
            return
        
        # 顯示圓形
        self.speed_limit_label.hide()
        
        # 檢查是否超速 (超過速限 10 km/h 以上) - 圓形border已經是紅色
        current_speed = getattr(self, 'speed', 0)
        self._speed_limit_flashing = (current_speed > limit + 10)
        
        # 非閃爍時直接顯示，閃爍時讓計時器處理
        if not self._speed_limit_flashing:
            self.speed_limit_container.show()
        
        self.speed_limit_circle_label.setText(str(limit))
    
    def _update_speed_limit_flash(self):
        """速限閃爍計時器 callback"""
        if not self._speed_limit_flashing:
            return
        
        self._speed_limit_timer += 1
        if self._speed_limit_timer % 10 == 0:  # 每 10 ticks 切換一次 (0.5 秒)
            if self.speed_limit_container.isVisible():
                self.speed_limit_container.hide()
            else:
                self.speed_limit_container.show()
    
    def create_status_bar(self):
        """創建頂部狀態欄，包含方向燈指示"""
        status_bar = QWidget()
        status_bar.setFixedHeight(50)
        status_bar.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {T('BG_STATUS_BAR')}, stop:1 {T('BG_DARK')});
                border-bottom: 2px solid {T('BORDER_DEFAULT')};
            }}
        """)
        
        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # === 左側區域：漸層條（從最左到1/4）+ 圖標疊在上面 ===
        left_container = QWidget()
        left_container.setFixedWidth(480)  # 1920 * 0.25 = 480 (1/4 螢幕寬)
        left_container.setStyleSheet("background: transparent;")
        
        # 漸層條使用 QPainter 實作的 TurnSignalBar
        self.left_gradient_bar = TurnSignalBar("left", left_container)
        self.left_gradient_bar.setGeometry(0, 5, 480, 40)  # 整個左側 1/4 區域
        
        # 左轉燈圖標（疊在條的最左邊上方）
        self.left_turn_indicator = QLabel("⬅", left_container)
        self.left_turn_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.left_turn_indicator.setGeometry(10, 5, 60, 40)
        self.left_turn_indicator.setStyleSheet(f"""
            QLabel {{
                color: {T('TURN_SIGNAL_DIM')};
                font-size: 28px;
                font-weight: bold;
                background: transparent;
                border: 2px solid #000000;
                border-radius: 8px;
            }}
        """)
        # 確保圖標在上層
        self.left_turn_indicator.raise_()
        
        # === 中間區域 - 時間顯示 ===
        center_container = QWidget()
        center_container.setStyleSheet("background: transparent;")
        center_layout = QHBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10) # 間距
        center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 1. 左側 GPS 速度顯示 (與右側 GPS Icon 平衡)
        self.gps_speed_label = QLabel("--")
        self.gps_speed_label.setFixedWidth(50)
        self.gps_speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gps_speed_label.setStyleSheet(f"color: {T('TEXT_DISABLED')}; font-size: 16px; font-weight: bold; background: transparent;")
        self.gps_speed_label.setToolTip("GPS 速度")
        
        # 2. 時間顯示 (中央)
        self.time_label = QLabel("--:--")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet(f"""
            QLabel {{
                color: {T('PRIMARY')};
                font-size: 24px;
                font-weight: bold;
                background: transparent;
                letter-spacing: 2px;
            }}
        """)
        
        # 3. GPS 狀態 (右側)
        self.gps_icon_label = QLabel("GPS") 
        self.gps_icon_label.setFixedWidth(40)
        self.gps_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gps_icon_label.setStyleSheet(f"color: {T('TEXT_DISABLED')}; font-size: 18px; font-weight: bold; background: transparent;")
        self.gps_icon_label.setToolTip("GPS: Searching...")
        
        # 使用 Stretch 確保整體置中
        center_layout.addStretch()
        center_layout.addWidget(self.gps_speed_label)
        center_layout.addWidget(self.time_label)
        center_layout.addWidget(self.gps_icon_label)
        center_layout.addStretch()
        
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
        
        # 漸層條使用 QPainter 實作的 TurnSignalBar
        self.right_gradient_bar = TurnSignalBar("right", right_container)
        self.right_gradient_bar.setGeometry(0, 5, 480, 40)  # 整個右側 1/4 區域
        
        # 右轉燈圖標（疊在條的最右邊上方）
        self.right_turn_indicator = QLabel("➡", right_container)
        self.right_turn_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.right_turn_indicator.setGeometry(410, 5, 60, 40)
        self.right_turn_indicator.setStyleSheet(f"""
            QLabel {{
                color: {T('TURN_SIGNAL_DIM')};
                font-size: 28px;
                font-weight: bold;
                background: transparent;
                border: 2px solid #000000;
                border-radius: 8px;
            }}
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
        """更新漸層動畫效果（優化：只在需要時更新樣式）"""
        # === 靜態開關版本 - 無動畫 ===
        # 直接根據開關狀態設定漸層位置，無漸變效果
        old_left_pos = self.left_gradient_pos
        old_right_pos = self.right_gradient_pos
        old_left_on = getattr(self, '_prev_left_turn_on', None)
        old_right_on = getattr(self, '_prev_right_turn_on', None)
        
        # 左轉燈 - 靜態開關
        if self.left_turn_on:
            self.left_gradient_pos = 1.0  # 開啟時全滿
        else:
            self.left_gradient_pos = 0.0  # 關閉時全暗
        
        # 右轉燈 - 靜態開關
        if self.right_turn_on:
            self.right_gradient_pos = 1.0  # 開啟時全滿
        else:
            self.right_gradient_pos = 0.0  # 關閉時全暗
        
        # 只在狀態實際變更時才更新樣式（避免無謂的 CSS 重解析）
        left_changed = (self.left_gradient_pos != old_left_pos or 
                       self.left_turn_on != old_left_on)
        right_changed = (self.right_gradient_pos != old_right_pos or 
                        self.right_turn_on != old_right_on)
        
        if left_changed or right_changed:
            self._prev_left_turn_on = self.left_turn_on
            self._prev_right_turn_on = self.right_turn_on
            self.update_turn_signal_style()
        
        # === 原始動畫代碼（已註解） ===
        # 如果兩個方向燈都關閉且動畫已完成，跳過更新
        # if (not self.left_turn_on and not self.right_turn_on and 
        #     self.left_gradient_pos <= 0.0 and self.right_gradient_pos <= 0.0):
        #     return
        # 
        # # 熄滅動畫速度
        # fade_speed = 0.05
        # 
        # # 記錄舊的狀態用於比較
        # old_left_pos = self.left_gradient_pos
        # old_right_pos = self.right_gradient_pos
        # old_left_on = getattr(self, '_prev_left_turn_on', None)
        # old_right_on = getattr(self, '_prev_right_turn_on', None)
        # 
        # # 左轉燈動畫
        # if self.left_turn_on:
        #     # 亮起時直接全滿
        #     self.left_gradient_pos = 1.0
        # else:
        #     # 熄滅時從中間向外漸暗
        #     self.left_gradient_pos = max(0.0, self.left_gradient_pos - fade_speed)
        # 
        # # 右轉燈動畫
        # if self.right_turn_on:
        #     # 亮起時直接全滿
        #     self.right_gradient_pos = 1.0
        # else:
        #     # 熄滅時從中間向外漸暗
        #     self.right_gradient_pos = max(0.0, self.right_gradient_pos - fade_speed)
        # 
        # # 只在狀態實際變更時才更新樣式（避免無謂的 CSS 重解析）
        # left_changed = (self.left_gradient_pos != old_left_pos or 
        #                self.left_turn_on != old_left_on)
        # right_changed = (self.right_gradient_pos != old_right_pos or 
        #                 self.right_turn_on != old_right_on)
        # 
        # if left_changed or right_changed:
        #     self._prev_left_turn_on = self.left_turn_on
        #     self._prev_right_turn_on = self.right_turn_on
        #     self.update_turn_signal_style()
    
    def update_turn_signal_style(self):
        """更新方向燈的視覺樣式 - 使用 QPainter 實作，避免 CSS 效能瓶頸"""
        # 方向燈圖標樣式（圖標仍使用 CSS，因為只在狀態改變時更新一次）
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
        
        # === 左轉燈 ===
        # 圖標的亮滅只看 left_turn_on，不受動畫影響
        if self.left_turn_on:
            self.left_turn_indicator.setStyleSheet(indicator_active)
        else:
            self.left_turn_indicator.setStyleSheet(indicator_inactive)
        
        # 漸層條使用 QPainter 繪製，直接設定 gradient_pos
        self.left_gradient_bar.set_gradient_pos(self.left_gradient_pos)
        
        # === 右轉燈 ===
        # 圖標的亮滅只看 right_turn_on，不受動畫影響
        if self.right_turn_on:
            self.right_turn_indicator.setStyleSheet(indicator_active)
        else:
            self.right_turn_indicator.setStyleSheet(indicator_inactive)
        
        # 漸層條使用 QPainter 繪製，直接設定 gradient_pos
        self.right_gradient_bar.set_gradient_pos(self.right_gradient_pos)

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
        self.fuel_gauge.setFixedSize(340, 340)

        # 油量卡片容器，附加百分比文字
        self.fuel_card = QWidget()
        fuel_layout = QVBoxLayout(self.fuel_card)
        fuel_layout.setContentsMargins(0, 0, 0, 0)
        fuel_layout.setSpacing(6)
        fuel_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fuel_percent_label = QLabel("--%")
        self.fuel_percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fuel_percent_label.setStyleSheet("color: #6af; font-size: 28px; font-weight: bold; background: transparent;")
        fuel_layout.addWidget(self.fuel_gauge, alignment=Qt.AlignmentFlag.AlignCenter)
        fuel_layout.addWidget(self.fuel_percent_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.fuel_card.setFixedSize(380, 380)
        
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
        self.left_card_stack.addWidget(self.fuel_card)          # index 2
        
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
        
        # === 上方：手煞車 + CRUISE 顯示區 ===
        indicator_row = QWidget()
        indicator_row.setFixedHeight(50)
        indicator_row.setStyleSheet("background: transparent;")
        indicator_row_layout = QHBoxLayout(indicator_row)
        indicator_row_layout.setContentsMargins(0, 0, 0, 0)
        indicator_row_layout.setSpacing(0)
        
        # 手煞車指示器（左側，固定寬度並置中）
        parking_brake_container = QWidget()
        parking_brake_container.setFixedWidth(80)
        parking_brake_container.setStyleSheet("background: transparent;")
        parking_brake_layout = QHBoxLayout(parking_brake_container)
        parking_brake_layout.setContentsMargins(0, 0, 0, 0)
        parking_brake_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.parking_brake_label = QLabel("")
        self.parking_brake_label.setFixedSize(50, 50)
        self.parking_brake_label.setStyleSheet(f"""
            color: {T('PARKING_BRAKE')};
            font-size: 28px;
            font-weight: bold;
            font-family: Arial;
            background: transparent;
        """)
        self.parking_brake_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        parking_brake_layout.addWidget(self.parking_brake_label)
        
        # CRUISE 指示器（右側）
        self.cruise_label = QLabel("")
        self.cruise_label.setStyleSheet(f"""
            color: {T('SUCCESS')};
            font-size: 40px;
            font-weight: bold;
            font-family: Arial;
            background: transparent;
            letter-spacing: 3px;
        """)
        self.cruise_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        indicator_row_layout.addWidget(parking_brake_container)
        indicator_row_layout.addWidget(self.cruise_label, 1)
        
        # === 中央：檔位(左) + 時速(右) ===
        speed_gear_widget = QWidget()
        speed_gear_widget.setStyleSheet("background: transparent;")
        speed_gear_layout = QHBoxLayout(speed_gear_widget)
        speed_gear_layout.setContentsMargins(0, 0, 0, 0)
        speed_gear_layout.setSpacing(10)
        speed_gear_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        # 檔位顯示（左側）- 可點擊切換顯示模式
        self.gear_label = ClickableLabel("P")
        self.gear_label.setStyleSheet(f"""
            color: {T('SUCCESS')};
            font-size: 120px;
            font-weight: bold;
            font-family: Arial;
            background: rgba(30, 30, 40, 0.8);
            border: 4px solid #456;
            border-radius: 20px;
        """)
        self.gear_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gear_label.setFixedSize(140, 180)
        self.gear_label.clicked.connect(self._toggle_gear_display_mode)
        
        # 時速區域（右側）
        speed_container = QWidget()
        speed_container.setStyleSheet("background: transparent;")
        speed_layout = QVBoxLayout(speed_container)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(0)
        
        # 速度數字
        self.speed_label = QLabel("0")
        self.speed_label.setStyleSheet(f"""
            color: {T('TEXT_PRIMARY')};
            font-size: 140px;
            font-weight: bold;
            font-family: 'Arial', 'Helvetica', sans-serif;
            background: transparent;
        """)
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_label.setFixedWidth(300)  # 固定寬度確保置中穩定
        
        # 單位標籤
        self.unit_label = QLabel("Km/h")
        self.unit_label.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 28px;
            font-family: Arial;
            background: transparent;
        """)
        self.unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_label.setFixedWidth(300)  # 與時速同寬確保置中
        
        # 速限標籤
        self.speed_limit_label = QLabel("--")
        self.speed_limit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_limit_label.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 36px;
            font-weight: bold;
            font-family: Arial;
            background: transparent;
        """)
        self.speed_limit_label.hide()
        
        # 速限圓形容器
        self.speed_limit_container = QWidget()
        self.speed_limit_container.setFixedSize(80, 80)
        self.speed_limit_container.setStyleSheet(f"""
            background: {T('SPEED_LIMIT_BG')};
            border: 4px solid {T('SPEED_LIMIT_BORDER')};
            border-radius: 40px;
        """)
        self.speed_limit_container.setToolTip("速限")
        speed_limit_circle_layout = QVBoxLayout(self.speed_limit_container)
        speed_limit_circle_layout.setContentsMargins(0, 0, 0, 0)
        speed_limit_circle_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_limit_circle_label = QLabel("--")
        self.speed_limit_circle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_limit_circle_label.setStyleSheet(f"""
            color: {T('SPEED_LIMIT_TEXT')};
            font-size: 36px;
            font-weight: bold;
            font-family: Arial;
            background: transparent;
            border: none;
        """)
        speed_limit_circle_layout.addWidget(self.speed_limit_circle_label)
        self.speed_limit_container.hide()
        
        speed_layout.addWidget(self.speed_label)
        speed_layout.addWidget(self.unit_label)
        
        speed_gear_layout.addWidget(self.gear_label)
        speed_gear_layout.addWidget(speed_container, 1)
        
        # 速限文字浮動區（疊加在底部，右下角）
        speed_limit_float_widget = QWidget()
        speed_limit_float_widget.setFixedWidth(440)
        speed_limit_float_widget.setStyleSheet("background: transparent;")
        speed_limit_float_layout = QGridLayout(speed_limit_float_widget)
        speed_limit_float_layout.setContentsMargins(0, 0, 0, 0)
        speed_limit_float_layout.setSpacing(0)
        speed_limit_float_layout.addWidget(self.speed_limit_label, 1, 1, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        
        # 速限圓形浮動區（疊加在底部，右下角）
        speed_limit_circle_float_widget = QWidget()
        speed_limit_circle_float_widget.setFixedWidth(440)
        speed_limit_circle_float_widget.setStyleSheet("background: transparent;")
        speed_limit_circle_float_layout = QGridLayout(speed_limit_circle_float_widget)
        speed_limit_circle_float_layout.setContentsMargins(0, 0, 0, 0)
        speed_limit_circle_float_layout.setSpacing(0)
        speed_limit_circle_float_layout.addWidget(self.speed_limit_container, 1, 1, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        
        # 組合中央區域佈局（使用 StackedLayout 實現疊加效果）
        center_stack_layout = QStackedLayout()
        center_stack_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)
        center_stack_layout.addWidget(speed_gear_widget)
        center_stack_layout.addWidget(speed_limit_float_widget)
        center_stack_layout.addWidget(speed_limit_circle_float_widget)
        
        # 疊加層容器
        stack_container = QWidget()
        stack_container.setLayout(center_stack_layout)
        stack_container.setStyleSheet("background: transparent;")
        
        center_layout.addWidget(indicator_row)
        center_layout.addWidget(stack_container, 1)
        
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
        
        # === 第一列：音樂卡片 / 導航卡片 / 門狀態卡片 ===
        row1_cards = QStackedWidget()
        row1_cards.setFixedSize(800, 380)
        
        # 音樂卡片（寬版）
        self.music_card = MusicCardWide()
        self.music_card.request_bind.connect(self.start_spotify_auth)
        
        # 導航卡片（寬版）
        self.nav_card = NavigationCard()
        
        # 門狀態卡片
        self.door_card = DoorStatusCard()
        self.door_card.setFixedSize(800, 380)
        
        row1_cards.addWidget(self.music_card)  # row1_index 0
        row1_cards.addWidget(self.nav_card)    # row1_index 1
        row1_cards.addWidget(self.door_card)   # row1_index 2
        
        # === 第二列：Trip 卡片 / ODO 卡片 / 行程資訊卡片 ===
        row2_cards = QStackedWidget()
        row2_cards.setFixedSize(800, 380)
        
        # Trip 卡片（寬版）
        self.trip_card = TripCardWide()
        row2_cards.addWidget(self.trip_card)  # row2_index 0
        
        # ODO 卡片（寬版）
        self.odo_card = OdometerCardWide()
        row2_cards.addWidget(self.odo_card)  # row2_index 1
        
        # 行程資訊卡片（寬版）- 啟動時間/行駛距離/瞬時油耗/平均油耗
        self.trip_info_card = TripInfoCardWide()
        row2_cards.addWidget(self.trip_info_card)  # row2_index 2
        
        # 連接 RPM、Speed 和 Turbo 信號到行程資訊卡片（用於計算油耗）
        self.signal_update_rpm.connect(self.trip_info_card.update_rpm)
        self.signal_update_speed.connect(self.trip_info_card.update_speed)
        self.signal_update_turbo.connect(self.trip_info_card.update_turbo)
        
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
        for i in range(3):  # 第一列有 3 張卡片
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
        self.row_card_counts = [3, 3]  # 每列的卡片數量（第一列: 音樂/導航/門, 第二列: Trip/ODO/行程資訊）
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
    
    def _init_shutdown_monitor(self):
        """初始化關機監控器"""
        self._shutdown_monitor = get_shutdown_monitor()
        
        # 連接信號
        self._shutdown_monitor.power_lost.connect(self._on_power_lost)
        self._shutdown_monitor.power_restored.connect(self._on_power_restored)
        
        # 連接無電壓訊號超時信號（3 分鐘沒收到 OBD 電壓數據）
        self._shutdown_monitor.no_signal_timeout.connect(self._on_no_voltage_signal_timeout)
        
        # 連接轉速信號到關機監控器（用於判斷是否低於 300 RPM）
        self.signal_update_rpm.connect(lambda rpm: self._shutdown_monitor.update_rpm(rpm * 1000))
        
        # 啟動無訊號監控
        self._shutdown_monitor.start_no_signal_monitoring()
        
        print("[ShutdownMonitor] 關機監控器已初始化（含無訊號超時監控）")
    
    def _on_power_lost(self):
        """電源中斷時顯示關機對話框"""
        print("⚠️ 偵測到電源中斷，顯示關機對話框")
        
        # 釋放 GPS 資源，讓 location_notifier 可以接手
        if hasattr(self, 'gps_monitor_thread') and self.gps_monitor_thread is not None:
            self.gps_monitor_thread.stop()
            
        self._shutdown_monitor.show_shutdown_dialog(self)
    
    def _on_power_restored(self):
        """電源恢復"""
        print("✅ 電源已恢復")
    
    def _on_no_voltage_signal_timeout(self):
        """無電壓訊號超時（3 分鐘沒收到 OBD 電壓數據）
        
        這表示儀表開機了，但車子從未發動（OBD 沒有回應）。
        為了節省電力，觸發關機流程。
        """
        print("⚠️ 無電壓訊號超時（3 分鐘未收到 OBD 電壓數據）")
        print("   可能原因: 儀表開機但車輛從未發動，OBD 無回應")
        
        # 釋放 GPS 資源
        if hasattr(self, 'gps_monitor_thread') and self.gps_monitor_thread is not None:
            self.gps_monitor_thread.stop()
        
        # 顯示關機對話框（與電源中斷相同的處理）
        self._shutdown_monitor.show_shutdown_dialog(self)
    
    def _create_brightness_overlay(self):
        """創建亮度調節覆蓋層"""
        self.brightness_overlay = QWidget(self)
        self.brightness_overlay.setGeometry(0, 0, 1920, 480)
        self.brightness_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # 讓滑鼠事件穿透
        self.brightness_overlay.setStyleSheet("background: transparent;")
        self.brightness_overlay.hide()
        self.brightness_overlay.raise_()  # 確保在最上層
    
    def set_brightness(self, level):
        """
        設定亮度等級
        level: 0=100% (全亮), 1=75%, 2=50%
        """
        self.brightness_level = level
        
        if level == 0:
            # 全亮 - 隱藏覆蓋層
            self.brightness_overlay.hide()
            print("[亮度] 設定為 100%")
        else:
            # 計算透明度 (level 1 = 25% 黑, level 2 = 50% 黑)
            opacity = level * 0.25  # 0.25 或 0.50
            alpha = int(opacity * 255)
            self.brightness_overlay.setStyleSheet(f"background: rgba(0, 0, 0, {alpha});")
            self.brightness_overlay.show()
            self.brightness_overlay.raise_()
            print(f"[亮度] 設定為 {100 - level * 25}%")
    
    def cycle_brightness(self):
        """循環切換亮度等級 100% -> 75% -> 50% -> 100%"""
        next_level = (self.brightness_level + 1) % 3
        self.set_brightness(next_level)
        return next_level
    
    def get_brightness_level(self):
        """取得當前亮度等級"""
        return self.brightness_level
    
    def get_brightness_percent(self):
        """取得當前亮度百分比"""
        return 100 - self.brightness_level * 25

    def init_data(self):
        """初始化儀表數據，可以從外部數據源更新"""
        self.speed = 0
        self.distance_speed = 0.0  # OBD 原始速度用於里程累積
        self.rpm = 0
        self.temp = None  # None = OBD 未回應，顯示 "--"
        self.fuel = 60  # 稍微偏上的油量
        self.gear = "P"  # 顯示用的檔位
        self.actual_gear = "P"  # 實際檔位（CAN 傳來的原始值）
        self.show_detailed_gear = True  # False=顯示D, True=顯示具體檔位(1-5)
        self.turbo = None  # None = OBD 未回應，顯示 "--"
        self.battery = None  # None = OBD 未回應，顯示 "--"
        
        # 施密特觸發器 (Schmitt Trigger) - 防止速度顯示閃爍
        # 當速度在 N.3 ~ N.7 之間波動時，顯示會保持穩定不跳動
        self._displayed_speed_int = 0   # 當前顯示的整數速度
        self._speed_hysteresis = 0.3    # 滯迴閾值 (±0.3 km/h)
        
        # 定速巡航狀態
        self.cruise_switch = False   # 開關是否開啟（白色）
        self.cruise_engaged = False  # 是否作動中（綠色）
        
        # 手煞車狀態
        self.parking_brake = False   # 手煞車是否拉起
        
        # GPS 座標
        self.gps_lat = None
        self.gps_lon = None
        
        # 網路狀態
        self.is_offline = False  # 是否斷線
        self._was_offline = True  # 記錄上次網路狀態（初始假設離線，連上後觸發初始化）
        
        # 服務連線狀態追蹤
        self._spotify_connected = False
        self._spotify_init_attempts = 0
        self._spotify_integration = None  # Spotify 整合實例引用
        self._mqtt_connected = False
        self._mqtt_reconnect_timer = None
        
        # 引擎狀態追蹤 (用於 MQTT status)
        self._engine_status = False  # 引擎運轉狀態
        self._last_battery_for_status = 0.0  # 追蹤上一次電壓用於判斷熄火

        # 速度校正狀態
        import vehicle.datagrab as datagrab
        self.speed_correction = datagrab.get_speed_correction()
        self._last_speed_cali_ts = 0
        
        # RPM 動畫平滑 (GUI 端二次平滑)
        self.target_rpm = 0.0  # 目標轉速
        self.rpm_animation_alpha = 0.3  # GUI 端平滑係數
        
        # 門狀態卡片自動切換
        self.door_auto_switch_timer = QTimer()
        self.door_auto_switch_timer.setSingleShot(True)
        self.door_auto_switch_timer.timeout.connect(self._auto_switch_back_from_door)
        self.previous_row_index = 0   # 記錄切換前的列索引
        self.previous_card_index = 0  # 記錄切換前的卡片索引
        
        # 雷達自動切換（低速 + D/R檔 + 雷達觸發時自動切到門卡片）
        self.last_radar_auto_switch_time = 0  # 上次雷達自動切換時間
        
        # 雷達自動切換（低速 + D/R檔 + 雷達觸發時自動切到門卡片）
        self.last_radar_auto_switch_time = 0  # 上次雷達自動切換時間
        
        # 物理心跳 Timer（每 100ms 觸發一次，持續累積里程）
        self.physics_timer = QTimer()
        self.physics_timer.timeout.connect(self._physics_tick)
        # Timer 啟動延遲到 start_dashboard() 調用時
        # self.physics_timer.start(100)  # 100ms = 0.1 秒
        self.last_physics_time = time.time()
        
        self.update_display()
        
        # Spotify 初始化延遲到 start_dashboard() 調用時
        # self.check_spotify_config()
        
        # 標記：是否跳過內建的 Spotify 初始化（用於 demo_mode.py 自行處理）
        self._skip_spotify_init = False

    def start_dashboard(self):
        """開機動畫完成後啟動儀表板的所有邏輯"""
        print("啟動儀表板邏輯...")
        
        # 啟動卡頓偵測器（閾值 100ms，只報告明顯卡頓）
        self.jank_detector = JankDetector(threshold_ms=100)
        self.jank_detector.start()
        
        # 啟動時間更新 Timer
        self.time_timer.start(1000)
        
        # 啟動方向燈動畫 Timer
        self.animation_timer.start(16)  # 約 60 FPS
        
        # 啟動速限閃爍 Timer
        self.speed_limit_timer = QTimer()
        self.speed_limit_timer.timeout.connect(self._update_speed_limit_flash)
        self.speed_limit_timer.start(50)  # 50ms = 約 20 FPS
        
        # 啟動速限查詢 Timer（每 5 秒查詢一次）
        self.speed_limit_query_timer = QTimer()
        self.speed_limit_query_timer.timeout.connect(self._update_speed_limit)
        self.speed_limit_query_timer.start(5000)  # 5000ms = 5 秒
        
        # 啟動物理心跳 Timer（里程累積）
        self.last_physics_time = time.time()  # 重設時間基準
        self.physics_timer.start(100)  # 100ms = 0.1 秒
        
        # 啟動增量式垃圾回收 Timer（每 10 秒執行一次小型 GC）
        # 更頻繁但更小量的 GC 可以避免物件累積後造成的長時間停頓
        self.gc_timer = QTimer()
        self.gc_timer.timeout.connect(self._incremental_gc)
        self.gc_timer.start(10000)  # 每 10 秒
        self._gc_counter = 0
        
        # 初始化 Spotify（除非被跳過）
        if not self._skip_spotify_init:
            self.check_spotify_config()
        else:
            print("跳過內建 Spotify 初始化（由外部處理）")
        
        # 初始化 MQTT（如果有設定檔）
        self._check_mqtt_config()
        
        # 啟動網路狀態檢測（每 5 秒檢查一次）
        self.network_check_timer = QTimer()
        self.network_check_timer.timeout.connect(self._check_network_status)
        self.network_check_timer.start(5000)  # 5 秒
        # 立即檢查一次
        QTimer.singleShot(2000, self._check_network_status)
        
        # 啟動服務健康檢查（每 60 秒檢查一次）
        self.service_health_timer = QTimer()
        self.service_health_timer.timeout.connect(self._check_service_health)
        self.service_health_timer.start(60000)  # 60 秒
        
        # === 初始化 GPIO 按鈕（樹莓派實體按鈕）===
        # GPIO19: 按鈕 A (短按=切換左卡片, 長按=詳細視圖)
        # GPIO26: 按鈕 B (短按=切換右卡片, 長按=重置Trip)
        # GPIO27: 手煞車感測器 (ESP32 數位輸出)
        self._gpio_handler = setup_gpio_buttons(self)
        if self._gpio_handler:
            print("GPIO 按鈕已啟用 - 可使用實體按鈕控制")
        else:
            print("GPIO 按鈕不可用 - 請使用鍵盤 F1/F2 控制")
        
        print("儀表板邏輯已啟動")
    
    def _incremental_gc(self):
        """智能垃圾回收 - 只在車輛靜止時執行
        
        策略：
        1. 完全禁用 Python 自動 GC（在 __init__ 中設定）
        2. 只在速度為 0（車輛靜止）時才考慮執行 GC
        3. 距離上次 GC 超過 1 小時才執行
        4. 這樣即使 GC 有短暫停頓，也不會影響駕駛體驗
        
        8GB RAM + 智能 GC = 不會記憶體洩漏，也不會凍結
        """
        self._gc_counter += 1
        
        # 初始化上次 GC 時間
        if not hasattr(self, '_last_full_gc_time'):
            self._last_full_gc_time = time.time()
        
        perf_enabled = os.environ.get('PERF_MONITOR', '').lower() in ('1', 'true', 'yes')
        
        # 每 10 秒檢查一次是否需要 GC
        now = time.time()
        hours_since_gc = (now - self._last_full_gc_time) / 3600
        
        # 條件：速度為 0 且距離上次 GC 超過 1 小時
        if self.speed == 0 and hours_since_gc >= 1.0:
            import threading
            
            def background_full_gc():
                start = time.perf_counter()
                # 按順序執行，避免一次性大量釋放
                collected0 = gc.collect(0)
                collected1 = gc.collect(1)
                collected2 = gc.collect(2)
                duration = (time.perf_counter() - start) * 1000
                total = collected0 + collected1 + collected2
                print(f"⚡ [GC] 智能 GC 完成 (車輛靜止): {duration:.1f}ms, 回收 {total} 物件")
            
            # 更新 GC 時間
            self._last_full_gc_time = now
            print(f"⚡ [GC] 觸發智能 GC (速度=0, 已 {hours_since_gc:.1f} 小時未 GC)")
            threading.Thread(target=background_full_gc, daemon=True).start()

    def check_spotify_config(self):
        """檢查 Spotify 設定並初始化"""
        config_path = get_spotify_config_path()
        cache_path = get_spotify_cache_path()
        
        # 只有當配置檔和快取都存在時才自動初始化
        if os.path.exists(config_path) and os.path.exists(cache_path):
            print("發現 Spotify 設定檔和快取，正在初始化...")
            self.music_card.show_player_ui()
            # 在背景執行緒初始化，避免卡住 UI
            import threading
            def init_spotify():
                result = setup_spotify(self)
                if result:
                    self._spotify_connected = True
                    self._spotify_integration = result  # 儲存整合實例引用
                    self._spotify_init_attempts = 0
                    print("Spotify 初始化成功")
                else:
                    self._spotify_connected = False
                    self._spotify_init_attempts += 1
                    print(f"Spotify 初始化失敗 (嘗試 {self._spotify_init_attempts})")
                    # 如果初始化失敗，30 秒後重試（最多 3 次）
                    if self._spotify_init_attempts < 3 and not self.is_offline:
                        print(f"[Spotify] 將在 30 秒後重試...")
                        QTimer.singleShot(30000, self._retry_spotify_init)
            threading.Thread(target=init_spotify, daemon=True).start()
        else:
            if not os.path.exists(config_path):
                print("未發現 Spotify 設定檔，顯示綁定介面")
            else:
                print("未發現授權快取，顯示綁定介面")
            self.music_card.show_bind_ui()
    
    def _retry_spotify_init(self):
        """重試 Spotify 初始化"""
        if self._spotify_connected or self.is_offline:
            return
        
        print(f"[Spotify] 重試初始化 (嘗試 {self._spotify_init_attempts + 1}/3)...")
        
        import threading
        def init_spotify():
            result = setup_spotify(self)
            if result:
                self._spotify_connected = True
                self._spotify_integration = result  # 儲存整合實例引用
                self._spotify_init_attempts = 0
                print("[Spotify] ✅ 重試成功")
            else:
                self._spotify_connected = False
                self._spotify_init_attempts += 1
                print(f"[Spotify] ❌ 重試失敗 (嘗試 {self._spotify_init_attempts})")
                # 繼續重試
                if self._spotify_init_attempts < 3 and not self.is_offline:
                    QTimer.singleShot(30000, self._retry_spotify_init)
        
        threading.Thread(target=init_spotify, daemon=True).start()

    def _handle_spotify_update_on_card_change(self, old_index, new_index):
        """處理卡片切換時的 Spotify 更新邏輯"""
        if not self._spotify_integration:
            return
        
        # 只有在第一列（音樂卡片所在列）才處理
        if self.current_row_index != 0:
            return
        
        # 音樂卡片在第一列的索引 0
        is_entering_music = (old_index != 0 and new_index == 0)
        is_leaving_music = (old_index == 0 and new_index != 0)
        
        if is_entering_music:
            print("進入音樂卡片，強制立即更新 Spotify")
            # 進入音樂卡片時立即更新
            self._spotify_integration.force_update_now()
            # 保持高頻更新（設定為2秒以獲得良好體驗）
            self._spotify_integration.set_update_interval(2.0)
        elif is_leaving_music:
            print("離開音樂卡片，恢復10秒更新間隔")
            # 離開音樂卡片時恢復10秒更新間隔
            self._spotify_integration.set_update_interval(10.0)
    
    def _handle_spotify_update_on_row_change(self, new_row_index):
        """處理列切換時的 Spotify 更新邏輯"""
        if not self._spotify_integration:
            return
        
        # 音樂卡片在第一列，切換到非第一列時要恢復10秒更新
        if self.current_row_index == 0 and new_row_index != 0:
            print("離開音樂卡片所在列，恢復10秒更新間隔")
            self._spotify_integration.set_update_interval(10.0)
        # 切換到第一列時，檢查是否在音樂卡片上
        elif self.current_row_index != 0 and new_row_index == 0:
            if self.current_left_index == 0:  # 目前在音樂卡片上
                print("進入音樂卡片所在列且在音樂卡片上，設定2秒更新")
                self._spotify_integration.force_update_now()
                self._spotify_integration.set_update_interval(2.0)
    
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
                    result = setup_spotify(self)
                    if result:
                        self._spotify_connected = True
                        self._spotify_init_attempts = 0
                        print("[Spotify] ✅ 初始化成功")
                    else:
                        self._spotify_connected = False
                        print("[Spotify] ❌ 初始化失敗")
                except Exception as e:
                    self._spotify_connected = False
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
    
    def show_mqtt_settings(self):
        """顯示 MQTT 設定對話框"""
        print("開啟 MQTT 設定對話框...")
        
        # 先隱藏控制面板
        if self.panel_visible:
            self.hide_control_panel()
        
        # 創建 MQTT 設定對話框
        self.mqtt_dialog = MQTTSettingsDialog()
        self.mqtt_dialog.signals.settings_saved.connect(self.on_mqtt_settings_saved)
        
        # 設定為模態對話框
        self.mqtt_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        # 設定視窗標誌
        self.mqtt_dialog.setWindowFlags(
            Qt.WindowType.Dialog | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint
        )
        
        # 顯示對話框
        self.mqtt_dialog.show()
        
        # 置於螢幕中央
        primary_screen = QApplication.primaryScreen()
        if primary_screen:
            screen_geometry = primary_screen.geometry()
            dialog_geometry = self.mqtt_dialog.geometry()
            x = (screen_geometry.width() - dialog_geometry.width()) // 2
            y = (screen_geometry.height() - dialog_geometry.height()) // 2
            self.mqtt_dialog.move(x, y)

    def show_spotify_settings(self):
        """顯示 Spotify 設定（授權）對話框"""
        print("開啟 Spotify 設定對話框...")

        # 先隱藏控制面板
        if self.panel_visible:
            self.hide_control_panel()

        # 復用既有 Spotify 授權/綁定流程
        self.start_spotify_auth()

    def show_telegram_settings(self):
        """顯示 Telegram 設定對話框"""
        print("開啟 Telegram 設定對話框...")

        # 先隱藏控制面板
        if self.panel_visible:
            self.hide_control_panel()

        # 創建 Telegram 設定對話框
        self.telegram_dialog = TelegramSettingsDialog()
        self.telegram_dialog.signals.settings_saved.connect(self.on_telegram_settings_saved)

        # 設定為模態對話框
        self.telegram_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)

        # 設定視窗標誌
        self.telegram_dialog.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint
        )

        # 顯示對話框
        self.telegram_dialog.show()

        # 置於螢幕中央
        primary_screen = QApplication.primaryScreen()
        if primary_screen:
            screen_geometry = primary_screen.geometry()
            dialog_geometry = self.telegram_dialog.geometry()
            x = (screen_geometry.width() - dialog_geometry.width()) // 2
            y = (screen_geometry.height() - dialog_geometry.height()) // 2
            self.telegram_dialog.move(x, y)
    
    def on_mqtt_settings_saved(self, success):
        """MQTT 設定儲存完成回調"""
        if success:
            print("MQTT 設定已儲存！")
            # 可以在這裡初始化 MQTT 連線
            self._init_mqtt_client()
        else:
            print("MQTT 設定失敗")
        
        # 關閉對話框 (如果還沒關閉)
        if hasattr(self, 'mqtt_dialog'):
            self.mqtt_dialog.close()
            del self.mqtt_dialog

    def on_telegram_settings_saved(self, success):
        """Telegram 設定儲存完成回調"""
        if success:
            print("Telegram 設定已儲存！")
            self._init_telegram_settings()
        else:
            print("Telegram 設定失敗")

        # 關閉對話框 (如果還沒關閉)
        if hasattr(self, 'telegram_dialog'):
            self.telegram_dialog.close()
            del self.telegram_dialog

    def _init_telegram_settings(self):
        """載入 Telegram 設定（供通知模組使用）"""
        config_path = os.path.join(PROJECT_ROOT, "telegram_config.json")
        if not os.path.exists(config_path):
            print("[Telegram] 尚未找到 telegram_config.json")
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            has_token = bool(config.get('bot_token', '').strip())
            has_chat_id = bool(config.get('chat_id', '').strip())
            if has_token and has_chat_id:
                print("[Telegram] 設定已載入")
            else:
                print("[Telegram] 設定檔欄位不完整")
        except Exception as e:
            print(f"[Telegram] 讀取設定失敗: {e}")
    
    def _check_network_status(self):
        """檢查網路連線狀態"""
        import socket
        import subprocess
        import platform
        
        def check_connection():
            # 方法 1: 嘗試 socket 連接 Google DNS
            try:
                sock = socket.create_connection(("8.8.8.8", 53), timeout=3)
                sock.close()
                return True
            except Exception:
                pass
            
            # 方法 2: 嘗試 socket 連接 Cloudflare DNS
            try:
                sock = socket.create_connection(("1.1.1.1", 53), timeout=3)
                sock.close()
                return True
            except Exception:
                pass
            
            # 都失敗了
            return False
        
        # 在背景執行緒檢查，避免卡住 UI
        import threading
        
        def check_and_update():
            is_connected = check_connection()
            # 使用 Signal 回到主執行緒更新 UI
            self.signal_update_network.emit(is_connected)
        
        threading.Thread(target=check_and_update, daemon=True).start()
    
    def _update_network_status(self, is_connected):
        """更新網路狀態顯示（主執行緒）"""
        was_offline = self.is_offline
        self.is_offline = not is_connected
        
        if self.is_offline != was_offline:
            if self.is_offline:
                print("[網路] ⚠️ 網路已斷線")
            else:
                print("[網路] ✅ 網路已恢復連線")
                # 網路恢復時嘗試重新連接服務
                self._on_network_restored()
        
        # 更新音樂卡片和導航卡片的離線狀態
        self.music_card.set_offline(self.is_offline)
        self.nav_card.set_offline(self.is_offline)
        
        # 更新下拉面板的「更新」按鈕狀態
        if self.control_panel:
            self.control_panel.set_update_button_enabled(is_connected)
    
    def _on_network_restored(self):
        """網路恢復時的重連邏輯"""
        print("[重連] 網路已恢復，檢查服務狀態...")
        
        # 延遲 2 秒後重連，避免網路剛恢復就馬上連接
        QTimer.singleShot(2000, self._attempt_reconnect_services)
    
    def _attempt_reconnect_services(self):
        """嘗試重新連接各項服務"""
        # 如果目前仍是離線狀態，取消重連
        if self.is_offline:
            print("[重連] 網路仍未恢復，取消重連")
            return
        
        # 1. 重連 Spotify（如果尚未連線且有設定檔）
        if not self._spotify_connected:
            config_path = get_spotify_config_path()
            cache_path = get_spotify_cache_path()
            if os.path.exists(config_path) and os.path.exists(cache_path):
                print("[重連] 嘗試重新連接 Spotify...")
                self._reconnect_spotify()
        
        # 2. 重連 MQTT（如果有設定檔但客戶端未連線）
        config_file = get_mqtt_config_path()
        if os.path.exists(config_file):
            if not hasattr(self, 'mqtt_client') or self.mqtt_client is None or not self._mqtt_connected:
                print("[重連] 嘗試重新連接 MQTT...")
                self._reconnect_mqtt()
    
    def _reconnect_spotify(self):
        """重新連接 Spotify"""
        def _init_spotify_async():
            try:
                result = setup_spotify(self)
                if result:
                    self._spotify_connected = True
                    self._spotify_init_attempts = 0
                    print("[Spotify] ✅ 重新連接成功")
                else:
                    self._spotify_init_attempts += 1
                    print(f"[Spotify] ❌ 重新連接失敗 (嘗試 {self._spotify_init_attempts})")
            except Exception as e:
                self._spotify_init_attempts += 1
                print(f"[Spotify] ❌ 重新連接錯誤: {e}")
        
        import threading
        threading.Thread(target=_init_spotify_async, daemon=True).start()
    
    def _reconnect_mqtt(self):
        """重新連接 MQTT"""
        # 先清理舊的連線
        if hasattr(self, 'mqtt_client') and self.mqtt_client is not None:
            try:
                self.mqtt_client.disconnect()
                self.mqtt_client.loop_stop()
            except Exception:
                pass
            self.mqtt_client = None
            self._mqtt_connected = False
        
        # 重新初始化
        self._init_mqtt_client()
    
    def _check_service_health(self):
        """定時檢查服務健康狀態，必要時重連"""
        # 如果離線，跳過檢查
        if self.is_offline:
            return
        
        # 檢查 Spotify 狀態
        config_path = get_spotify_config_path()
        cache_path = get_spotify_cache_path()
        if os.path.exists(config_path) and os.path.exists(cache_path):
            if not self._spotify_connected and self._spotify_init_attempts < 3:
                print("[健康檢查] Spotify 未連線，嘗試重連...")
                self._reconnect_spotify()
        
        # 檢查 MQTT 狀態
        config_file = get_mqtt_config_path()
        if os.path.exists(config_file):
            if not self._mqtt_connected:
                print("[健康檢查] MQTT 未連線，嘗試重連...")
                self._reconnect_mqtt()
    
    def _check_mqtt_config(self):
        """檢查 MQTT 設定並自動連線"""
        config_file = get_mqtt_config_path()
        if os.path.exists(config_file):
            print("[MQTT] 發現設定檔，嘗試自動連線...")
            self._init_mqtt_client()
        else:
            print("[MQTT] 未發現設定檔，可從下拉面板進行設定")
    
    def _init_mqtt_client(self):
        """初始化 MQTT 客戶端（支援自動重連）"""
        config_file = get_mqtt_config_path()
        if not os.path.exists(config_file):
            print("[MQTT] 設定檔不存在")
            return
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            import paho.mqtt.client as mqtt
            
            dashboard = self  # 保存 dashboard 參考
            mqtt_publish_topic = config.get('publish_topic', 'car/telemetry')  # 上傳用的主題
            
            def on_connect(client, userdata, flags, rc, properties=None):
                if rc == 0:
                    dashboard._mqtt_connected = True
                    print(f"[MQTT] ✅ 已連接到 {config['broker']}:{config['port']}")
                    # 訂閱主題
                    topic = config.get('topic', 'car/#')
                    client.subscribe(topic)
                    print(f"[MQTT] 已訂閱主題: {topic}")
                    print(f"[MQTT] 發布主題: {mqtt_publish_topic}")
                    # 透過 Signal 在主執行緒啟動數據上傳計時器
                    dashboard.signal_start_mqtt_telemetry.emit()
                else:
                    dashboard._mqtt_connected = False
                    print(f"[MQTT] ❌ 連線失敗，錯誤碼: {rc}")
            
            def on_disconnect(client, userdata, rc, properties=None, reason_code=None):
                dashboard._mqtt_connected = False
                # 停止遙測上傳
                if hasattr(dashboard, '_mqtt_telemetry_timer') and dashboard._mqtt_telemetry_timer:
                    dashboard._mqtt_telemetry_timer.stop()
                    print("[MQTT] 遙測上傳已暫停")
                if rc != 0:
                    print(f"[MQTT] ⚠️ 意外斷線 (rc={rc})，將自動重連...")
                else:
                    print("[MQTT] 已斷線")
            
            def on_message(client, userdata, msg):
                try:
                    payload = msg.payload.decode('utf-8')
                    data = json.loads(payload)
                    print(f"[MQTT] 收到訊息: {msg.topic} -> {payload[:100]}...")
                    
                    # 處理導航訊息 - 使用 Signal 確保在主執行緒更新 UI
                    if 'navigation' in msg.topic or 'nav' in msg.topic:
                        # 透過 Signal 傳遞資料到主執行緒
                        dashboard.signal_update_navigation.emit(data)
                    
                except Exception as e:
                    print(f"[MQTT] 處理訊息錯誤: {e}")
            
            self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            self.mqtt_client.on_connect = on_connect
            self.mqtt_client.on_disconnect = on_disconnect
            self.mqtt_client.on_message = on_message
            
            # 啟用自動重連，指數退避（1秒起，最大 5 秒）
            self.mqtt_client.reconnect_delay_set(min_delay=1, max_delay=5)
            
            # 設定認證
            username = config.get('username', '').strip()
            password = config.get('password', '').strip()
            if username:
                self.mqtt_client.username_pw_set(username, password)
            
            # 在背景執行緒中連線
            import threading
            def connect_mqtt():
                try:
                    self.mqtt_client.connect(config['broker'], config['port'], keepalive=60)
                    # 使用 loop_forever 會自動處理重連
                    self.mqtt_client.loop_forever(retry_first_connection=True)
                except Exception as e:
                    print(f"[MQTT] 連線錯誤: {e}")
                    dashboard._mqtt_connected = False
            
            mqtt_thread = threading.Thread(target=connect_mqtt, daemon=True)
            mqtt_thread.start()
            
        except ImportError:
            print("[MQTT] paho-mqtt 未安裝")
        except Exception as e:
            print(f"[MQTT] 初始化失敗: {e}")
    
    def _start_mqtt_telemetry_timer(self):
        """啟動 MQTT 車輛數據上傳計時器"""
        if hasattr(self, '_mqtt_telemetry_timer') and self._mqtt_telemetry_timer is not None:
            self._mqtt_telemetry_timer.stop()
        
        self._mqtt_telemetry_timer = QTimer()
        self._mqtt_telemetry_timer.timeout.connect(self._publish_telemetry)
        self._mqtt_telemetry_timer.start(30000)  # 每 30 秒上傳一次
        print("[MQTT] 車輛數據上傳已啟動 (每 30 秒)")

    def _update_engine_status(self):
        """根據 RPM 與電壓更新引擎狀態，回傳是否從 on 掉到 off"""
        prev_status = self._engine_status
        current_rpm = int(self.rpm * 1000) if self.rpm else 0
        current_battery = self.battery if self.battery is not None else 0.0

        # 判斷引擎狀態：
        # 1. 電壓從 >= 10V 掉到 0V：斷電，判定為熄火
        # 2. RPM > 500：引擎運轉中
        # 3. RPM <= 500：引擎熄火（怠速一般 600-900 rpm，低於 500 視為熄火）
        
        if self._last_battery_for_status >= 10 and current_battery == 0:
            # 電壓掉到 0 優先判斷為熄火（斷電情況）
            self._engine_status = False
        elif current_rpm > 500:
            # 轉速高於 500 rpm 視為引擎運轉
            self._engine_status = True
        elif current_rpm <= 500:
            # 轉速低於或等於 500 rpm 視為熄火
            self._engine_status = False
        # 不應該有其他情況，但如果有則維持原狀態

        self._last_battery_for_status = current_battery
        status_fell = prev_status and not self._engine_status
        return status_fell, current_rpm

    def _maybe_publish_engine_off(self):
        """引擎狀態從 on 掉到 off 時立即上傳一次"""
        status_fell, _ = self._update_engine_status()
        if status_fell and self._mqtt_connected:
            self._publish_telemetry()
    
    def _publish_telemetry(self):
        """發布車輛遙測數據到 MQTT"""
        if not self._mqtt_connected or not hasattr(self, 'mqtt_client') or self.mqtt_client is None:
            return
        
        try:
            # 取得 ODO 和 Trip 資料
            storage = OdometerStorage()
            odo_total = storage.get_odo()
            trip1_distance, _ = storage.get_trip1()
            trip2_distance, _ = storage.get_trip2()
            
            # 取得門狀態 (開門 = "on", 關門 = "off")
            door_status = {}
            if hasattr(self, 'door_card'):
                door_status = {
                    'FL': 'off' if self.door_card.door_fl_closed else 'on',
                    'FR': 'off' if self.door_card.door_fr_closed else 'on',
                    'RL': 'off' if self.door_card.door_rl_closed else 'on',
                    'RR': 'off' if self.door_card.door_rr_closed else 'on',
                    'BK': 'off' if self.door_card.door_bk_closed else 'on'
                }
            
            # 水溫轉換：self.temp 是百分比 (0-100)，轉換為攝氏度 (40-120°C)
            coolant_celsius = 40 + (self.temp / 100) * 80 if self.temp is not None else None
            
            # 計算引擎狀態 (status)
            # 電壓從 10 以上掉到 0 時，status 優先變成 false（熄火）
            # RPM > 100 時，status 變成 true（引擎運轉）
            status_fell, current_rpm = self._update_engine_status()
            
            # 組裝數據
            telemetry = {
                'timestamp': time.time(),
                'status': self._engine_status,
                'speed': int(self.speed),  # 與儀表顯示一致，使用整數
                'rpm': current_rpm,  # 使用已計算的整數 RPM
                'coolant_temp': coolant_celsius,
                'fuel': self.fuel,
                'gear': self.gear,
                'turbo': self.turbo,
                'battery': self.battery,
                'odo': odo_total,
                'trip_a': trip1_distance,
                'trip_b': trip2_distance,
                'gps': {
                    'lat': self.gps_lat,
                    'lon': self.gps_lon,
                    'fixed': getattr(self, 'is_gps_fixed', False)
                },
                'doors': door_status,
                'cruise': {
                    'switch': self.cruise_switch,
                    'engaged': self.cruise_engaged
                },
                'parking_brake': self.parking_brake
            }
            
            # 讀取發布主題
            config_file = get_mqtt_config_path()
            publish_topic = "car/telemetry"
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        publish_topic = config.get('publish_topic', 'car/telemetry')
                except:
                    pass
            
            # 發布數據 (retain=True 讓新訂閱者能收到最後一筆訊息)
            payload = json.dumps(telemetry, ensure_ascii=False)
            self.mqtt_client.publish(publish_topic, payload, qos=0, retain=True)
            
        except Exception as e:
            print(f"[MQTT] 發布遙測數據錯誤: {e}")
    
    @pyqtSlot(dict)
    def _slot_update_navigation(self, data: dict):
        """處理導航訊息（Slot - 在主執行緒執行）"""
        print(f"[Navigation] _slot_update_navigation 被呼叫")
        print(f"[Navigation] 資料: direction={data.get('direction')}, distance={data.get('totalDistance')}")

        # 先取出 GPS 相關欄位（即使導航訊息過時也可用於外部 GPS 備援）
        lat = data.get('latitude')
        lon = data.get('longitude')
        speed = data.get('speed')
        bearing = data.get('bearing', 0)

        # 檢查是否為有效的 GPS 數值（排除空字符串、None）
        try:
            lat = float(lat) if lat not in (None, '', 'None') else None
            lon = float(lon) if lon not in (None, '', 'None') else None
            speed = float(speed) if speed not in (None, '', 'None') else None
            bearing = float(bearing) if bearing not in (None, '', 'None') else 0
        except (ValueError, TypeError):
            lat = lon = speed = None
            bearing = 0

        # 更新 bearing (用於速限查詢)
        self.current_bearing = bearing

        # 外部 GPS 備援：
        # 1) 內部 GPS 未定位時啟用
        # 2) 一旦進入外部模式，後續持續注入以維持 freshness，避免圖示閃回 searching
        if lat is not None and lon is not None and self.gps_monitor_thread is not None:
            keep_external = (not self.is_gps_fixed) or self.gps_monitor_thread.is_using_external_gps()
            if keep_external:
                print(f"[Navigation] 使用 MQTT GPS 備援: lat={lat}, lon={lon}, speed={speed}")
                self.gps_monitor_thread.inject_external_gps(lat, lon, speed or 0, bearing, data.get('timestamp', ''))

            # 更新 GPS 位置（速限由計時器每 5 秒查詢一次）
            self.gps_lat = lat
            self.gps_lon = lon
        
        # 檢查 timestamp 新鮮度 (15秒內)
        timestamp_str = data.get('timestamp')
        if timestamp_str:
            try:
                from datetime import datetime, timezone
                # 解析 ISO 8601 格式的 timestamp
                msg_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                current_time = datetime.now(timezone.utc)
                time_diff = abs((current_time - msg_time).total_seconds())
                
                print(f"[Navigation] 訊息時間: {timestamp_str}, 時間差: {time_diff:.1f}秒")
                
                if time_diff > 15:
                    print(f"[Navigation] ⚠️ 訊息過時 (相差 {time_diff:.1f}秒)，僅更新 GPS 備援並顯示無導航畫面")
                    # 訊息過時，顯示無導航資訊畫面
                    if hasattr(self, 'nav_card'):
                        self.nav_card.show_no_nav_ui()
                    return
                    
            except Exception as e:
                print(f"[Navigation] ⚠️ 解析 timestamp 失敗: {e}，仍繼續處理")
        else:
            print("[Navigation] ⚠️ 訊息無 timestamp，仍繼續處理")
        
        if hasattr(self, 'nav_card'):
            self.nav_card.update_navigation(data)
            print(f"[Navigation] 已更新導航資訊: {data.get('direction', '')}")
        else:
            print("[Navigation] 錯誤：nav_card 不存在")

    def set_speed_sync_mode(self, mode: str):
        """設定速度同步三段模式並同步 datagrab"""
        if mode not in self.speed_sync_modes:
            print(f"[速度同步] 無效模式: {mode}")
            return
        self.speed_sync_mode = mode
        if self.control_panel:
            self.control_panel.set_speed_sync_state(mode)

        try:
            import vehicle.datagrab as datagrab
            datagrab.set_speed_sync_mode(mode)
        except Exception as e:
            print(f"[速度同步] 更新 datagrab 失敗: {e}")
        print(f"[速度同步] 模式切換為 {mode}")

    def cycle_speed_sync_mode(self):
        """依序切換速度模式 calibrated -> fixed -> gps"""
        try:
            idx = self.speed_sync_modes.index(self.speed_sync_mode)
        except ValueError:
            idx = 0
        next_mode = self.speed_sync_modes[(idx + 1) % len(self.speed_sync_modes)]
        self.set_speed_sync_mode(next_mode)

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
        
        # 確保控制面板在亮度覆蓋層之上
        if self.brightness_overlay:
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
            from wifi.wifi_manager import WiFiManagerWidget
            
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
        
        # 門卡片位於第一列的第三張 (row=0, card=2)
        DOOR_ROW_INDEX = 0
        DOOR_CARD_INDEX = 2  # 音樂=0, 導航=1, 門=2
        
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
        DOOR_CARD_INDEX = 2  # 音樂=0, 導航=1, 門=2
        
        if self.current_row_index == DOOR_ROW_INDEX and self.current_card_index == DOOR_CARD_INDEX:
            # 切回之前的位置
            self.current_row_index = self.previous_row_index
            self.current_card_index = self.previous_card_index
            self.row_stack.setCurrentIndex(self.previous_row_index)
            self.rows[self.previous_row_index].setCurrentIndex(self.previous_card_index)
            
            # 更新指示器
            self.update_indicators()
            
            row_names = ["第一列", "第二列"]
            row1_card_names = ["音樂播放器", "導航", "門狀態"]
            row2_card_names = ["Trip", "ODO", "行程資訊"]
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
        # 如果 GPS 速度優先且已定位且且速度 >= 20，則忽略 CAN 速度更新 (顯示部分)
        import vehicle.datagrab as datagrab
        use_gps = (datagrab.gps_speed_mode and 
                   self.is_gps_fixed and 
                   speed >= 20.0) # 這裡用傳入的 speed (即 OBD 速度)
                   
        if use_gps:
            # 仍然更新後台數據 (如 trip 計算)，但不更新主顯示
            # 這裡假設 trip/odo 應該繼續使用 CAN 數據累計
            pass
        else:
            # 只有在非 GPS 模式下才刷新顯示變數
            pass

        # 動態校正速度權重：僅在 GPS 已鎖定且兩者差距小時逐步調整
        raw_obd_speed = None
        smoothed_obd_speed = None
        try:
            obd_data = datagrab.data_store.get("OBD", {})
            last_update = obd_data.get("last_update", 0)
            # 只有在 OBD 資料是「新鮮」的（5 秒內有更新）才使用
            if time.time() - last_update < 5.0:
                raw_obd_speed = obd_data.get("speed")
                smoothed_obd_speed = obd_data.get("speed_smoothed")
        except Exception:
            pass
        
        # --- 修改點 A: 分離顯示速度與物理計算速度 ---
        # 顯示用：如果有平滑值就用平滑值 (視覺不跳動)
        display_speed_candidate = smoothed_obd_speed if smoothed_obd_speed is not None else speed
        
        # 物理計算用：優先使用 RAW 數據 (積分更準)，如果沒有才用平滑或傳入值
        physics_speed_candidate = raw_obd_speed if raw_obd_speed is not None else display_speed_candidate
        
        # 存入變數供 physics_tick 使用
        self.calc_speed_source = max(0.0, physics_speed_candidate if physics_speed_candidate is not None else 0.0)

        # 更新顯示邏輯
        new_speed = max(0, min(200, display_speed_candidate if display_speed_candidate is not None else speed))
        # 兼容性：保留 distance_speed 供其他模擬/測試使用 (例如鍵盤模擬)
        self.distance_speed = max(0.0, display_speed_candidate if display_speed_candidate is not None else 0.0)
        
        # 里程/卡片顯示使用顯示速度（實際累積由 _physics_tick 驅動）
        self.trip_card.current_speed = new_speed
        self.odo_card.current_speed = new_speed
        
        # 更新行程資訊卡片的行駛距離（根據車速累計）
        if hasattr(self, 'trip_info_card'):
            self.trip_info_card.update_from_speed(new_speed)
        
        # 更新速度校正（維持原本邏輯）
        self._maybe_update_speed_correction(smoothed_obd_speed or raw_obd_speed)

        # === 施密特觸發器 (Schmitt Trigger) ===
        # 防止速度在 116 ↔ 117 之間頻繁跳動
        # 
        # 原理：
        # - 傳統方式：直接取整數，116.4→116, 116.6→117 (造成閃爍)
        # - 施密特方式：需要明確超過閾值才會改變
        #   - 從 116 升到 117：需要 speed > 116 + 0.5 + 0.3 = 116.8
        #   - 從 117 降到 116：需要 speed < 117 + 0.5 - 0.3 - 1 = 116.2
        #
        current_displayed = self._displayed_speed_int
        h = self._speed_hysteresis
        
        # 特殊處理：速度 < 1 時強制顯示 0（避免停車時顯示 1）
        if new_speed < 1.0:
            new_displayed = 0
        else:
            # 計算施密特閾值
            upper_threshold = current_displayed + 0.5 + h  # 升到 current+1 的閾值
            lower_threshold = current_displayed - 0.5 - h  # 降到 current-1 的閾值
            
            new_displayed = current_displayed
            if new_speed >= upper_threshold:
                # 速度明確上升，更新顯示
                new_displayed = int(new_speed)
            elif new_speed <= lower_threshold:
                # 速度明確下降，更新顯示
                new_displayed = int(new_speed)
            # else: 在滯迴區間內，保持不變
        
        # 更新速度狀態
        self.speed = new_speed
        
        # 更新速限顯示（檢查是否超速）
        if self.current_speed_limit is not None:
            self._apply_speed_limit_style()
        
        if new_displayed != current_displayed:
            self._displayed_speed_int = new_displayed
            self.update_display()

    def _maybe_update_speed_correction(self, obd_speed):
        """根據 GPS 與 OBD 速度差逐步修正校正係數"""
        if obd_speed is None or not self.is_gps_fixed:
            return
        try:
            import vehicle.datagrab as datagrab
            if getattr(datagrab, "speed_sync_mode", "calibrated") == "fixed":
                return
            if hasattr(datagrab, "is_speed_calibration_enabled") and not datagrab.is_speed_calibration_enabled():
                return
        except Exception:
            pass
        gps_speed = self.current_gps_speed
        if gps_speed <= 5 or obd_speed <= 5:
            return
        now = time.time()
        if now - self._last_speed_cali_ts < 1.0:
            return
        diff = abs(gps_speed - obd_speed)
        if diff > 10:
            return

        ratio = gps_speed / max(obd_speed, 0.1)
        ratio = max(0.7, min(1.3, ratio))

        import vehicle.datagrab as datagrab
        prev = datagrab.get_speed_correction()
        alpha = 0.05  # 漸進式更新，避免瞬間跳動
        new_value = (1 - alpha) * prev + alpha * ratio
        datagrab.set_speed_correction(new_value)
        self.speed_correction = new_value
        self._last_speed_cali_ts = now
        print(f"[速度校正] GPS 已鎖定，係數 {prev:.3f} -> {new_value:.3f} (比例 {ratio:.3f}，差 {diff:.1f} km/h)")
    
    def _physics_tick(self):
        """物理心跳：每 100ms 根據當前速度累積里程 (梯形積分法)"""
        current_time = time.time()
        time_delta = current_time - getattr(self, "last_physics_time", current_time)
        
        # 安全檢查
        if time_delta <= 0 or time_delta > 1.0:
            self.last_physics_time = current_time # 重置時間，避免跳變
            return
            
        self.last_physics_time = current_time
        
        # === 低頻率垃圾回收 ===
        # 每 5 分鐘執行一次 GC，清理累積的記憶體
        # 使用低頻率避免影響正常運作的流暢度
        if not hasattr(self, '_last_gc_time'):
            self._last_gc_time = current_time
        
        if current_time - self._last_gc_time >= 300:  # 300 秒 = 5 分鐘
            gc.collect()
            self._last_gc_time = current_time
            print(f"[GC] 執行定期垃圾回收 @ {time.strftime('%H:%M:%S')}")
        
        # 取得當前速度 (來自 _slot_set_speed 的最新 raw 值)
        # 如果還沒初始化過，就預設為 0
        current_speed = getattr(self, "calc_speed_source", 0.0)
        
        # 取得上一次計算時的速度 (用於梯形公式)
        prev_speed = getattr(self, "_prev_physics_speed", current_speed)
        
        # --- 修改點 B: 梯形積分公式 ---
        # 距離 = ((上一次速度 + 這一次速度) / 2) * 時間
        avg_speed = (prev_speed + current_speed) / 2.0
        
        if avg_speed > 0:
            # --- 修改點 C: 更新校正係數 ---
            # 根據你 101.2 vs 102.7 的數據，這裡應該接近 0.985
            # 先設 0.985 試試看，或者乾脆 1.0
            DISTANCE_CORRECTION = 0.985 
            
            # (km/h -> km/s) * s = km
            distance_increment = (avg_speed / 3600.0) * time_delta * DISTANCE_CORRECTION
            
            self.trip_card.add_distance(distance_increment)
            self.odo_card.add_distance(distance_increment)
            
            # 同時更新 trip_info_card 的本次里程（使用與 Trip A/B 相同的計算邏輯）
            if hasattr(self, 'trip_info_card'):
                self.trip_info_card.add_distance(distance_increment)
            
        # 記錄這次速度供下次梯形計算使用
        self._prev_physics_speed = current_speed
    
    @pyqtSlot(float)
    @perf_track
    def _slot_set_rpm(self, rpm):
        """Slot: 在主執行緒中更新轉速顯示 (含 GUI 端平滑)"""
        target = max(0, min(8, rpm))
        old_rpm = self.rpm
        
        # 追蹤最大 RPM (原始值×1000)
        get_max_value_logger().update_rpm(target * 1000)
        
        # GUI 端二次平滑：使用 EMA 讓指針移動更絲滑
        if self.rpm == 0:
            self.rpm = target  # 首次直接設定
        else:
            # 平滑插值：越接近目標越慢
            self.rpm = self.rpm * (1 - self.rpm_animation_alpha) + target * self.rpm_animation_alpha
        
        # 只在轉速變化明顯時才更新 UI（降低重繪頻率）
        if abs(self.rpm - old_rpm) > 0.02:  # 變化超過 0.02 千轉
            self.update_display()
        
        # 若引擎狀態從 on 掉到 off，立即上傳一次 MQTT
        self._maybe_publish_engine_off()
    
    @pyqtSlot(float)
    def _slot_set_temperature(self, temp):
        """Slot: 在主執行緒中更新水溫顯示"""
        self.temp = max(0, min(100, temp))
        
        # 追蹤最大水溫 (轉換為攝氏度)
        # temp 是百分比 (0-100)，轉換為 40-120°C
        temp_celsius = 40 + (self.temp / 100) * 80
        get_max_value_logger().update_coolant(temp_celsius)
        self.update_display()
    
    @pyqtSlot(float)
    def _slot_set_fuel(self, fuel):
        """Slot: 在主執行緒中更新油量顯示"""
        self.fuel = max(0, min(100, fuel))
        # Update ShutdownMonitor
        get_shutdown_monitor().update_fuel_level(self.fuel)
        self.update_display()
    
    @pyqtSlot(str)
    def _slot_set_gear(self, gear):
        """Slot: 在主執行緒中更新檔位顯示"""
        # 記錄換檔前的狀態（用於 D→N 偵測）
        prev_display_gear = self.gear
        
        # 儲存實際檔位
        self.actual_gear = gear
        
        # 決定顯示的檔位
        display_gear = self._get_display_gear(gear)
        
        gear_changed = display_gear != self.gear

        # 只在檔位真正改變時才收起控制面板
        if gear_changed and self.panel_visible:
            self.hide_control_panel()

        # 先更新狀態與畫面，再發布 MQTT，避免送出舊檔位
        self.gear = display_gear
        self.update_display()

        # 檔位變更時立即上傳 MQTT 數據
        if gear_changed and self._mqtt_connected:
            self._publish_telemetry()
        
        # === D→N 換檔時觸發 GPS 軟重啟（UBX Hot Start）===
        # 利用停車/暫停的自然時機刷新 GPS 模組狀態
        # 防止長時間行駛後 GPS 速度卡死的問題
        # 偵測：從行駛檔（D/1/2/3/4/5/S/L）→ 空檔（N）
        if gear_changed and display_gear == 'N':
            # prev_display_gear 保留了換檔前的顯示檔位
            # 只有從行駛檔切入 N 才觸發（排除 P→N、R→N）
            driving_gears = {'D', '1', '2', '3', '4', '5', 'S', 'L'}
            if prev_display_gear in driving_gears:
                try:
                    if hasattr(self, 'gps_monitor_thread') and self.gps_monitor_thread.isRunning():
                        self.gps_monitor_thread.request_soft_reset()
                        logger.info(f"[Dashboard] {prev_display_gear}→N detected, requested GPS soft reset")
                except Exception as e:
                    logger.debug(f"[Dashboard] GPS soft reset request failed: {e}")
    
    def _get_display_gear(self, actual_gear):
        """根據顯示模式決定要顯示的檔位"""
        # P, R, N 永遠直接顯示
        if actual_gear in ["P", "R", "N"]:
            return actual_gear
        
        # 數字檔位 (1-5) 根據模式決定
        if actual_gear in ["1", "2", "3", "4", "5"]:
            if self.show_detailed_gear:
                return actual_gear  # 顯示具體檔位
            else:
                return "D"  # 顯示 D
        
        # 其他情況直接顯示
        return actual_gear
    
    def _toggle_gear_display_mode(self):
        """切換檔位顯示模式（D 或具體檔位）"""
        self.show_detailed_gear = not self.show_detailed_gear
        
        # 重新計算顯示的檔位
        self.gear = self._get_display_gear(self.actual_gear)
        self.update_display()
    
    @pyqtSlot(str)
    def _slot_update_turn_signal(self, state):
        """Slot: 在主執行緒中更新方向燈狀態（從 CAN 訊號）
        Args:
            state: "left_on", "left_off", "right_on", "right_off", "both_on", "both_off", "off"
        
        RPI4 優化：收到 CAN 訊號時立即更新 UI，不等待 animation_timer
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
            # RPI4 優化：立即更新漸層位置和樣式
            self.left_gradient_pos = 1.0
            self.update_turn_signal_style()
        elif state == "left_off":
            self.left_turn_on = False
            # 熄滅動畫由 animation_timer 處理
        elif state == "right_on":
            self.right_turn_on = True
            self.left_turn_on = False
            # RPI4 優化：立即更新漸層位置和樣式
            self.right_gradient_pos = 1.0
            self.update_turn_signal_style()
        elif state == "right_off":
            self.right_turn_on = False
            # 熄滅動畫由 animation_timer 處理
        elif state == "both_on":
            self.left_turn_on = True
            self.right_turn_on = True
            # RPI4 優化：立即更新漸層位置和樣式
            self.left_gradient_pos = 1.0
            self.right_gradient_pos = 1.0
            self.update_turn_signal_style()
        elif state == "both_off":
            self.left_turn_on = False
            self.right_turn_on = False
            # 熄滅動畫由 animation_timer 處理
        elif state == "off":
            self.left_turn_on = False
            self.right_turn_on = False
            # 熄滅動畫由 animation_timer 處理

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
            # 如果在詳細視圖中，不處理左側區域的滑動（但仍然接受點擊返回）
            if self._in_detail_view:
                return
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
        
        # 安全檢查：確保 current_card_index 在有效範圍內
        if self.current_card_index >= current_row_cards:
            print(f"⚠️ 修正卡片索引: {self.current_card_index} -> 0 (max: {current_row_cards-1})")
            self.current_card_index = 0
            self.rows[self.current_row_index].setCurrentIndex(0)
            self.update_indicators()
        
        old_card_index = self.current_card_index
        new_card_index = (self.current_card_index + direction) % current_row_cards
        
        if old_card_index == new_card_index:
            return
        
        # 使用動畫切換卡片
        self._animate_card_switch(old_card_index, new_card_index, direction)
        
        # 顯示提示
        row1_card_names = ["音樂播放器", "導航", "門狀態"]
        row2_card_names = ["Trip卡片", "ODO卡片", "行程資訊"]
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
        
        # 安全檢查：確保 widget 存在
        if from_widget is None or to_widget is None:
            print(f"⚠️ 左側卡片切換錯誤: from_index={from_index}, to_index={to_index}, "
                  f"count={self.left_card_stack.count()}")
            self._left_card_animating = False
            return
        
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
            old_left_index = self.current_left_index
            self.current_left_index = to_index
            self._update_left_indicators()
            
            # Spotify 更新邏輯：檢查是否進入音樂卡片
            self._handle_spotify_update_on_card_change(old_left_index, to_index)
            
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
        
        # 安全檢查：確保 widget 存在
        if from_widget is None or to_widget is None:
            print(f"⚠️ 卡片切換錯誤: from_index={from_index}, to_index={to_index}, "
                  f"row={self.current_row_index}, count={current_row.count()}")
            self._right_card_animating = False
            # 重置到有效的卡片索引
            self.current_card_index = 0
            current_row.setCurrentIndex(0)
            self.update_indicators()
            return
        
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
            
            # Spotify 更新邏輯：檢查是否在音樂卡片所在的第一列
            self._handle_spotify_update_on_row_change(self.current_row_index)
            
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
        
        # 安全檢查：確保 widget 存在
        if from_widget is None or to_widget is None:
            print(f"⚠️ 列切換錯誤: from_row={from_row}, to_row={to_row}, "
                  f"count={self.row_stack.count()}")
            self._right_row_animating = False
            return
        
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
        
        # 注意：不再禁用全局滑動，右側卡片仍可操作
        # _in_detail_view 狀態會阻止左側區域的滑動切換
        
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
        prev_index = self._detail_gauge_index
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
        
        # 注意：不再需要恢復滑動，因為進入時沒有禁用
        
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
        row1_card_names = ["音樂播放器", "導航", "門狀態"]
        row2_card_names = ["Trip卡片", "ODO卡片", "行程資訊"]
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
            self.distance_speed = self.speed
            # 轉速與速度成比例，但不超過紅區
            self.rpm = min(7, 0.8 + (self.speed / 180.0) * 5.0)
        elif key == Qt.Key.Key_S:
            self.speed = max(0, self.speed - 5)
            self.distance_speed = self.speed
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
        
        # F10 / =: 電壓歸零測試（觸發關機對話框）
        elif key == Qt.Key.Key_F10 or key == Qt.Key.Key_Equal:
            self.trigger_voltage_zero_test()

        # R: 雷達測試 (循環切換測試資料)
        elif key == Qt.Key.Key_R:
            if not hasattr(self, '_radar_test_idx'):
                self._radar_test_idx = 0
            
            test_patterns = [
                "(LR:0,RR:0,LF:0,RF:0)", # 全關
                "(LR:1,RR:0,LF:0,RF:0)", # 左後黃
                "(LR:2,RR:0,LF:0,RF:0)", # 左後紅
                "(LR:0,RR:1,LF:0,RF:0)", # 右後黃
                "(LR:0,RR:2,LF:0,RF:0)", # 右後紅
                "(LR:0,RR:0,LF:1,RF:0)", # 左前黃
                "(LR:0,RR:0,LF:2,RF:0)", # 左前紅
                "(LR:0,RR:0,LF:0,RF:1)", # 右前黃
                "(LR:0,RR:0,LF:0,RF:2)", # 右前紅
                "(LR:1,RR:1,LF:1,RF:1)", # 全黃
                "(LR:2,RR:2,LF:2,RF:2)", # 全紅
            ]
            pattern = test_patterns[self._radar_test_idx]
            self.signal_update_radar.emit(pattern)
            print(f"雷達測試: {pattern}")
            
            # 切換到門卡片看效果
            DOOR_ROW_INDEX = 0
            DOOR_CARD_INDEX = 2
            self.current_row_index = DOOR_ROW_INDEX
            self.current_card_index = DOOR_CARD_INDEX
            self.row_stack.setCurrentIndex(DOOR_ROW_INDEX)
            self.rows[DOOR_ROW_INDEX].setCurrentIndex(DOOR_CARD_INDEX)
            self.update_indicators()
            
            self._radar_test_idx = (self._radar_test_idx + 1) % len(test_patterns)

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
        # 發送 signal 給行程資訊卡片（用於計算油耗）
        self.signal_update_turbo.emit(turbo_bar)
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
        # 電壓歸零測試鎖定：測試中忽略正常電壓更新
        if getattr(self, '_voltage_test_locked', False) and voltage > 1.0:
            return  # 測試中，忽略正常電壓
        
        self.battery = voltage
        
        # === 關機監控：必須即時更新 (不受節流影響) ===
        if hasattr(self, '_shutdown_monitor'):
            self._shutdown_monitor.update_voltage(voltage)
        
        # === UI 更新：節流 (每 0.5 秒) ===
        now = time.time()
        if not hasattr(self, '_last_battery_ui_update'):
            self._last_battery_ui_update = 0
        
        if now - self._last_battery_ui_update >= 0.5:
            # 更新四宮格卡片
            if hasattr(self, 'quad_gauge_card'):
                self.quad_gauge_card.set_battery(voltage)
            # 如果在詳細視圖中且顯示的是 BATTERY，也更新
            if self._in_detail_view and self._detail_gauge_index == 3:
                self.quad_gauge_detail.set_value(voltage)
            
            self._last_battery_ui_update = now
        
        # 若引擎狀態從 on 掉到 off，立即上傳一次 MQTT
        self._maybe_publish_engine_off()
    
    def set_fuel_consumption(self, instant: float, avg: float):
        """外部數據接口：設置油耗 - 透過 Signal 發送，由主執行緒執行
        Args:
            instant: 瞬時油耗 (L/100km)
            avg: 平均油耗 (L/100km)
        """
        self.signal_update_fuel_consumption.emit(instant, avg)
    
    @pyqtSlot(float, float)
    def _slot_update_fuel_consumption(self, instant: float, avg: float):
        """Slot: 在主執行緒中更新油耗顯示"""
        # 更新行程資訊卡片
        if hasattr(self, 'trip_info_card'):
            self.trip_info_card.update_fuel_consumption(instant, avg)

        # 更新關機監控器的行程資訊
        if hasattr(self, '_shutdown_monitor') and hasattr(self, 'trip_info_card'):
            trip_info = self.trip_info_card.get_trip_info()
            print(f"[DEBUG] get_trip_info result: {trip_info}")
            print(f"[DEBUG] trip_info_card.start_time: {self.trip_info_card.start_time}")
            print(f"[DEBUG] trip_info_card.trip_distance: {self.trip_info_card.trip_distance}")
            print(f"[DEBUG] trip_info_card.avg_fuel: {self.trip_info_card.avg_fuel}")
            if trip_info:
                self._shutdown_monitor.update_trip_info(trip_info['elapsed_time'], trip_info['trip_distance'], trip_info['avg_fuel'])
    
    def trigger_voltage_zero_test(self):
        """觸發電壓歸零測試（F10 或 = 鍵）"""
        # 如果已經在測試中，忽略
        if getattr(self, '_voltage_test_locked', False):
            print("⚡ [測試] 電壓測試已在進行中...")
            return
        
        print("⚡ [測試] 按鍵觸發電壓歸零測試")
        current_battery = self.battery if self.battery is not None else 0.0
        print(f"   電壓: {current_battery:.1f}V → 0.0V")
        
        # 鎖定電壓測試，忽略後續的正常電壓更新
        self._voltage_test_locked = True
        
        # 先設定正常電壓（確保關機監控器記錄過正常狀態）
        if hasattr(self, '_shutdown_monitor'):
            if not self._shutdown_monitor.was_powered:
                print("   先模擬正常電壓狀態...")
                self._voltage_test_locked = False  # 暫時解鎖
                self._shutdown_monitor.update_voltage(12.5)
                self._voltage_test_locked = True   # 重新鎖定
            
            # 連接對話框關閉事件來解鎖
            def on_dialog_closed():
                self._voltage_test_locked = False
                print("⚡ [測試] 電壓測試結束，恢復正常更新")
            
            # 連接取消和確認信號
            if self._shutdown_monitor.shutdown_dialog:
                try:
                    self._shutdown_monitor.shutdown_dialog.shutdown_cancelled.disconnect(on_dialog_closed)
                except:
                    pass
                try:
                    self._shutdown_monitor.shutdown_dialog.shutdown_confirmed.disconnect(on_dialog_closed)
                except:
                    pass
                try:
                    self._shutdown_monitor.shutdown_dialog.exit_app.disconnect(on_dialog_closed)
                except:
                    pass
            
            # 模擬電壓掉落到 0V
            self._voltage_test_locked = False  # 暫時解鎖讓 0V 可以更新
            self.set_battery(0.0)
            self.set_battery(0.0)
            self.set_battery(0.0)  # 連續三次觸發防抖
            self._voltage_test_locked = True   # 重新鎖定
            
            # 重新連接信號（在對話框創建後）
            if self._shutdown_monitor.shutdown_dialog:
                self._shutdown_monitor.shutdown_dialog.shutdown_cancelled.connect(on_dialog_closed)
                self._shutdown_monitor.shutdown_dialog.shutdown_confirmed.connect(on_dialog_closed)
                self._shutdown_monitor.shutdown_dialog.exit_app.connect(on_dialog_closed)
    
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

    def update_parking_brake_display(self):
        """更新手煞車顯示"""
        if self.parking_brake:
            # 紅色 - 手煞車拉起
            self.parking_brake_label.setText("P")
            self.parking_brake_label.setStyleSheet("""
                color: #f66;
                font-size: 32px;
                font-weight: bold;
                font-family: Arial;
                background: rgba(255, 100, 100, 0.2);
                border: 2px solid #f66;
                border-radius: 25px;
            """)
        else:
            # 不顯示
            self.parking_brake_label.setText("")
            self.parking_brake_label.setStyleSheet("""
                color: #f66;
                font-size: 32px;
                font-weight: bold;
                font-family: Arial;
                background: transparent;
                border: none;
            """)

    def _slot_update_parking_brake(self, is_engaged: bool):
        """Slot: 更新手煞車狀態（從 GPIO 訊號）"""
        print(f"[Dashboard] 收到手煞車信號: {is_engaged}")
        self.parking_brake = is_engaged
        self.update_parking_brake_display()

    def _slot_update_radar(self, radar_str: str):
        """Slot: 更新雷達狀態 (格式: "(LR:0,RR:0,LF:0,RF:0)" 或 "LR:0,RR:0,LF:0,RF:0")
        
        自動切換規則：
        - 當車速 <= 10 km/h
        - 檔位在 D 或 R
        - 有任意雷達觸發（值 > 0）
        - 1 分鐘內只自動切換一次
        """
        print(f"[Dashboard] Received radar data: {radar_str}")  # Debug 用
        if hasattr(self, 'door_card'):
            self.door_card.set_radar_status(radar_str)
        
        # 雷達自動切換邏輯
        import re
        try:
            # 解析雷達數據
            pattern = r"LR:(\d),RR:(\d),LF:(\d),RF:(\d)"
            match = re.search(pattern, radar_str)
            if match:
                lr = int(match.group(1))
                rr = int(match.group(2))
                lf = int(match.group(3))
                rf = int(match.group(4))
                
                # 檢查是否有任意雷達觸發
                has_radar_trigger = (lf > 0 or rf > 0 or lr > 0 or rr > 0)
                
                # 檢查速度條件（<= 10 km/h）
                speed_ok = self.speed <= 10
                
                # 檢查檔位條件（D 或 R）
                gear_ok = self.gear in ['D', 'R']
                
                # 檢查時間間隔（距離上次切換是否已超過 60 秒）
                current_time = time.time()
                time_ok = (current_time - self.last_radar_auto_switch_time) >= 60
                
                # 檢查是否不在門卡片上（避免重複切換）
                not_on_door_card = not (self.current_row_index == 0 and self.current_card_index == 2)
                
                if has_radar_trigger and speed_ok and gear_ok and time_ok and not_on_door_card:
                    print(f"[Dashboard] 雷達自動切換觸發: 速度={self.speed}km/h, 檔位={self.gear}, 雷達=(LF:{lf},RF:{rf},LR:{lr},RR:{rr})")
                    
                    # 記錄切換前的位置（供跳回使用）
                    self.previous_row_index = self.current_row_index
                    self.previous_card_index = self.current_card_index
                    
                    # 切換到門卡片（第一列第三張，索引為 2）
                    DOOR_ROW_INDEX = 0
                    DOOR_CARD_INDEX = 2
                    
                    self.current_row_index = DOOR_ROW_INDEX
                    self.current_card_index = DOOR_CARD_INDEX
                    self.row_stack.setCurrentIndex(DOOR_ROW_INDEX)
                    self.rows[DOOR_ROW_INDEX].setCurrentIndex(DOOR_CARD_INDEX)
                    self.update_indicators()
                    
                    # 更新最後切換時間
                    self.last_radar_auto_switch_time = current_time
                    
        except Exception as e:
            print(f"[Dashboard] 雷達自動切換錯誤: {e}")
    
    def _on_accent_color_changed(self, color_hex: str):
        """當強調色改變時，重新整理所有卡片的 UI"""
        print(f"[Dashboard] 強調色已更改為 {color_hex}，正在刷新卡片...")
        import re

        previous_accent = getattr(self, '_last_accent_color', color_hex)
        self._last_accent_color = color_hex
        
        def refresh_widget_tree(widget):
            try:
                ss = widget.styleSheet()
                if ss:
                    refreshed_ss = reapply_t_function(ss)
                    if previous_accent and previous_accent != color_hex:
                        refreshed_ss = re.sub(re.escape(previous_accent), color_hex, refreshed_ss, flags=re.IGNORECASE)

                    widget.setStyleSheet("")
                    widget.style().unpolish(widget)
                    widget.setStyleSheet(refreshed_ss)
                    widget.style().polish(widget)
                for child in widget.children():
                    if isinstance(child, QWidget):
                        refresh_widget_tree(child)
            except Exception:
                pass
        
        app = QApplication.instance()
        if app:
            for widget in app.topLevelWidgets():
                refresh_widget_tree(widget)
        
        self.update()
        print("[Dashboard] 卡片 UI 已刷新")
    
    def set_parking_brake(self, is_engaged: bool):
        """設定手煞車狀態 - 供外部呼叫"""
        print(f"[Dashboard] 設定手煞車: {is_engaged}")
        self.parking_brake = is_engaged
        self.update_parking_brake_display()

    def update_display(self):
        """更新所有儀表顯示"""
        # 更新四宮格卡片
        # rpm 是以「千轉」為單位 (0-8)，轉換為實際轉速
        self.quad_gauge_card.set_rpm(self.rpm * 1000)
        
        # temp 是百分比 (0-100)，轉換為大約的攝氏溫度
        # 假設 0% = 40°C, 100% = 120°C
        # 如果 temp 為 None（OBD 未回應），則傳入 None
        if self.temp is not None:
            temp_celsius = 40 + (self.temp / 100) * 80
        else:
            temp_celsius = None
        self.quad_gauge_card.set_coolant_temp(temp_celsius)
        
        # 如果在詳細視圖中，同步更新
        if self._in_detail_view:
            if self._detail_gauge_index == 0:  # RPM
                self.quad_gauge_detail.update_value(self.rpm * 1000)
            elif self._detail_gauge_index == 1:  # 水溫
                self.quad_gauge_detail.update_value(temp_celsius)
        
        self.fuel_gauge.set_value(self.fuel)
        if hasattr(self, "fuel_percent_label"):
            self.fuel_percent_label.setText(f"{self.fuel:.0f}%")
        
        # 決定顯示哪個速度
        import vehicle.datagrab as datagrab
        # 邏輯: 僅當 (速度同步開啟 AND GPS定位完成 AND OBD速度 >= 20) 時使用 GPS 速度
        # 這是為了避免低速時的 GPS 漂移
        use_gps = (datagrab.gps_speed_mode and 
                   self.is_gps_fixed and 
                   self.speed >= 20.0)
                   
        if use_gps:
            # 使用 GPS 速度
            self.speed_label.setText(str(int(self.current_gps_speed)))
        else:
            # 使用 CAN/Sim 速度 (施密特觸發器處理後的穩定值)
            self.speed_label.setText(str(self._displayed_speed_int))
        
        # 更新檔位顯示顏色
        gear_colors = {
            "P": "#6af",   # 藍色
            "R": "#f66",   # 紅色
            "N": "#fa6",   # 橙色
            "D": "#4ade80",  # 綠色
            "1": "#6af",   # 藍色 (1檔)
            "2": "#6af",   # 藍色 (2檔)
            "3": "#6af",   # 藍色 (3檔)
            "4": "#6af",   # 藍色 (4檔)
            "5": "#6af",   # 藍色 (5檔)
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

def run_dashboard(
    on_dashboard_ready=None,
    window_title=None,
    setup_data_source=None,
    startup_info=None,
    skip_splash=False,
    hardware_init_callback=None,
    hardware_init_timeout=60.0,
    skip_gps=False
):
    """
    統一的儀表板啟動函數 - 所有入口點都應使用此函數
    
    這個函數處理：
    1. QApplication 初始化
    2. 啟動進度視窗顯示（如果提供 startup_info 或 hardware_init_callback）
    3. 硬體初始化（如果在 RPi 上且提供 hardware_init_callback）
    4. Dashboard 建立
    5. SplashScreen 播放（如果有）
    6. 正確的啟動順序（splash 結束後才啟動 dashboard 邏輯）
    7. 資料來源設定
    
    Args:
        on_dashboard_ready: 可選的回調函數，在 dashboard 完全準備好後呼叫
                           簽名: callback(dashboard) -> cleanup_func 或 None
                           返回的 cleanup_func 會在程式結束時被呼叫
        window_title: 可選的視窗標題
        setup_data_source: 可選的資料來源設定函數
                          簽名: setup_func(dashboard) -> cleanup_func 或 None
                          這個會在 splash 結束後、start_dashboard 之前呼叫
        startup_info: 可選的啟動資訊列表，用於顯示進度視窗
                     格式: [(step_name, detail_text), ...]
        skip_splash: 是否跳過開機動畫（例如：車輛不在 P 檔時）
        hardware_init_callback: 可選的硬體初始化回調函數（用於 RPi）
                               簽名: callback(progress_window, timeout) -> (success, result_data)
                               - progress_window: StartupProgressWindow 實例，用於更新 GUI
                               - timeout: 超時時間（秒）
                               - 返回: (success: bool, result_data: any)
        hardware_init_timeout: 硬體初始化超時時間（秒），預設 60 秒
    
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
        
        # 帶啟動進度視窗
        startup_steps = [
            ("📺 設定螢幕顯示", "旋轉螢幕 90°"),
            ("👆 校正觸控面板", "USB2IIC_CTP_CONTROL"),
            ("🔊 初始化音訊服務", "PipeWire"),
        ]
        run_dashboard(startup_info=startup_steps)
        
        # 跳過開機動畫（例如車輛不在 P 檔）
        run_dashboard(skip_splash=True)
        
        # 帶硬體初始化（RPi 專用）
        def init_hardware(progress_window, timeout):
            # 在這裡執行硬體初始化，可以呼叫 progress_window.update_hardware_status() 更新 GUI
            ...
            return success, can_bus
        run_dashboard(hardware_init_callback=init_hardware)
    """
    app = QApplication(sys.argv)
    
    # 檢測環境
    is_production = is_production_environment()
    env_name = "生產環境（樹莓派）" if is_production else "開發環境（Mac/Windows）"
    print(f"檢測到 {env_name}")
    print(f"系統: {platform.system()}, 全螢幕模式: {'是' if is_production else '否'}")
    
    # 生產環境（樹莓派）隱藏滑鼠游標
    if is_production:
        app.setOverrideCursor(Qt.CursorShape.BlankCursor)
        print("已隱藏滑鼠游標")
    
    # === 啟動進度視窗 & 硬體初始化 ===
    progress_window = None
    hardware_init_result = None  # 儲存硬體初始化結果
    
    # 決定是否需要顯示進度視窗
    need_progress_window = (startup_info and len(startup_info) > 0) or (hardware_init_callback and is_production)
    
    if need_progress_window:
        progress_window = StartupProgressWindow()
        
        if is_production:
            progress_window.showFullScreen()
        else:
            progress_window.resize(800, 300)  # 增加高度以容納硬體狀態
            progress_window.show()
        
        QApplication.processEvents()
        
        # === 階段 1: 硬體初始化（如果有回調）===
        if hardware_init_callback and is_production:
            print("🔧 開始硬體初始化...")
            progress_window.set_hardware_retry_mode(True)
            QApplication.processEvents()
            
            # 執行硬體初始化回調
            # 回調函數會使用 progress_window.update_hardware_status() 更新 GUI
            try:
                success, result = hardware_init_callback(progress_window, hardware_init_timeout)
                hardware_init_result = (success, result)
                
                # 硬體初始化完成
                can_only = success and not getattr(result, 'all_ready', True) if hasattr(result, 'all_ready') else False
                progress_window.hardware_init_complete(success, can_only=can_only)
                QApplication.processEvents()
                
                if not success:
                    print("❌ 硬體初始化失敗")
                    # 顯示錯誤訊息但繼續
                    time.sleep(2.0)
            except Exception as e:
                print(f"❌ 硬體初始化異常: {e}")
                hardware_init_result = (False, None)
                progress_window.hardware_init_complete(False)
                time.sleep(2.0)
        
        # === 階段 2: 啟動步驟（如果有）===
        if startup_info and len(startup_info) > 0:
            progress_window.set_steps(startup_info)
            
            # 模擬步驟執行（每步 0.2 秒）
            for i in range(len(startup_info)):
                progress_window.show_step(i)
                QApplication.processEvents()
                time.sleep(0.2)
        
        # 完成並關閉進度視窗
        progress_window.complete()
        QApplication.processEvents()
        time.sleep(0.3)
        progress_window.close()
        progress_window = None
    
    # 建立主儀表板
    dashboard = Dashboard(skip_gps=skip_gps)
    
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
    splash_video_path = os.path.join(os.path.dirname(__file__), "assets", "video", "Splash_short.mp4")
    has_splash = os.path.exists(splash_video_path) and not skip_splash
    
    if skip_splash:
        print("🚗 非 P 檔啟動，跳過開機動畫")
    
    if has_splash:
        splash = SplashScreen(splash_video_path)
        on_splash_finished.splash = splash
        
        splash.finished.connect(on_splash_finished)
        
        if is_production:
            splash.showFullScreen()
        else:
            splash.resize(800, 200)  # 4:1 比例 (1920x480 影片的縮小版)
            splash.show()
    else:
        if not skip_splash:
            print("未找到 assets/video/Splash_short.mp4，跳過啟動畫面")
        # 沒有 splash 或要求跳過，直接執行啟動流程
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
        
        # 儲存最大值記錄
        try:
            max_logger = get_max_value_logger()
            max_logger.save()
        except Exception as e:
            print(f"儲存最大值記錄時發生錯誤: {e}")
        
        # 執行所有清理函數
        for cleanup in cleanup_funcs:
            try:
                cleanup()
            except Exception as e:
                print(f"清理時發生錯誤: {e}")
    
    sys.exit(exit_code)

# 全域變數儲存硬體初始化結果
_hardware_init_result = None


def main():
    """主程式進入點"""
    from vehicle.hardware_init import initialize_hardware
    from vehicle import datagrab
    import cantools
    global _hardware_init_result
    
    def init_hardware(progress_window, timeout):
        """硬體初始化回調 - 初始化 CAN Bus、GPIO 等"""
        global _hardware_init_result
        success, status, can_bus = initialize_hardware(
            timeout=timeout,
            require_gps=False,  # GPS 不是必需的
            require_gpio=False,  # GPIO 不是必需的（可用鍵盤）
            show_progress=True
        )
        
        # 載入 DBC 文件
        db = None
        try:
            dbc_path = os.path.join(os.path.dirname(__file__), 'luxgen_m7_2009.dbc')
            if os.path.exists(dbc_path):
                db = cantools.database.load_file(dbc_path)
                print(f"[OK] DBC 文件已載入: {dbc_path}")
            else:
                print(f"[WARNING] DBC 文件不存在: {dbc_path}")
        except Exception as e:
            print(f"[ERROR] 載入 DBC 文件失敗: {e}")
        
        _hardware_init_result = (success, status, can_bus, db)
        return success, status
    
    def setup_data_source(dashboard):
        """設定 CAN Bus 資料來源 - 在 dashboard 啟動後呼叫"""
        global _hardware_init_result
        
        if _hardware_init_result is None:
            print("[ERROR] 硬體初始化結果不存在")
            return None
        
        success, status, can_bus, db = _hardware_init_result
        
        if can_bus is None:
            print("[WARNING] CAN Bus 未初始化，儀表板將顯示預設值 '--'")
            return None
        
        # 連接信號到 Dashboard
        signals = datagrab.WorkerSignals()
        signals.update_rpm.connect(dashboard.set_rpm)
        signals.update_speed.connect(dashboard.set_speed)
        signals.update_temp.connect(dashboard.set_temperature)
        signals.update_fuel.connect(dashboard.set_fuel)
        signals.update_gear.connect(dashboard.set_gear)
        signals.update_turn_signal.connect(dashboard.set_turn_signal)
        signals.update_door_status.connect(dashboard.set_door_status)
        signals.update_turbo.connect(dashboard.set_turbo)
        signals.update_battery.connect(dashboard.set_battery)
        signals.update_fuel_consumption.connect(dashboard.set_fuel_consumption)
        
        # 啟動背景執行緒
        import threading
        t_receiver = threading.Thread(
            target=datagrab.unified_receiver, 
            args=(can_bus, db, signals), 
            daemon=True, 
            name="CAN-Receiver"
        )
        t_query = threading.Thread(
            target=datagrab.obd_query, 
            args=(can_bus, signals), 
            daemon=True, 
            name="OBD-Query"
        )
        
        t_receiver.start()
        t_query.start()
        
        print("[OK] CAN Bus 資料執行緒已啟動")
        
        # 返回清理函數
        def cleanup():
            datagrab.stop_threads = True
            can_bus.shutdown()
            print("[OK] CAN Bus 已關閉")
        
        return cleanup
    
    run_dashboard(
        hardware_init_callback=init_hardware,
        setup_data_source=setup_data_source
    )

if __name__ == "__main__":
    main()
