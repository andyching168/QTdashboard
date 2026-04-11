#!/usr/bin/env python3
"""
手煞車監控器 - 讀取 ESP32 透過 GPIO 傳來的數位信號

接線方式:
1. 光敏電阻模組 -> ESP32:
   - VCC -> 3.3V
   - GND -> GND
   - AO  -> GPIO34 (ADC)

2. ESP32 -> Raspberry Pi:
    - GPIO25 (輸出) -> GPIO27 (Pin 13)
   - GND -> GND (Pin 6)

ESP32 負責讀取類比值並輸出 HIGH/LOW 給 RPi
"""

import time
import threading

# GPIO 設定
PARKING_BRAKE_GPIO = 27  # 使用 GPIO27，可自行更改

# 偵測設定
ACTIVE_LOW = False  # False = ESP32 輸出 HIGH 時表示手煞車拉起
                    # True = ESP32 輸出 LOW 時表示手煞車拉起

DEBOUNCE_TIME = 0.1  # 防抖時間（秒）


class ParkingBrakeMonitor:
    """手煞車監控器"""
    
    def __init__(self, gpio_pin=PARKING_BRAKE_GPIO, active_low=ACTIVE_LOW):
        self.gpio_pin = gpio_pin
        self.active_low = active_low
        self.is_engaged = False
        self._running = False
        self._thread = None
        self._callback = None
        self._gpio_available = False
        
        # 嘗試初始化 GPIO
        self._init_gpio()
    
    def _init_gpio(self):
        """初始化 GPIO"""
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            GPIO.setwarnings(False)  # 避免重複設定警告
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.gpio_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            self._gpio_available = True
            print(f"[ParkingBrake] GPIO{self.gpio_pin} 初始化成功")
        except ImportError:
            print("[ParkingBrake] 警告: RPi.GPIO 不可用，使用模擬模式")
            self._gpio_available = False
        except Exception as e:
            print(f"[ParkingBrake] GPIO 初始化失敗: {e}")
            self._gpio_available = False
    
    def _read_state(self) -> bool:
        """讀取手煞車狀態"""
        if not self._gpio_available:
            return False
        
        raw_value = self.GPIO.input(self.gpio_pin)
        
        # 根據 active_low 設定判斷
        if self.active_low:
            # LOW = 燈亮 = 手煞車拉起
            return raw_value == self.GPIO.LOW
        else:
            # HIGH = 燈亮 = 手煞車拉起
            return raw_value == self.GPIO.HIGH
    
    def set_callback(self, callback):
        """設定狀態變化回調函數
        
        callback(is_engaged: bool) - 當狀態變化時呼叫
        """
        self._callback = callback
    
    def start(self):
        """開始監控"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print("[ParkingBrake] 監控已啟動")
    
    def stop(self):
        """停止監控"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        print("[ParkingBrake] 監控已停止")
    
    def _monitor_loop(self):
        """監控迴圈"""
        last_state = self._read_state()
        self.is_engaged = last_state
        
        # 初始通知
        if self._callback:
            self._callback(last_state)
        
        while self._running:
            current_state = self._read_state()
            
            if current_state != last_state:
                # 簡單防抖：等待一小段時間再確認
                time.sleep(DEBOUNCE_TIME)
                current_state = self._read_state()
                
                if current_state != last_state:
                    last_state = current_state
                    self.is_engaged = current_state
                    print(f"[ParkingBrake] 狀態變化: {'拉起' if current_state else '放下'}")
                    
                    if self._callback:
                        self._callback(current_state)
            
            time.sleep(0.05)  # 50ms 輪詢間隔
    
    def cleanup(self):
        """清理 GPIO 資源"""
        self.stop()
        if self._gpio_available:
            try:
                self.GPIO.cleanup(self.gpio_pin)
            except:
                pass


# 全域實例
_monitor = None


def get_monitor() -> ParkingBrakeMonitor:
    """取得全域監控器實例"""
    global _monitor
    if _monitor is None:
        _monitor = ParkingBrakeMonitor()
    return _monitor


def start_monitoring(dashboard=None, gpio_pin=PARKING_BRAKE_GPIO):
    """啟動手煞車監控
    
    Args:
        dashboard: Dashboard 實例，用於更新 UI
        gpio_pin: GPIO 腳位編號
    """
    global _monitor
    
    # 如果已有實例且腳位不同，先清理
    if _monitor is not None:
        _monitor.cleanup()
        _monitor = None
    
    # 建立新實例
    _monitor = ParkingBrakeMonitor(gpio_pin=gpio_pin)
    
    if dashboard:
        def on_state_change(is_engaged):
            # 使用 signal 安全地更新 UI
            print(f"[ParkingBrake] 發送信號到儀表板: {is_engaged}")
            dashboard.signal_update_parking_brake.emit(is_engaged)
        
        _monitor.set_callback(on_state_change)
    
    _monitor.start()
    return _monitor


def stop_monitoring():
    """停止監控"""
    global _monitor
    if _monitor:
        _monitor.cleanup()
        _monitor = None


# 測試用
if __name__ == "__main__":
    print("手煞車監控測試")
    print(f"GPIO 腳位: {PARKING_BRAKE_GPIO}")
    print(f"模式: {'LOW = 燈亮' if ACTIVE_LOW else 'HIGH = 燈亮'}")
    print("-" * 40)
    
    def test_callback(is_engaged):
        status = "🔴 手煞車拉起" if is_engaged else "⚪ 手煞車放下"
        print(f"[{time.strftime('%H:%M:%S')}] {status}")
    
    monitor = ParkingBrakeMonitor()
    monitor.set_callback(test_callback)
    monitor.start()
    
    try:
        print("按 Ctrl+C 結束測試...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n結束測試")
    finally:
        monitor.cleanup()
