#!/usr/bin/env python3
"""
測試方向燈整合功能
模擬 CAN Bus 發送 BODY_ECU_STATUS 訊息，測試方向燈顯示
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from main import Dashboard

def test_turn_signals():
    """測試方向燈功能"""
    
    # 建立 Qt 應用程式
    app = QApplication(sys.argv)
    dashboard = Dashboard()
    dashboard.show()
    
    # 測試序列
    test_sequence = [
        ("關閉", {"LEFT_SIGNAL_STATUS": 0, "RIGHT_SIGNAL_STATUS": 0}),
        ("左轉", {"LEFT_SIGNAL_STATUS": 1, "RIGHT_SIGNAL_STATUS": 0}),
        ("關閉", {"LEFT_SIGNAL_STATUS": 0, "RIGHT_SIGNAL_STATUS": 0}),
        ("右轉", {"LEFT_SIGNAL_STATUS": 0, "RIGHT_SIGNAL_STATUS": 1}),
        ("關閉", {"LEFT_SIGNAL_STATUS": 0, "RIGHT_SIGNAL_STATUS": 0}),
        ("雙閃", {"LEFT_SIGNAL_STATUS": 1, "RIGHT_SIGNAL_STATUS": 1}),
        ("關閉", {"LEFT_SIGNAL_STATUS": 0, "RIGHT_SIGNAL_STATUS": 0}),
    ]
    
    current_step = [0]  # 使用 list 來在閉包中修改
    
    def update_turn_signal():
        """更新方向燈測試步驟"""
        if current_step[0] >= len(test_sequence):
            print("\n✓ 測試完成！")
            timer.stop()
            return
        
        name, signals = test_sequence[current_step[0]]
        print(f"\n[測試 {current_step[0] + 1}/{len(test_sequence)}] {name}")
        print(f"  LEFT_SIGNAL_STATUS: {signals['LEFT_SIGNAL_STATUS']}")
        print(f"  RIGHT_SIGNAL_STATUS: {signals['RIGHT_SIGNAL_STATUS']}")
        
        # 根據訊號狀態更新儀表板
        left = signals['LEFT_SIGNAL_STATUS']
        right = signals['RIGHT_SIGNAL_STATUS']
        
        if left == 1 and right == 1:
            dashboard.set_turn_signal("both_on")
        elif left == 1:
            dashboard.set_turn_signal("left_on")
        elif right == 1:
            dashboard.set_turn_signal("right_on")
        else:
            dashboard.set_turn_signal("off")
        
        current_step[0] += 1
    
    # 建立定時器
    timer = QTimer()
    timer.timeout.connect(update_turn_signal)
    timer.start(2000)  # 每 2 秒切換一次
    
    # 執行第一步
    update_turn_signal()
    
    print("\n" + "=" * 50)
    print("方向燈測試程式")
    print("=" * 50)
    print("將自動測試以下序列：")
    for i, (name, _) in enumerate(test_sequence, 1):
        print(f"  {i}. {name}")
    print("\n按 Ctrl+C 可隨時停止")
    print("=" * 50 + "\n")
    
    # 進入 Qt 事件循環
    sys.exit(app.exec())

if __name__ == "__main__":
    test_turn_signals()
