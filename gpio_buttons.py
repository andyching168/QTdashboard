"""
GPIO 按鈕處理模組 - 樹莓派實體按鈕控制

按鈕配置：
- GPIO19: 按鈕 A (左側卡片控制)
  - 短按: 切換左側卡片/焦點
  - 長按: 進入/退出詳細視圖
  
- GPIO26: 按鈕 B (右側卡片控制)
  - 短按: 切換右側卡片/焦點
  - 長按: 重置 Trip

接線：
- 按鈕一端接 GPIO 腳位
- 按鈕另一端接 GND
- 使用內部上拉電阻 (按下為 LOW)
"""

import sys
import time
from typing import Optional, Callable

# 嘗試導入 gpiozero (樹莓派 GPIO 庫)
try:
    from gpiozero import Button
    from gpiozero.exc import BadPinFactory
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("[GPIO] gpiozero 未安裝，GPIO 按鈕功能不可用")

from PyQt6.QtCore import QObject, pyqtSignal


class GPIOButtonHandler(QObject):
    """
    GPIO 按鈕處理器
    
    處理按鈕的短按和長按事件，並通過 Qt 信號發送到主程式。
    使用 gpiozero 庫，支援軟體防抖動。
    """
    
    # Qt 信號 - 用於跨線程通信
    button_a_pressed = pyqtSignal()      # 按鈕 A 短按
    button_a_long_pressed = pyqtSignal() # 按鈕 A 長按
    button_b_pressed = pyqtSignal()      # 按鈕 B 短按
    button_b_long_pressed = pyqtSignal() # 按鈕 B 長按
    
    # 配置參數
    BUTTON_A_PIN = 19  # GPIO19
    BUTTON_B_PIN = 26  # GPIO26
    LONG_PRESS_TIME = 0.8  # 長按閾值（秒）
    DEBOUNCE_TIME = 0.05   # 防抖動時間（秒）
    
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        
        self._button_a: Optional['Button'] = None
        self._button_b: Optional['Button'] = None
        
        # 初始化 GPIO
        self._initialized = False
        self._init_gpio()
    
    def _init_gpio(self) -> bool:
        """初始化 GPIO 按鈕"""
        if not GPIO_AVAILABLE:
            print("[GPIO] gpiozero 不可用，跳過 GPIO 初始化")
            return False
        
        try:
            # 按鈕 A - GPIO19
            # pull_up=True: 使用內部上拉電阻，按下時為 LOW
            # bounce_time: 軟體防抖動
            # hold_time: 長按閾值
            self._button_a = Button(
                self.BUTTON_A_PIN,
                pull_up=True,
                bounce_time=self.DEBOUNCE_TIME,
                hold_time=self.LONG_PRESS_TIME
            )
            self._button_a.when_held = self._on_button_a_held
            self._button_a.when_released = self._on_button_a_released
            
            # 按鈕 B - GPIO26
            self._button_b = Button(
                self.BUTTON_B_PIN,
                pull_up=True,
                bounce_time=self.DEBOUNCE_TIME,
                hold_time=self.LONG_PRESS_TIME
            )
            self._button_b.when_held = self._on_button_b_held
            self._button_b.when_released = self._on_button_b_released
            
            self._initialized = True
            print(f"[GPIO] 按鈕初始化成功")
            print(f"  - 按鈕 A: GPIO{self.BUTTON_A_PIN} (短按=切換左卡片, 長按=詳細視圖)")
            print(f"  - 按鈕 B: GPIO{self.BUTTON_B_PIN} (短按=切換右卡片, 長按=重置Trip)")
            print(f"  - 長按時間: {self.LONG_PRESS_TIME}秒")
            return True
            
        except BadPinFactory as e:
            print(f"[GPIO] 無法初始化 GPIO (可能不在樹莓派上): {e}")
            return False
        except Exception as e:
            print(f"[GPIO] GPIO 初始化失敗: {e}")
            return False
    
    @property
    def is_available(self) -> bool:
        """檢查 GPIO 是否可用"""
        return self._initialized
    
    # === 按鈕 A 事件處理 ===
    def _on_button_a_held(self):
        """按鈕 A 長按"""
        print("[GPIO] 按鈕 A 長按")
        self.button_a_long_pressed.emit()
    
    def _on_button_a_released(self):
        """按鈕 A 被釋放 - 用 is_held 判斷是短按還是長按"""
        if not self._button_a.is_held:
            print("[GPIO] 按鈕 A 短按")
            self.button_a_pressed.emit()
    
    # === 按鈕 B 事件處理 ===
    def _on_button_b_held(self):
        """按鈕 B 長按"""
        print("[GPIO] 按鈕 B 長按")
        self.button_b_long_pressed.emit()
    
    def _on_button_b_released(self):
        """按鈕 B 被釋放 - 用 is_held 判斷是短按還是長按"""
        if not self._button_b.is_held:
            print("[GPIO] 按鈕 B 短按")
            self.button_b_pressed.emit()
    
    def cleanup(self):
        """清理 GPIO 資源"""
        if self._button_a:
            self._button_a.close()
            self._button_a = None
        if self._button_b:
            self._button_b.close()
            self._button_b = None
        self._initialized = False
        print("[GPIO] GPIO 資源已釋放")
    
    def __del__(self):
        """析構函數"""
        self.cleanup()


