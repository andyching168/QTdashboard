#!/usr/bin/env python3
"""
演示模式 - 不需要 CAN Bus 硬體
直接運行前端並使用模擬數據更新
"""

import sys
import time
import random
import math
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from main import Dashboard


class VehicleSimulator:
    """車輛狀態模擬器"""
    
    def __init__(self):
        self.speed = 0.0
        self.rpm = 0.8  # 千轉
        self.fuel = 65.0
        self.temp = 45.0  # 儀表百分比
        self.gear = "P"
        
        self.mode = "idle"
        self.time = 0
        self.target_speed = 0
    
    def update(self, dt=0.1):
        """更新車輛狀態"""
        self.time += dt
        
        # 模式切換
        if self.mode == "idle":
            if self.time > 5:
                self.mode = "accelerating"
                self.target_speed = random.uniform(40, 100)
                self.gear = "D"
                self.time = 0
                
        elif self.mode == "accelerating":
            if self.speed >= self.target_speed * 0.95:
                self.mode = "cruising"
                self.time = 0
                
        elif self.mode == "cruising":
            if self.time > random.uniform(8, 15):
                self.mode = "decelerating"
                self.time = 0
                
        elif self.mode == "decelerating":
            if self.speed < 5:
                self.mode = "idle"
                self.gear = "P"
                self.time = 0
        
        # 更新速度
        if self.mode == "idle":
            self.speed = max(0, self.speed - 2 * dt)
            self.rpm = 0.8  # 怠速
            
        elif self.mode == "accelerating":
            self.speed = min(self.target_speed, self.speed + 3 * dt)
            self.rpm = 0.8 + (self.speed / 100.0) * 4.5
            
        elif self.mode == "cruising":
            self.speed += random.uniform(-0.5, 0.5) * dt
            self.rpm = 1.5 + (self.speed / 100.0) * 2.5
            
        elif self.mode == "decelerating":
            self.speed = max(0, self.speed - 4 * dt)
            if self.speed < 5:
                self.rpm = 0.8
            else:
                self.rpm = max(0.8, 1.0 + (self.speed / 100.0) * 3.0)
        
        # 限制範圍
        self.speed = max(0, min(180, self.speed))
        self.rpm = max(0, min(7, self.rpm))
        
        # 更新油量（緩慢減少）
        if self.speed > 0:
            self.fuel = max(5, self.fuel - 0.005 * dt)
        
        # 更新水溫
        if self.rpm > 1.5:
            target_temp = 50  # 正常工作溫度
        else:
            target_temp = 45
        
        if self.temp < target_temp:
            self.temp += 0.5 * dt
        elif self.temp > target_temp:
            self.temp -= 0.3 * dt
        
        # 添加小波動
        self.temp += random.uniform(-0.1, 0.1)
        self.temp = max(20, min(95, self.temp))
        
        # 檔位邏輯
        if self.speed > 5 and self.gear == "P":
            self.gear = "D"
        elif self.speed < 1 and self.mode == "idle":
            self.gear = "P"


def main():
    """主程式"""
    print("=" * 50)
    print("演示模式 - Luxgen M7 數位儀表板")
    print("無需 CAN Bus 硬體")
    print("=" * 50)
    print()
    print("功能:")
    print("  - 自動模擬車輛行駛狀態")
    print("  - 怠速 → 加速 → 巡航 → 減速 循環")
    print()
    print("鍵盤控制:")
    print("  W/S: 加速/減速")
    print("  Q/E: 降低/升高水溫")
    print("  A/D: 減少/增加油量")
    print("  1-6: 切換檔位 (P/R/N/D/S/L)")
    print()
    print("按 Ctrl+C 或關閉視窗退出")
    print("=" * 50)
    
    app = QApplication(sys.argv)
    dashboard = Dashboard()
    dashboard.setWindowTitle("Luxgen M7 儀表板 - 演示模式")
    dashboard.show()
    
    # 建立模擬器
    simulator = VehicleSimulator()
    
    # 建立定時器更新數據
    def update_data():
        simulator.update(0.1)
        dashboard.set_speed(simulator.speed)
        dashboard.set_rpm(simulator.rpm)
        dashboard.set_fuel(simulator.fuel)
        dashboard.set_temperature(simulator.temp)
        dashboard.set_gear(simulator.gear)
    
    timer = QTimer()
    timer.timeout.connect(update_data)
    timer.start(100)  # 每 100ms 更新一次 (10 Hz)
    
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\n程式結束")
        timer.stop()


if __name__ == '__main__':
    main()
