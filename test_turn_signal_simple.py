#!/usr/bin/env python3
"""
簡化版方向燈測試 - 不依賴 Spotify
直接測試 Dashboard 的方向燈功能
"""

import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import QTimer, Qt

# 建立簡化版儀表板 - 只包含方向燈相關元件
class SimpleDashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("方向燈測試")
        self.setFixedSize(800, 400)
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # 狀態標籤
        self.status_label = QLabel("方向燈狀態: 關閉")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 24px; color: white; padding: 20px;")
        layout.addWidget(self.status_label)
        
        # 方向燈指示
        indicator_layout = QVBoxLayout()
        
        self.left_indicator = QLabel("⬅ 左轉燈")
        self.left_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.left_indicator.setStyleSheet("""
            font-size: 48px;
            color: #333;
            background: #111;
            padding: 20px;
            border: 3px solid #333;
            border-radius: 10px;
        """)
        
        self.right_indicator = QLabel("右轉燈 ➡")
        self.right_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.right_indicator.setStyleSheet("""
            font-size: 48px;
            color: #333;
            background: #111;
            padding: 20px;
            border: 3px solid #333;
            border-radius: 10px;
        """)
        
        indicator_layout.addWidget(self.left_indicator)
        indicator_layout.addWidget(self.right_indicator)
        layout.addLayout(indicator_layout)
        
        # 控制按鈕
        btn_layout = QVBoxLayout()
        
        btn_left = QPushButton("左轉燈 ON/OFF")
        btn_left.clicked.connect(lambda: self.toggle_signal("left"))
        btn_left.setStyleSheet("font-size: 16px; padding: 10px;")
        
        btn_right = QPushButton("右轉燈 ON/OFF")
        btn_right.clicked.connect(lambda: self.toggle_signal("right"))
        btn_right.setStyleSheet("font-size: 16px; padding: 10px;")
        
        btn_both = QPushButton("雙閃 ON/OFF")
        btn_both.clicked.connect(lambda: self.toggle_signal("both"))
        btn_both.setStyleSheet("font-size: 16px; padding: 10px;")
        
        btn_off = QPushButton("全部關閉")
        btn_off.clicked.connect(lambda: self.set_turn_signal("off"))
        btn_off.setStyleSheet("font-size: 16px; padding: 10px; background: #c44;")
        
        btn_layout.addWidget(btn_left)
        btn_layout.addWidget(btn_right)
        btn_layout.addWidget(btn_both)
        btn_layout.addWidget(btn_off)
        layout.addLayout(btn_layout)
        
        # 方向燈狀態
        self.left_on = False
        self.right_on = False
        
        # 背景色
        self.setStyleSheet("background: #222;")
    
    def toggle_signal(self, direction):
        """切換方向燈"""
        if direction == "left":
            if self.left_on:
                self.set_turn_signal("left_off")
            else:
                self.set_turn_signal("left_on")
        elif direction == "right":
            if self.right_on:
                self.set_turn_signal("right_off")
            else:
                self.set_turn_signal("right_on")
        elif direction == "both":
            if self.left_on and self.right_on:
                self.set_turn_signal("off")
            else:
                self.set_turn_signal("both_on")
    
    def set_turn_signal(self, state):
        """設定方向燈狀態"""
        print(f"[方向燈] {state}")
        
        if state == "left_on":
            self.left_on = True
            self.right_on = False
            self.status_label.setText("方向燈狀態: 左轉")
        elif state == "left_off":
            self.left_on = False
            self.status_label.setText("方向燈狀態: 關閉")
        elif state == "right_on":
            self.right_on = True
            self.left_on = False
            self.status_label.setText("方向燈狀態: 右轉")
        elif state == "right_off":
            self.right_on = False
            self.status_label.setText("方向燈狀態: 關閉")
        elif state == "both_on":
            self.left_on = True
            self.right_on = True
            self.status_label.setText("方向燈狀態: 雙閃 (警示燈)")
        elif state == "both_off" or state == "off":
            self.left_on = False
            self.right_on = False
            self.status_label.setText("方向燈狀態: 關閉")
        
        # 更新視覺效果
        self.update_indicators()
    
    def update_indicators(self):
        """更新指示燈視覺效果"""
        # 左轉燈
        if self.left_on:
            self.left_indicator.setStyleSheet("""
                font-size: 48px;
                color: #00FF00;
                background: #0a3;
                padding: 20px;
                border: 3px solid #0f6;
                border-radius: 10px;
            """)
        else:
            self.left_indicator.setStyleSheet("""
                font-size: 48px;
                color: #333;
                background: #111;
                padding: 20px;
                border: 3px solid #333;
                border-radius: 10px;
            """)
        
        # 右轉燈
        if self.right_on:
            self.right_indicator.setStyleSheet("""
                font-size: 48px;
                color: #00FF00;
                background: #0a3;
                padding: 20px;
                border: 3px solid #0f6;
                border-radius: 10px;
            """)
        else:
            self.right_indicator.setStyleSheet("""
                font-size: 48px;
                color: #333;
                background: #111;
                padding: 20px;
                border: 3px solid #333;
                border-radius: 10px;
            """)

def run_auto_test():
    """自動測試序列"""
    app = QApplication(sys.argv)
    dashboard = SimpleDashboard()
    dashboard.show()
    
    test_sequence = [
        ("off", "初始狀態"),
        ("left_on", "左轉燈亮"),
        ("left_off", "左轉燈滅"),
        ("right_on", "右轉燈亮"),
        ("right_off", "右轉燈滅"),
        ("both_on", "雙閃亮"),
        ("off", "全部關閉"),
    ]
    
    current_step = [0]
    
    def next_step():
        if current_step[0] >= len(test_sequence):
            print("\n✓ 自動測試完成！")
            timer.stop()
            return
        
        state, desc = test_sequence[current_step[0]]
        print(f"\n[步驟 {current_step[0] + 1}/{len(test_sequence)}] {desc}: {state}")
        dashboard.set_turn_signal(state)
        current_step[0] += 1
    
    timer = QTimer()
    timer.timeout.connect(next_step)
    timer.start(1500)  # 每 1.5 秒切換
    
    print("=" * 60)
    print("方向燈自動測試程式")
    print("=" * 60)
    print("將依序測試：")
    for i, (state, desc) in enumerate(test_sequence, 1):
        print(f"  {i}. {desc} ({state})")
    print("=" * 60 + "\n")
    
    next_step()  # 執行第一步
    
    sys.exit(app.exec())

def run_manual_test():
    """手動測試"""
    app = QApplication(sys.argv)
    dashboard = SimpleDashboard()
    dashboard.show()
    
    print("=" * 60)
    print("方向燈手動測試程式")
    print("=" * 60)
    print("使用按鈕控制方向燈，觀察視覺效果")
    print("=" * 60 + "\n")
    
    sys.exit(app.exec())

if __name__ == "__main__":
    # 預設執行自動測試
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "manual":
        run_manual_test()
    else:
        run_auto_test()
