#!/usr/bin/env python3
"""
GPIO 按鈕測試腳本

這個腳本用於在樹莓派上測試 GPIO 按鈕是否正常工作。
不需要啟動完整的儀表板程式。

使用方法:
    python3 test_gpio_buttons.py

按鈕配置:
    GPIO19 - 按鈕 A (短按/長按)
    GPIO26 - 按鈕 B (短按/長按)
    GND    - 共地

退出: Ctrl+C
"""

import sys
import time

def test_with_gpiozero():
    """使用 gpiozero 測試按鈕"""
    try:
        from gpiozero import Button
        from signal import pause
        
        print("=" * 50)
        print("GPIO 按鈕測試 (使用 gpiozero)")
        print("=" * 50)
        print()
        print("按鈕配置:")
        print("  GPIO19 - 按鈕 A")
        print("  GPIO26 - 按鈕 B")
        print("  GND    - 共地")
        print()
        print("長按時間: 0.8 秒")
        print()
        print("按 Ctrl+C 退出")
        print("-" * 50)
        
        # 設定按鈕（使用內部上拉電阻）
        button_a = Button(19, pull_up=True, bounce_time=0.05, hold_time=0.8)
        button_b = Button(26, pull_up=True, bounce_time=0.05, hold_time=0.8)
        
        # 事件計數器
        event_count = [0]
        
        def on_a_pressed():
            event_count[0] += 1
            print(f"[{event_count[0]:03d}] 按鈕 A: 按下")
        
        def on_a_released():
            event_count[0] += 1
            if not button_a.is_held:
                print(f"[{event_count[0]:03d}] 按鈕 A: 短按釋放")
            else:
                print(f"[{event_count[0]:03d}] 按鈕 A: 長按釋放")
        
        def on_a_held():
            event_count[0] += 1
            print(f"[{event_count[0]:03d}] 按鈕 A: ★ 長按觸發 ★")
        
        def on_b_pressed():
            event_count[0] += 1
            print(f"[{event_count[0]:03d}] 按鈕 B: 按下")
        
        def on_b_released():
            event_count[0] += 1
            if not button_b.is_held:
                print(f"[{event_count[0]:03d}] 按鈕 B: 短按釋放")
            else:
                print(f"[{event_count[0]:03d}] 按鈕 B: 長按釋放")
        
        def on_b_held():
            event_count[0] += 1
            print(f"[{event_count[0]:03d}] 按鈕 B: ★ 長按觸發 ★")
        
        # 綁定事件
        button_a.when_pressed = on_a_pressed
        button_a.when_released = on_a_released
        button_a.when_held = on_a_held
        
        button_b.when_pressed = on_b_pressed
        button_b.when_released = on_b_released
        button_b.when_held = on_b_held
        
        print("等待按鈕事件...")
        print()
        
        # 等待事件
        pause()
        
    except ImportError:
        print("錯誤: gpiozero 未安裝")
        print("請執行: pip3 install gpiozero")
        sys.exit(1)
    except Exception as e:
        print(f"錯誤: {e}")
        print()
        print("可能原因:")
        print("  1. 不在樹莓派上執行")
        print("  2. GPIO 權限不足 (試試 sudo)")
        print("  3. GPIO 腳位被其他程式佔用")
        sys.exit(1)


def test_raw_gpio():
    """使用 RPi.GPIO 直接測試（備用方案）"""
    try:
        import RPi.GPIO as GPIO
        
        print("=" * 50)
        print("GPIO 按鈕測試 (使用 RPi.GPIO)")
        print("=" * 50)
        print()
        print("按鈕配置:")
        print("  GPIO19 - 按鈕 A")
        print("  GPIO26 - 按鈕 B")
        print()
        print("按 Ctrl+C 退出")
        print("-" * 50)
        
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(19, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(26, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        last_a = GPIO.HIGH
        last_b = GPIO.HIGH
        
        print("持續讀取 GPIO 狀態...")
        print()
        
        while True:
            a = GPIO.input(19)
            b = GPIO.input(26)
            
            if a != last_a:
                status = "按下 ▼" if a == GPIO.LOW else "釋放 ▲"
                print(f"按鈕 A (GPIO19): {status}")
                last_a = a
            
            if b != last_b:
                status = "按下 ▼" if b == GPIO.LOW else "釋放 ▲"
                print(f"按鈕 B (GPIO26): {status}")
                last_b = b
            
            time.sleep(0.01)
            
    except ImportError:
        print("錯誤: RPi.GPIO 未安裝")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n退出")
    finally:
        try:
            GPIO.cleanup()
        except:
            pass


def main():
    print()
    print("╔════════════════════════════════════════════════╗")
    print("║         GPIO 按鈕測試工具                       ║")
    print("╚════════════════════════════════════════════════╝")
    print()
    
    # 檢查是否在樹莓派上
    is_rpi = False
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            is_rpi = 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo
    except:
        pass
    
    if not is_rpi:
        print("⚠️  警告: 似乎不在樹莓派上執行")
        print("    此測試腳本需要在樹莓派上使用實體按鈕")
        print()
    
    # 選擇測試模式
    if len(sys.argv) > 1 and sys.argv[1] == '--raw':
        test_raw_gpio()
    else:
        test_with_gpiozero()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n退出測試")
        sys.exit(0)
