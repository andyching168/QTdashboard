#!/usr/bin/env python3
"""
ODO Card 測試腳本
測試總里程表和內嵌虛擬鍵盤功能
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from main import Dashboard

def main():
    """測試 ODO Card"""
    app = QApplication(sys.argv)
    dashboard = Dashboard()
    dashboard.show()
    
    # 切換到第二列的 ODO 卡片
    dashboard.current_row_index = 1
    dashboard.current_card_index = 1  # ODO 卡片位於 row2_index 1
    dashboard.row_stack.setCurrentIndex(1)
    dashboard.rows[1].setCurrentIndex(1)
    dashboard.update_indicators()
    
    print("=" * 60)
    print("ODO Card 測試 - 內嵌虛擬鍵盤版本")
    print("=" * 60)
    print("已切換到 ODO 卡片（第二列第二張）")
    print()
    print("測試項目：")
    print("1. 點擊「同步里程」按鈕 - 顯示內嵌鍵盤")
    print("2. 使用虛擬鍵盤輸入里程數")
    print("3. 輸入時滑動功能會自動禁用")
    print("4. 確定或取消後恢復滑動功能")
    print("5. 觀察里程隨著速度自動累積")
    print("=" * 60)
    
    # 模擬車速變化（最高200km/h，序列重複2輪）
    base_speeds = [0, 80, 120, 160, 200, 160, 120, 80, 0]
    test_speeds = base_speeds * 2  # 連續2輪
    current_index = [0]

    def update_speed():
        """更新測試速度"""
        if current_index[0] < len(test_speeds):
            speed = test_speeds[current_index[0]]
            print(f"\n設定速度: {speed} km/h")
            dashboard.set_speed(speed)

            # 顯示當前 ODO 數據
            odo_dist = dashboard.odo_card.total_distance
            editing_status = "（輸入模式 - 滑動已禁用）" if dashboard.odo_card.is_editing else ""
            print(f"  ODO: {odo_dist:.3f} km (顯示: {int(odo_dist)} km) {editing_status}")
            print(f"  滑動狀態: {'禁用' if not dashboard.swipe_enabled else '啟用'}")

            current_index[0] += 1
        else:
            print("\n速度模擬完成！")
            print(f"最終 ODO: {dashboard.odo_card.total_distance:.3f} km")
            print("提示：可以點擊「同步里程」測試內嵌虛擬鍵盤")
            print("      輸入時嘗試滑動，會發現已被禁用")
            timer.stop()

    # 每5秒更新一次速度
    timer = QTimer()
    timer.timeout.connect(update_speed)
    timer.start(5000)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
