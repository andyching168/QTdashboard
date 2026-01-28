#!/usr/bin/env python3
"""
關機檢測模組 - 偵測電壓掉落並自動關機

當電壓從 >10V 掉到 ≈0V 時，顯示倒數計時對話框
如果使用者在 30 秒內按「取消」，則不關機
否則自動執行 sudo poweroff

測試模式（非 Raspberry Pi）：
    - 不執行關機命令，改為退出程式
    - 可透過 test_mode 參數控制
"""

import os
import sys
import platform
import subprocess
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont
import threading
from location_notifier import notify_current_location


def is_raspberry_pi():
    """檢測是否在樹莓派上運行"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            return 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo
    except:
        return False


class ShutdownDialog(QDialog):
    """關機倒數對話框"""
    
    shutdown_confirmed = pyqtSignal()  # 確認關機信號
    shutdown_cancelled = pyqtSignal()  # 取消關機信號
    exit_app = pyqtSignal()  # 退出程式信號（測試模式用）
    
    def __init__(self, countdown_seconds=30, test_mode=None, parent=None):
        # macOS 上不設定 parent，使用獨立視窗
        if platform.system() == 'Darwin':
            super().__init__(None)  # 無 parent
        else:
            super().__init__(parent)
        
        self._parent_window = parent  # 保存父視窗引用（用於置中）
        self.countdown = countdown_seconds
        self.initial_countdown = countdown_seconds
        
        # 測試模式：自動偵測或手動指定
        if test_mode is None:
            self.test_mode = not is_raspberry_pi()
        else:
            self.test_mode = test_mode
        
        # 設置視窗屬性 - macOS 需要特別處理
        if platform.system() == 'Darwin':
            # macOS: 使用獨立最上層視窗
            self.setWindowFlags(
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool  # Tool 視窗在 macOS 上更容易顯示在前景
            )
            self.setWindowTitle("電源中斷警告")
        else:
            # Linux/RPi: 使用無框架模式，但不使用透明背景（會影響觸控）
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | 
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Dialog
            )
            # 注意：不設置 WA_TranslucentBackground，否則觸控螢幕可能無法點擊
            # self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.setModal(False)  # 非模態，避免阻塞主視窗
        
        # 確保可以接收觸控/滑鼠事件
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        
        # 固定大小（加大以容納更大的按鈕）
        self.setFixedSize(550, 350)
        
        self._init_ui()
        self._setup_timer()
    
    def _init_ui(self):
        """初始化 UI"""
        # 設置對話框本身的背景（不使用子容器，避免觸控問題）
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a1a1a, stop:1 #1a0a0a);
                border-radius: 20px;
                border: 3px solid #f44;
            }
        """)
        
        # 直接在對話框上創建佈局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # 警告圖標
        icon_label = QLabel("⚠️")
        icon_label.setStyleSheet("font-size: 48px; background: transparent;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 標題
        title_label = QLabel("電源已中斷")
        title_label.setStyleSheet("""
            color: #f44;
            font-size: 28px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 說明
        desc_label = QLabel("偵測到電壓掉落，系統即將關機")
        desc_label.setStyleSheet("""
            color: #ccc;
            font-size: 16px;
            background: transparent;
        """)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 倒數計時
        action_text = "退出程式" if self.test_mode else "自動關機"
        self.countdown_label = QLabel(f"{self.countdown} 秒後{action_text}")
        self.countdown_label.setStyleSheet("""
            color: #ff8800;
            font-size: 24px;
            font-weight: bold;
            background: transparent;
        """)
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 按鈕區域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(30)  # 增加按鈕間距
        
        # 取消按鈕 - 加大尺寸方便觸控
        self.cancel_btn = QPushButton("取消關機")
        self.cancel_btn.setFixedSize(200, 60)  # 加大按鈕
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 確保可以獲得焦點
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a55;
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a5a65;
            }
            QPushButton:pressed {
                background-color: #3a3a45;
            }
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        
        # 立即關機/退出按鈕 - 加大尺寸方便觸控
        btn_text = "立即退出" if self.test_mode else "立即關機"
        self.shutdown_btn = QPushButton(btn_text)
        self.shutdown_btn.setFixedSize(200, 60)  # 加大按鈕
        self.shutdown_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.shutdown_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 確保可以獲得焦點
        self.shutdown_btn.setStyleSheet("""
            QPushButton {
                background-color: #c33;
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d44;
            }
            QPushButton:pressed {
                background-color: #b22;
            }
        """)
        self.shutdown_btn.clicked.connect(self._on_shutdown)
        
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.shutdown_btn)
        button_layout.addStretch()
        
        # 組合佈局
        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        layout.addWidget(self.countdown_label)
        layout.addStretch()
        layout.addLayout(button_layout)
    
    def _setup_timer(self):
        """設置倒數計時器"""
        self.timer = QTimer()
        self.timer.timeout.connect(self._on_tick)
    
    def showEvent(self, event):
        """顯示時開始倒數"""
        super().showEvent(event)
        self.countdown = self.initial_countdown
        self._update_countdown_display()
        self.timer.start(1000)  # 每秒更新
        
        # 置中顯示
        if platform.system() == 'Darwin':
            # macOS: 使用螢幕中心
            from PyQt6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            if screen:
                screen_geo = screen.availableGeometry()
                x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
                y = screen_geo.y() + (screen_geo.height() - self.height()) // 2
                self.move(x, y)
        elif self._parent_window:
            # Linux/RPi: 使用父視窗中心
            parent_rect = self._parent_window.geometry()
            x = parent_rect.x() + (parent_rect.width() - self.width()) // 2
            y = parent_rect.y() + (parent_rect.height() - self.height()) // 2
            self.move(x, y)
        elif self.parent():
            parent_rect = self.parent().geometry()
            x = parent_rect.x() + (parent_rect.width() - self.width()) // 2
            y = parent_rect.y() + (parent_rect.height() - self.height()) // 2
            self.move(x, y)
    
    def hideEvent(self, event):
        """隱藏時停止計時"""
        super().hideEvent(event)
        self.timer.stop()
    
    def _on_tick(self):
        """每秒更新倒數"""
        self.countdown -= 1
        self._update_countdown_display()
        
        if self.countdown <= 0:
            self.timer.stop()
            self._do_shutdown()
    
    def _update_countdown_display(self):
        """更新倒數顯示"""
        if self.countdown <= 5:
            # 最後 5 秒變紅色
            self.countdown_label.setStyleSheet("""
                color: #f44;
                font-size: 24px;
                font-weight: bold;
                background: transparent;
            """)
        
        action_text = "退出程式" if self.test_mode else "自動關機"
        self.countdown_label.setText(f"{self.countdown} 秒後{action_text}")
    
    def _on_cancel(self):
        """取消關機"""
        self.timer.stop()
        self.shutdown_cancelled.emit()
        self.close()
    
    def _on_shutdown(self):
        """立即關機"""
        self.timer.stop()
        self._do_shutdown()
    
    def _do_shutdown(self):
        """執行關機或退出程式"""
        # 關機前再次儲存速度校正係數（確保最新值被保存）
        try:
            import datagrab
            datagrab.persist_speed_correction()
            print(f"[速度校正] 關機前儲存校正係數 {datagrab.get_speed_correction():.3f}")
        except Exception as e:
            print(f"[速度校正] 儲存失敗: {e}")
        
        # 強制同步檔案系統，確保資料寫入磁碟
        try:
            os.sync()
            print("[Sync] 檔案系統已同步")
        except Exception as e:
            print(f"[Sync] 同步失敗: {e}")
        
        if self.test_mode:
            print("🟡 [測試模式] 退出程式...")
            self.exit_app.emit()
            self.close()
            # 延遲退出，讓信號有時間處理
            QTimer.singleShot(100, lambda: QApplication.instance().quit())
        else:
            print("🔴 執行系統關機...")
            self.shutdown_confirmed.emit()
            self.close()
            
            # 執行關機命令
            try:
                subprocess.run(['sudo', 'poweroff'], check=False)
            except Exception as e:
                print(f"關機失敗: {e}")


class ShutdownMonitor(QObject):
    """關機監控器 - 監測電壓變化
    
    功能：
    1. 電壓掉落偵測：當電壓從正常值掉到接近 0 時，觸發關機
    2. 無訊號超時偵測：當 OBD 連續 3 分鐘沒有收到電壓訊號時，觸發關機
       （用於儀表開機但車子從未發動的情況）
    """
    
    # 信號
    power_lost = pyqtSignal()      # 電源中斷
    power_restored = pyqtSignal()  # 電源恢復
    exit_app = pyqtSignal()        # 退出程式（測試模式用）
    no_signal_timeout = pyqtSignal()  # 無訊號超時
    
    # 無電壓訊號超時時間（秒）
    NO_VOLTAGE_SIGNAL_TIMEOUT = 180  # 3 分鐘（針對從未發動的情況）
    
    # 快速斷電檢測超時時間（秒）
    # 當 was_powered=True 時，如果連續這麼久沒收到電壓更新，視為熄火
    QUICK_POWER_LOSS_TIMEOUT = 15  # 15 秒（從 5 秒增加，避免誤觸發）
    
    def __init__(self, 
                 voltage_threshold=10.0,      # 正常電壓閾值
                 low_voltage_threshold=1.0,   # 低電壓閾值 (視為斷電)
                 debounce_count=3,            # 需要連續幾次低電壓才觸發
                 test_mode=None,              # 測試模式（None=自動偵測）
                 parent=None):
        super().__init__(parent)
        
        self.voltage_threshold = voltage_threshold
        self.low_voltage_threshold = low_voltage_threshold
        self.debounce_count = debounce_count
        
        # 測試模式：自動偵測或手動指定
        if test_mode is None:
            self.test_mode = not is_raspberry_pi()
        else:
            self.test_mode = test_mode
        
        if self.test_mode:
            print("[ShutdownMonitor] 測試模式：電壓歸零將退出程式而非關機")
        
        # 狀態
        self.last_voltage = 0.0
        self.was_powered = False  # 是否曾經有過正常電壓
        self.low_voltage_count = 0
        self.power_lost_triggered = False
        
        # === 無電壓訊號超時監控 ===
        self.last_voltage_received_time = None  # 上次收到電壓訊號的時間
        self.no_signal_triggered = False        # 是否已觸發無訊號超時
        self._no_signal_check_timer = None      # 檢查計時器
        
        # === 快速斷電檢測 ===
        self._quick_power_loss_timer = None     # 快速斷電檢測計時器
        self._quick_power_loss_triggered = False  # 是否已觸發快速斷電
        
        # 關機對話框
        self.shutdown_dialog = None
        
        # 車輛狀態
        self.current_fuel_level = None
        self.current_avg_fuel = None
        self.trip_elapsed_time = None  # 字串格式 "hh:mm"
        self.trip_distance = None

    def update_fuel_level(self, level: float):
        """更新油量"""
        self.current_fuel_level = level

    def update_avg_fuel(self, avg_fuel: float):
        """更新平均油耗"""
        self.current_avg_fuel = avg_fuel

    def update_trip_info(self, elapsed_time: str, distance: float, avg_fuel: float = None):
        """更新本次行程資訊"""
        self.trip_elapsed_time = elapsed_time
        self.trip_distance = distance
        if avg_fuel is not None:
            self.current_avg_fuel = avg_fuel
    
    def start_no_signal_monitoring(self):
        """啟動無電壓訊號監控
        
        應在 Dashboard 啟動後呼叫，開始監控是否收到電壓訊號。
        
        兩種超時機制：
        1. 快速斷電檢測 (5秒): 曾經有正常電壓後突然沒有回應 → 熄火
        2. 長時間無訊號 (3分鐘): 從未收到正常電壓 → OBD 未連接/車輛從未發動
        """
        import time
        
        # 記錄啟動時間作為初始參考點
        self.last_voltage_received_time = time.time()
        self.no_signal_triggered = False
        self._quick_power_loss_triggered = False
        
        # 建立並啟動快速斷電檢測計時器（每 1 秒檢查一次）
        if self._quick_power_loss_timer is None:
            self._quick_power_loss_timer = QTimer()
            self._quick_power_loss_timer.timeout.connect(self._check_quick_power_loss)
        
        self._quick_power_loss_timer.start(1000)  # 每 1 秒檢查一次
        
        # 建立並啟動長時間無訊號檢查計時器（每 30 秒檢查一次）
        if self._no_signal_check_timer is None:
            self._no_signal_check_timer = QTimer()
            self._no_signal_check_timer.timeout.connect(self._check_no_signal_timeout)
        
        self._no_signal_check_timer.start(30000)  # 30 秒檢查一次
        print(f"[ShutdownMonitor] 電源監控已啟動 (快速斷電: {self.QUICK_POWER_LOSS_TIMEOUT}秒, 無訊號超時: {self.NO_VOLTAGE_SIGNAL_TIMEOUT}秒)")
    
    def stop_no_signal_monitoring(self):
        """停止無電壓訊號監控"""
        if self._no_signal_check_timer:
            self._no_signal_check_timer.stop()
        if self._quick_power_loss_timer:
            self._quick_power_loss_timer.stop()
        print("[ShutdownMonitor] 電源監控已停止")
    
    def _check_quick_power_loss(self):
        """檢查快速斷電（熄火）
        
        當 was_powered=True（曾經有正常電壓）且連續 5 秒沒有收到電壓更新時，
        視為車輛熄火，立即觸發關機流程。
        """
        import time
        
        # 必須曾經有過正常電壓才檢測
        if not self.was_powered:
            return
        
        if self.last_voltage_received_time is None:
            return
        
        # 如果已經觸發過，不重複觸發
        if self._quick_power_loss_triggered or self.power_lost_triggered:
            return
        
        # 如果關機對話框正在顯示，不重複觸發
        if self.shutdown_dialog and self.shutdown_dialog.isVisible():
            return
        
        elapsed = time.time() - self.last_voltage_received_time
        
        if elapsed >= self.QUICK_POWER_LOSS_TIMEOUT:
            self._quick_power_loss_triggered = True
            self.power_lost_triggered = True  # 防止重複觸發
            print(f"🔴 [ShutdownMonitor] 快速斷電偵測！已 {elapsed:.1f} 秒未收到 OBD 電壓數據")
            print(f"   上次電壓: {self.last_voltage:.1f}V，判定為熄火")
            
            # 啟動位置通知 (背景執行)
            print("[ShutdownMonitor] 觸發位置通知...")
            threading.Thread(target=notify_current_location, args=(
                self.current_fuel_level,
                self.current_avg_fuel,
                self.trip_elapsed_time,
                self.trip_distance
            ), daemon=True).start()
            
            self.power_lost.emit()
    
    def _check_no_signal_timeout(self):
        """檢查是否超過無訊號超時時間（針對從未發動的情況）"""
        import time
        
        if self.last_voltage_received_time is None:
            return
        
        # 如果已經觸發過，不重複觸發
        if self.no_signal_triggered:
            return
        
        # 如果已經由快速斷電觸發，不再檢查
        if self._quick_power_loss_triggered or self.power_lost_triggered:
            return
        
        # 如果關機對話框正在顯示，不重複觸發
        if self.shutdown_dialog and self.shutdown_dialog.isVisible():
            return
        
        elapsed = time.time() - self.last_voltage_received_time
        remaining = self.NO_VOLTAGE_SIGNAL_TIMEOUT - elapsed
        
        if elapsed >= self.NO_VOLTAGE_SIGNAL_TIMEOUT:
            self.no_signal_triggered = True
            print(f"⚠️ [ShutdownMonitor] 無電壓訊號超時！已 {elapsed:.0f} 秒未收到 OBD 電壓數據")
            print("   原因: OBD 可能未連接或車輛從未發動")
            self.no_signal_timeout.emit()
        elif remaining <= 60:
            # 最後 60 秒時顯示警告
            print(f"⚠️ [ShutdownMonitor] 無電壓訊號警告: 還剩 {remaining:.0f} 秒將自動關機")
    
    def update_voltage(self, voltage: float):
        """更新電壓值
        
        Args:
            voltage: 當前電壓 (V)
        """
        import time
        
        # === 更新收到訊號的時間（關鍵：任何電壓值都代表有收到訊號）===
        self.last_voltage_received_time = time.time()
        
        # 如果之前因無訊號而觸發，現在收到訊號了，重置狀態
        if self.no_signal_triggered:
            print("🟢 [ShutdownMonitor] 收到電壓訊號，重置無訊號超時狀態")
            self.no_signal_triggered = False
        
        # 如果之前因快速斷電而觸發，現在收到訊號了，重置狀態（車子重新發動）
        if self._quick_power_loss_triggered:
            print("🟢 [ShutdownMonitor] 收到電壓訊號，重置快速斷電狀態")
            self._quick_power_loss_triggered = False
        
        # === 診斷日誌：記錄電壓變化 ===
        # 只在電壓有顯著變化時記錄，避免大量日誌
        voltage_diff = abs(voltage - self.last_voltage)
        if voltage_diff >= 1.0 or (not self.was_powered and voltage > 0):
            print(f"[Voltage] {self.last_voltage:.1f}V → {voltage:.1f}V | was_powered={self.was_powered} | low_count={self.low_voltage_count}")
        
        # 記錄是否曾經有過正常電壓
        if voltage >= self.voltage_threshold:
            if not self.was_powered:
                print(f"🟢 [ShutdownMonitor] 首次偵測到正常電壓: {voltage:.1f}V (閾值: {self.voltage_threshold}V)")
            self.was_powered = True
            self.low_voltage_count = 0
            self.power_lost_triggered = False
            self._quick_power_loss_triggered = False  # 同時重置快速斷電狀態
            
            # 如果電源恢復且對話框正在顯示，關閉它
            if self.shutdown_dialog and self.shutdown_dialog.isVisible():
                print("🟢 電源恢復，取消關機")
                self.shutdown_dialog.close()
                self.power_restored.emit()
        
        # 檢測電壓掉落
        elif self.was_powered and voltage < self.low_voltage_threshold:
            self.low_voltage_count += 1
            print(f"⚠️ [Voltage] 低電壓偵測: {voltage:.1f}V (count: {self.low_voltage_count}/{self.debounce_count})")
            
            # 連續多次低電壓才觸發 (防抖動)
            if self.low_voltage_count >= self.debounce_count and not self.power_lost_triggered:
                self.power_lost_triggered = True
                print(f"🔴 電源中斷偵測: {self.last_voltage:.1f}V → {voltage:.1f}V")
                
                # 啟動位置通知 (背景執行)
                print("[ShutdownMonitor] 觸發位置通知...")
                threading.Thread(target=notify_current_location, args=(
                    self.current_fuel_level,
                    self.current_avg_fuel,
                    self.trip_elapsed_time,
                    self.trip_distance
                ), daemon=True).start()
                
                self.power_lost.emit()
        
        # 記錄電壓未觸發的原因（僅在電壓接近 0 時）
        elif voltage < self.low_voltage_threshold and not self.was_powered:
            # 電壓低但從未有過正常電壓，不觸發
            if voltage_diff >= 1.0:
                print(f"⚠️ [Voltage] 低電壓 {voltage:.1f}V 但 was_powered=False，不觸發關機")
        
        self.last_voltage = voltage
    
    def show_shutdown_dialog(self, parent=None):
        """顯示關機對話框"""
        if self.shutdown_dialog is None:
            self.shutdown_dialog = ShutdownDialog(
                countdown_seconds=30, 
                test_mode=self.test_mode,
                parent=parent
            )
            self.shutdown_dialog.shutdown_cancelled.connect(self._on_shutdown_cancelled)
            self.shutdown_dialog.exit_app.connect(lambda: self.exit_app.emit())
        
        if not self.shutdown_dialog.isVisible():
            self.shutdown_dialog.show()
            
            # 強制前景顯示
            self.shutdown_dialog.raise_()
            self.shutdown_dialog.activateWindow()
            
            # macOS 額外處理：使用 NSApplication 強制激活
            if platform.system() == 'Darwin':
                try:
                    from AppKit import NSApplication, NSApp
                    NSApp.activateIgnoringOtherApps_(True)
                except ImportError:
                    pass  # 沒有 pyobjc，跳過
            
            print("[關機對話框] 已顯示")
    
    def _on_shutdown_cancelled(self):
        """使用者取消關機"""
        import time
        print("🟡 使用者取消關機")
        # 重置狀態，允許再次觸發
        self.power_lost_triggered = False
        self.low_voltage_count = 0
        
        # 也重置無訊號超時狀態，重新計時
        self.no_signal_triggered = False
        self.last_voltage_received_time = time.time()  # 重新計時


# === 全域單例 ===
_shutdown_monitor = None

def get_shutdown_monitor() -> ShutdownMonitor:
    """取得關機監控器單例"""
    global _shutdown_monitor
    if _shutdown_monitor is None:
        _shutdown_monitor = ShutdownMonitor()
    return _shutdown_monitor


if __name__ == "__main__":
    """測試用 - 可以直接執行來測試關機對話框"""
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel
    
    app = QApplication(sys.argv)
    
    # 建立測試視窗
    window = QMainWindow()
    window.setWindowTitle("關機測試 - 電壓歸零測試")
    window.setGeometry(100, 100, 800, 480)
    window.setStyleSheet("background: #1a1a25;")
    
    # 顯示測試資訊
    info_label = QLabel(window)
    info_label.setGeometry(50, 50, 700, 380)
    info_label.setStyleSheet("color: white; font-size: 16px;")
    info_label.setWordWrap(True)
    
    # 建立監控器
    monitor = get_shutdown_monitor()
    
    test_info = f"""
    <h2>🔌 電壓歸零關機測試</h2>
    <hr>
    <p><b>測試模式:</b> {'是 (退出程式)' if monitor.test_mode else '否 (真實關機)'}</p>
    <p><b>是否為 Raspberry Pi:</b> {is_raspberry_pi()}</p>
    <hr>
    <p><b>測試流程:</b></p>
    <ol>
        <li>1 秒後: 模擬正常電壓 12.5V</li>
        <li>3 秒後: 模擬電壓掉落到 0V</li>
        <li>系統將顯示關機倒數對話框</li>
        <li>你可以選擇「取消關機」或等待倒數結束</li>
    </ol>
    <hr>
    <p style="color: #ff8800;">⚠️ 在非 RPi 環境，倒數結束會退出程式而非關機</p>
    """
    info_label.setText(test_info)
    
    monitor.power_lost.connect(lambda: monitor.show_shutdown_dialog(window))
    monitor.exit_app.connect(lambda: print("✅ 收到退出信號"))
    
    # 模擬電壓變化
    def simulate_power_loss():
        print("模擬電壓正常: 12.5V")
        monitor.update_voltage(12.5)
        
        QTimer.singleShot(2000, lambda: (
            print("模擬電壓掉落: 0V"),
            monitor.update_voltage(0),
            monitor.update_voltage(0),
            monitor.update_voltage(0)
        ))
    
    QTimer.singleShot(1000, simulate_power_loss)
    
    window.show()
    sys.exit(app.exec())
