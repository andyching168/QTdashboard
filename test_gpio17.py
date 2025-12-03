#!/usr/bin/env python3
"""
GPIO17 測試程式 - 測試 ESP32 傳來的手煞車信號
"""

import time

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("錯誤: RPi.GPIO 不可用")
    print("請安裝: sudo apt install python3-rpi.gpio")
    exit(1)

GPIO_PIN = 17

def main():
    print("=" * 40)
    print("GPIO17 測試程式")
    print("=" * 40)
    print(f"腳位: GPIO{GPIO_PIN} (Pin 11)")
    print("按 Ctrl+C 結束")
    print("-" * 40)
    
    # 設定 GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(GPIO_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    
    last_state = None
    
    try:
        while True:
            state = GPIO.input(GPIO_PIN)
            
            if state != last_state:
                if state == GPIO.HIGH:
                    print(f"[{time.strftime('%H:%M:%S')}] GPIO17 = HIGH (1) 🔴 手煞車拉起")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] GPIO17 = LOW  (0) ⚪ 手煞車放下")
                last_state = state
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n結束測試")
    finally:
        GPIO.cleanup(GPIO_PIN)
        print("GPIO 已清理")

if __name__ == "__main__":
    main()
