#!/usr/bin/env python3
"""
關機檢測模組 - 偵測電壓掉落並自動關機

當電壓從 >10V 掉到 ≈0V 時，顯示倒數計時對話框
如果使用者在 30 秒內按「取消」，則不關機
否則自動執行 sudo poweroff
"""

import os
import subprocess
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont


class ShutdownDialog(QDialog):
    """關機倒數對話框"""
    
    shutdown_confirmed = pyqtSignal()  # 確認關機信號
    shutdown_cancelled = pyqtSignal()  # 取消關機信號
    
    def __init__(self, countdown_seconds=30, parent=None):
        super().__init__(parent)
        
        self.countdown = countdown_seconds
        self.initial_countdown = countdown_seconds
        
        # 設置視窗屬性
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Dialog
        )
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 固定大小
        self.setFixedSize(500, 300)
        
        self._init_ui()
        self._setup_timer()
    
    def _init_ui(self):
        """初始化 UI"""
        # 主容器
        container = QWidget(self)
        container.setGeometry(0, 0, 500, 300)
        container.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a1a1a, stop:1 #1a0a0a);
                border-radius: 20px;
                border: 3px solid #f44;
            }
        """)
        
        layout = QVBoxLayout(container)
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
        self.countdown_label = QLabel(f"{self.countdown} 秒後自動關機")
        self.countdown_label.setStyleSheet("""
            color: #ff8800;
            font-size: 24px;
            font-weight: bold;
            background: transparent;
        """)
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 按鈕區域
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        
        # 取消按鈕
        self.cancel_btn = QPushButton("取消關機")
        self.cancel_btn.setFixedSize(180, 50)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a55;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 18px;
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
        
        # 立即關機按鈕
        self.shutdown_btn = QPushButton("立即關機")
        self.shutdown_btn.setFixedSize(180, 50)
        self.shutdown_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.shutdown_btn.setStyleSheet("""
            QPushButton {
                background-color: #c33;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 18px;
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
        if self.parent():
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
        
        self.countdown_label.setText(f"{self.countdown} 秒後自動關機")
    
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
        """執行關機"""
        print("🔴 執行系統關機...")
        self.shutdown_confirmed.emit()
        self.close()
        
        # 執行關機命令
        try:
            subprocess.run(['sudo', 'poweroff'], check=False)
        except Exception as e:
            print(f"關機失敗: {e}")


class ShutdownMonitor(QObject):
    """關機監控器 - 監測電壓變化"""
    
    # 信號
    power_lost = pyqtSignal()      # 電源中斷
    power_restored = pyqtSignal()  # 電源恢復
    
    def __init__(self, 
                 voltage_threshold=10.0,      # 正常電壓閾值
                 low_voltage_threshold=1.0,   # 低電壓閾值 (視為斷電)
                 debounce_count=3,            # 需要連續幾次低電壓才觸發
                 parent=None):
        super().__init__(parent)
        
        self.voltage_threshold = voltage_threshold
        self.low_voltage_threshold = low_voltage_threshold
        self.debounce_count = debounce_count
        
        # 狀態
        self.last_voltage = 0.0
        self.was_powered = False  # 是否曾經有過正常電壓
        self.low_voltage_count = 0
        self.power_lost_triggered = False
        
        # 關機對話框
        self.shutdown_dialog = None
    
    def update_voltage(self, voltage: float):
        """更新電壓值
        
        Args:
            voltage: 當前電壓 (V)
        """
        # 記錄是否曾經有過正常電壓
        if voltage >= self.voltage_threshold:
            self.was_powered = True
            self.low_voltage_count = 0
            self.power_lost_triggered = False
            
            # 如果電源恢復且對話框正在顯示，關閉它
            if self.shutdown_dialog and self.shutdown_dialog.isVisible():
                print("🟢 電源恢復，取消關機")
                self.shutdown_dialog.close()
                self.power_restored.emit()
        
        # 檢測電壓掉落
        elif self.was_powered and voltage < self.low_voltage_threshold:
            self.low_voltage_count += 1
            
            # 連續多次低電壓才觸發 (防抖動)
            if self.low_voltage_count >= self.debounce_count and not self.power_lost_triggered:
                self.power_lost_triggered = True
                print(f"🔴 電源中斷偵測: {self.last_voltage:.1f}V → {voltage:.1f}V")
                self.power_lost.emit()
        
        self.last_voltage = voltage
    
    def show_shutdown_dialog(self, parent=None):
        """顯示關機對話框"""
        if self.shutdown_dialog is None:
            self.shutdown_dialog = ShutdownDialog(countdown_seconds=30, parent=parent)
            self.shutdown_dialog.shutdown_cancelled.connect(self._on_shutdown_cancelled)
        
        if not self.shutdown_dialog.isVisible():
            self.shutdown_dialog.show()
    
    def _on_shutdown_cancelled(self):
        """使用者取消關機"""
        print("🟡 使用者取消關機")
        # 重置狀態，允許再次觸發
        self.power_lost_triggered = False
        self.low_voltage_count = 0


# === 全域單例 ===
_shutdown_monitor = None

def get_shutdown_monitor() -> ShutdownMonitor:
    """取得關機監控器單例"""
    global _shutdown_monitor
    if _shutdown_monitor is None:
        _shutdown_monitor = ShutdownMonitor()
    return _shutdown_monitor


if __name__ == "__main__":
    """測試用"""
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow
    
    app = QApplication(sys.argv)
    
    # 建立測試視窗
    window = QMainWindow()
    window.setWindowTitle("關機測試")
    window.setGeometry(100, 100, 800, 480)
    window.setStyleSheet("background: #1a1a25;")
    
    # 建立監控器
    monitor = get_shutdown_monitor()
    monitor.power_lost.connect(lambda: monitor.show_shutdown_dialog(window))
    
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
