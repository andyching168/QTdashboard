#!/usr/bin/env python3
"""
模擬 CAN bus 方向燈訊號
使用 85 BPM 的閃爍頻率（符合原廠規格）
"""

import sys
import time
import threading
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# 確保可以導入 main.py
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import Dashboard


class CANBusSimulator:
    """模擬 CAN bus 方向燈訊號"""
    
    def __init__(self, dashboard):
        self.dashboard = dashboard
        self.running = False
        self.thread = None
        
        # 85 BPM = 85 beats per minute = 85/60 Hz ≈ 1.417 Hz
        # 週期 = 1/1.417 ≈ 0.706 秒
        # 亮和滅各佔一半，所以每個狀態持續 0.353 秒
        self.blink_interval = 60.0 / 85.0 / 2.0  # ≈ 0.353 秒
        
        self.left_turn_active = False
        self.right_turn_active = False
        self.hazard_active = False  # 雙閃
        
    def start(self):
        """啟動 CAN bus 模擬"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._simulate_can_signals, daemon=True)
        self.thread.start()
        print(f"✓ CAN bus 模擬器已啟動 (85 BPM, 週期 {self.blink_interval*2:.3f}s)")
    
    def stop(self):
        """停止 CAN bus 模擬"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        print("✓ CAN bus 模擬器已停止")
    
    def set_left_turn(self, active):
        """設定左轉燈"""
        self.left_turn_active = active
        self.hazard_active = False
        if not active:
            self.dashboard.set_turn_signal("left_off")
    
    def set_right_turn(self, active):
        """設定右轉燈"""
        self.right_turn_active = active
        self.hazard_active = False
        if not active:
            self.dashboard.set_turn_signal("right_off")
    
    def set_hazard(self, active):
        """設定雙閃"""
        self.hazard_active = active
        if active:
            self.left_turn_active = False
            self.right_turn_active = False
        else:
            self.dashboard.set_turn_signal("both_off")
    
    def _simulate_can_signals(self):
        """在背景執行緒中模擬 CAN 訊號"""
        while self.running:
            try:
                # 雙閃優先
                if self.hazard_active:
                    self.dashboard.set_turn_signal("both_on")
                    time.sleep(self.blink_interval)
                    if not self.running:
                        break
                    self.dashboard.set_turn_signal("both_off")
                    time.sleep(self.blink_interval)
                
                # 左轉燈
                elif self.left_turn_active:
                    self.dashboard.set_turn_signal("left_on")
                    time.sleep(self.blink_interval)
                    if not self.running:
                        break
                    self.dashboard.set_turn_signal("left_off")
                    time.sleep(self.blink_interval)
                
                # 右轉燈
                elif self.right_turn_active:
                    self.dashboard.set_turn_signal("right_on")
                    time.sleep(self.blink_interval)
                    if not self.running:
                        break
                    self.dashboard.set_turn_signal("right_off")
                    time.sleep(self.blink_interval)
                
                else:
                    # 無訊號時短暫休眠
                    time.sleep(0.1)
                    
            except Exception as e:
                print(f"CAN bus 模擬錯誤: {e}")
                time.sleep(0.1)


def main():
    """測試方向燈與 CAN bus 模擬"""
    print("=" * 60)
    print("CAN Bus 方向燈模擬測試")
    print("=" * 60)
    print()
    print("規格:")
    print("  - 閃爍頻率: 85 BPM (符合原廠維修手冊)")
    print("  - 週期: 約 0.706 秒")
    print("  - 亮/滅時間: 各 0.353 秒")
    print()
    print("測試流程:")
    print("  1. 啟動儀表板")
    print("  2. 啟動 CAN bus 模擬器")
    print("  3. 自動測試各種方向燈狀態")
    print()
    print("鍵盤控制:")
    print("  Z: 左轉燈")
    print("  X: 右轉燈")
    print("  C: 雙閃")
    print("  (再按一次關閉)")
    print()
    print("=" * 60)
    print()
    
    app = QApplication(sys.argv)
    dashboard = Dashboard()
    dashboard.show()
    
    # 建立 CAN bus 模擬器
    can_sim = CANBusSimulator(dashboard)
    can_sim.start()
    
    # 自動測試序列
    def auto_test():
        """自動測試各種方向燈狀態"""
        
        def test_left():
            print("→ 測試: 左轉燈啟動")
            can_sim.set_left_turn(True)
        
        def test_left_off():
            print("→ 測試: 左轉燈關閉")
            can_sim.set_left_turn(False)
        
        def test_right():
            print("→ 測試: 右轉燈啟動")
            can_sim.set_right_turn(True)
        
        def test_right_off():
            print("→ 測試: 右轉燈關閉")
            can_sim.set_right_turn(False)
        
        def test_hazard():
            print("→ 測試: 雙閃啟動")
            can_sim.set_hazard(True)
        
        def test_hazard_off():
            print("→ 測試: 雙閃關閉")
            can_sim.set_hazard(False)
        
        def test_complete():
            print()
            print("=" * 60)
            print("✅ 自動測試完成！")
            print()
            print("你可以使用鍵盤繼續測試:")
            print("  Z: 切換左轉燈")
            print("  X: 切換右轉燈")
            print("  C: 切換雙閃")
            print("=" * 60)
        
        # 測試序列（每個狀態持續 3 秒）
        tests = [
            (2000, test_left),
            (5000, test_left_off),
            (6000, test_right),
            (9000, test_right_off),
            (10000, test_hazard),
            (13000, test_hazard_off),
            (14000, test_complete),
        ]
        
        for delay, action in tests:
            QTimer.singleShot(delay, action)
    
    # 啟動自動測試
    QTimer.singleShot(1000, auto_test)
    
    # 確保程式退出時停止模擬器
    import atexit
    atexit.register(can_sim.stop)
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
