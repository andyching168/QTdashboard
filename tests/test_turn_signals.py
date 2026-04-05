#!/usr/bin/env python3
"""
測試方向燈功能
模擬 CAN bus 訊號控制方向燈
"""

import sys
import time
from PyQt6.QtWidgets import QApplication
from main import Dashboard


def test_turn_signals():
    """測試方向燈自動控制"""
    print("=== 方向燈測試 ===")
    print()
    print("啟動儀表板...")
    
    app = QApplication(sys.argv)
    dashboard = Dashboard()
    dashboard.show()
    
    print("✓ 儀表板已啟動")
    print()
    print("自動測試序列：")
    print("  3 秒後開啟左轉燈")
    print("  3 秒後關閉")
    print("  3 秒後開啟右轉燈")
    print("  3 秒後關閉")
    print("  3 秒後開啟雙閃")
    print("  3 秒後關閉")
    print()
    print("鍵盤控制：")
    print("  Z: 左轉燈")
    print("  X: 右轉燈")
    print("  C: 雙閃")
    print("  (再按一次關閉)")
    print()
    
    # 自動測試序列
    from PyQt6.QtCore import QTimer
    
    def test_sequence():
        """測試序列"""
        tests = [
            (3000, lambda: (dashboard.set_turn_signal("left"), print("→ 左轉燈開啟"))),
            (6000, lambda: (dashboard.set_turn_signal("off"), print("→ 左轉燈關閉"))),
            (9000, lambda: (dashboard.set_turn_signal("right"), print("→ 右轉燈開啟"))),
            (12000, lambda: (dashboard.set_turn_signal("off"), print("→ 右轉燈關閉"))),
            (15000, lambda: (dashboard.set_turn_signal("both"), print("→ 雙閃開啟"))),
            (18000, lambda: (dashboard.set_turn_signal("off"), print("→ 雙閃關閉"))),
            (19000, lambda: print("\n✅ 自動測試完成！可以使用鍵盤繼續測試")),
        ]
        
        for delay, action in tests:
            QTimer.singleShot(delay, action)
    
    # 啟動測試
    QTimer.singleShot(100, test_sequence)
    
    sys.exit(app.exec())


if __name__ == '__main__':
    test_turn_signals()
