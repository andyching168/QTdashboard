#!/usr/bin/env python3
"""
Trip Card 測試腳本
測試里程計算功能
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from main import Dashboard

def main():
    """測試 Trip Card"""
    app = QApplication(sys.argv)
    dashboard = Dashboard()
    dashboard.show()
    
    # 模擬車速變化
    test_speeds = [0, 20, 40, 60, 80, 100, 80, 60, 40, 20, 0]
    current_index = [0]
    
    def update_speed():
        """更新測試速度"""
        if current_index[0] < len(test_speeds):
            speed = test_speeds[current_index[0]]
            print(f"設定速度: {speed} km/h")
            dashboard.set_speed(speed)
            
            # 顯示當前 Trip 數據
            trip1_dist = dashboard.trip_card.trip1_distance
            trip2_dist = dashboard.trip_card.trip2_distance
            print(f"  Trip 1: {trip1_dist:.3f} km")
            print(f"  Trip 2: {trip2_dist:.3f} km")
            
            current_index[0] += 1
        else:
            print("\n測試完成！")
            print(f"最終 Trip 1: {dashboard.trip_card.trip1_distance:.3f} km")
            print(f"最終 Trip 2: {dashboard.trip_card.trip2_distance:.3f} km")
            timer.stop()
    
    # 每秒更新一次速度
    timer = QTimer()
    timer.timeout.connect(update_speed)
    timer.start(1000)
    
    print("=" * 60)
    print("Trip Card 測試")
    print("=" * 60)
    print("模擬速度變化，觀察里程累積")
    print("提示：可以點擊 Reset 按鈕測試重置功能")
    print("=" * 60)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