# === 單例模式 ===
_gpio_handler: Optional[GPIOButtonHandler] = None


def get_gpio_handler(parent: Optional[QObject] = None) -> GPIOButtonHandler:
    """
    獲取 GPIO 按鈕處理器單例
    
    Args:
        parent: Qt 父物件（僅在首次創建時使用）
    
    Returns:
        GPIOButtonHandler 實例
    """
    global _gpio_handler
    if _gpio_handler is None:
        _gpio_handler = GPIOButtonHandler(parent)
    return _gpio_handler


def setup_gpio_buttons(dashboard_window) -> Optional[GPIOButtonHandler]:
    """
    設置 GPIO 按鈕並連接到儀表板視窗
    
    Args:
        dashboard_window: 儀表板主視窗，需要有以下方法：
            - on_button_a_pressed()
            - on_button_a_long_pressed()
            - on_button_b_pressed()
            - on_button_b_long_pressed()
    
    Returns:
        GPIOButtonHandler 實例，如果初始化失敗則返回 None
    """
    handler = get_gpio_handler()
    
    if not handler.is_available:
        print("[GPIO] GPIO 不可用，按鈕功能將使用鍵盤模擬 (F1/F2)")
        return None
    
    # 連接信號到儀表板方法
    handler.button_a_pressed.connect(dashboard_window.on_button_a_pressed)
    handler.button_a_long_pressed.connect(dashboard_window.on_button_a_long_pressed)
    handler.button_b_pressed.connect(dashboard_window.on_button_b_pressed)
    handler.button_b_long_pressed.connect(dashboard_window.on_button_b_long_pressed)
    
    print("[GPIO] GPIO 按鈕已連接到儀表板")
    return handler


# === 測試程式 ===
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
    from PyQt6.QtCore import Qt
    
    app = QApplication(sys.argv)
    
    # 創建測試視窗
    window = QWidget()
    window.setWindowTitle("GPIO 按鈕測試")
    window.setFixedSize(400, 300)
    
    layout = QVBoxLayout(window)
    
    status_label = QLabel("等待按鈕事件...")
    status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    status_label.setStyleSheet("font-size: 18px; padding: 20px;")
    layout.addWidget(status_label)
    
    info_label = QLabel(
        f"按鈕 A: GPIO{GPIOButtonHandler.BUTTON_A_PIN}\n"
        f"按鈕 B: GPIO{GPIOButtonHandler.BUTTON_B_PIN}\n"
        f"長按時間: {GPIOButtonHandler.LONG_PRESS_TIME}秒"
    )
    info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    info_label.setStyleSheet("color: #888;")
    layout.addWidget(info_label)
    
    # 獲取 GPIO 處理器
    gpio = get_gpio_handler()
    
    # 連接信號
    def on_a_pressed():
        status_label.setText("按鈕 A 短按")
        status_label.setStyleSheet("font-size: 18px; padding: 20px; color: #4a4;")
    
    def on_a_long():
        status_label.setText("按鈕 A 長按")
        status_label.setStyleSheet("font-size: 18px; padding: 20px; color: #4a4; font-weight: bold;")
    
    def on_b_pressed():
        status_label.setText("按鈕 B 短按")
        status_label.setStyleSheet("font-size: 18px; padding: 20px; color: #44a;")
    
    def on_b_long():
        status_label.setText("按鈕 B 長按")
        status_label.setStyleSheet("font-size: 18px; padding: 20px; color: #44a; font-weight: bold;")
    
    gpio.button_a_pressed.connect(on_a_pressed)
    gpio.button_a_long_pressed.connect(on_a_long)
    gpio.button_b_pressed.connect(on_b_pressed)
    gpio.button_b_long_pressed.connect(on_b_long)
    
    if gpio.is_available:
        info_label.setText(info_label.text() + "\n\nGPIO 已初始化 ✓")
    else:
        info_label.setText(info_label.text() + "\n\nGPIO 不可用 ✗\n(可能不在樹莓派上)")
    
    window.show()
    
    try:
        sys.exit(app.exec())
    finally:
        gpio.cleanup()
