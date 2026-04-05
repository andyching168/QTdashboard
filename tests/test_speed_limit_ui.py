#!/usr/bin/env python3
"""
速限 UI 測試腳本
在 Mac 上測試速限顯示效果，無需 CAN Bus 或完整 dashboard
"""

import sys
import os

# 確保專案根目錄在 Python 路徑中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from navigation.speed_limit import query_speed_limit


class SpeedLimitTestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("速限 UI 測試")
        self.setFixedSize(400, 200)
        
        # 速限狀態
        self.current_speed_limit = None
        self.current_speed_limit_dual = None
        self._speed_limit_flashing = False
        self._speed_limit_timer = 0
        
        # Mock GPS 座標（在國道上）
        self.gps_lat = 24.9850
        self.gps_lon = 121.4921
        self.bearing = 0  # 北上
        
        # 測試座標列表
        self.test_coords = [
            (24.9850, 121.4921, 0, "國3 35K 北上"),
            (24.9850, 121.4921, 180, "國3 35K 南下"),
            (24.9850, 121.4921, None, "國3 35K 雙向"),
            (23.6751, 120.5846, None, "國3 267K"),
            (22.7090, 120.3604, None, "國10 0K"),
            (25.0330, 121.5654, None, "台北市區 (非國道)"),
        ]
        self.current_coord_index = 0
        
        self._setup_ui()
        self._setup_timer()
        self._update_speed_limit()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 速限標籤
        self.speed_limit_label = QLabel("--")
        self.speed_limit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_limit_label.setStyleSheet("""
            QLabel {
                color: #4ade80;
                font-size: 72px;
                font-weight: bold;
                background: transparent;
            }
        """)
        layout.addWidget(self.speed_limit_label)
        
        # 位置資訊
        self.info_label = QLabel("等待更新...")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet("""
            QLabel {
                color: #888;
                font-size: 14px;
            }
        """)
        layout.addWidget(self.info_label)
        
        # 操作說明
        self.hint_label = QLabel("按 N 切換座標 | 按 B 切換方向 | 按 Q 退出")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setStyleSheet("""
            QLabel {
                color: #555;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.hint_label)
        
        self.setLayout(layout)
    
    def _setup_timer(self):
        # 速限閃爍計時器
        self.flash_timer = QTimer()
        self.flash_timer.timeout.connect(self._update_speed_limit_flash)
        self.flash_timer.start(50)  # 50ms
    
    def keyPressEvent(self, event):
        key = event.key()
        
        if key == Qt.Key.Key_N:
            # 切換座標
            self.current_coord_index = (self.current_coord_index + 1) % len(self.test_coords)
            lat, lon, bearing, desc = self.test_coords[self.current_coord_index]
            self.gps_lat = lat
            self.gps_lon = lon
            if bearing is not None:
                self.bearing = bearing
            self._update_speed_limit()
            
        elif key == Qt.Key.Key_B:
            # 切換方向 (0 -> 90 -> 180 -> 270 -> 0)
            directions = [0, 90, 180, 270]
            current_idx = directions.index(self.bearing) if self.bearing in directions else 0
            self.bearing = directions[(current_idx + 1) % len(directions)]
            self._update_speed_limit()
            
        elif key == Qt.Key.Key_Q:
            self.close()
    
    def _update_speed_limit(self):
        """根據 GPS 座標更新速限"""
        limit, direction, dual_limits = query_speed_limit(self.gps_lat, self.gps_lon, self.bearing)
        
        if limit != self.current_speed_limit or dual_limits != self.current_speed_limit_dual:
            self.current_speed_limit = limit
            self.current_speed_limit_dual = dual_limits
            self._apply_speed_limit_style()
            
            # 更新資訊
            lat, lon, bearing, desc = self.test_coords[self.current_coord_index]
            bearing_str = f"{bearing}°" if bearing is not None else "無方向"
            info = f"{desc} | {bearing_str} | lat={lat:.4f} lon={lon:.4f}"
            self.info_label.setText(info)
    
    def _apply_speed_limit_style(self):
        """應用速限標籤樣式"""
        limit = self.current_speed_limit
        dual_limits = self.current_speed_limit_dual
        
        if limit is None and not dual_limits:
            self.speed_limit_label.setText("--")
            self.speed_limit_label.setStyleSheet("""
                QLabel {
                    color: #888;
                    font-size: 72px;
                    font-weight: bold;
                    background: transparent;
                }
            """)
            self._speed_limit_flashing = False
            return
        
        # 處理雙向速限顯示 (N:XX / S:XX)
        if dual_limits and len(dual_limits) > 1:
            n_speed = dual_limits.get('N', '-')
            s_speed = dual_limits.get('S', '-')
            self.speed_limit_label.setText(f"N:{n_speed} S:{s_speed}")
            self.speed_limit_label.setStyleSheet("""
                QLabel {
                    color: #facc15;
                    font-size: 48px;
                    font-weight: bold;
                    background: transparent;
                }
            """)
            self._speed_limit_flashing = False
            return
        
        # 一般單一速限
        if limit is None:
            self.speed_limit_label.setText("--")
            self._speed_limit_flashing = False
            return
        
        self.speed_limit_label.setText(str(limit))
        
        # 假設當前速度為 90 km/h，檢查是否超速
        current_speed = 90  # Mock 速度
        if current_speed >= limit + 10:
            # 超速 10+ km/h，紅色閃爍
            self._speed_limit_flashing = True
            self.speed_limit_label.setStyleSheet("""
                QLabel {
                    color: #ef4444;
                    font-size: 72px;
                    font-weight: bold;
                    background: transparent;
                }
            """)
        else:
            # 正常速限，綠色
            self._speed_limit_flashing = False
            self.speed_limit_label.setStyleSheet("""
                QLabel {
                    color: #4ade80;
                    font-size: 72px;
                    font-weight: bold;
                    background: transparent;
                }
            """)
    
    def _update_speed_limit_flash(self):
        """速限閃爍計時器 callback"""
        if not self._speed_limit_flashing:
            return
        
        self._speed_limit_timer += 1
        if self._speed_limit_timer % 10 == 0:  # 每 10 ticks 切換一次
            current = self.speed_limit_label.styleSheet()
            if "color: #ef4444" in current:
                self.speed_limit_label.setStyleSheet("""
                    QLabel {
                        color: transparent;
                        font-size: 72px;
                        font-weight: bold;
                        background: transparent;
                    }
                """)
            else:
                self.speed_limit_label.setStyleSheet("""
                    QLabel {
                        color: #ef4444;
                        font-size: 72px;
                        font-weight: bold;
                        background: transparent;
                    }
                """)


def main():
    app = QApplication(sys.argv)
    
    print("=" * 50)
    print("速限 UI 測試")
    print("=" * 50)
    print("操作說明:")
    print("  N - 切換到下一個測試座標")
    print("  B - 切換行駛方向 (0°/90°/180°/270°)")
    print("  Q - 離開測試")
    print("=" * 50)
    
    window = SpeedLimitTestWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
