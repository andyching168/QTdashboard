import os
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from ui.common import RadarOverlay
from ui.theme import T


class DoorStatusCard(QWidget):
    """門狀態顯示卡片"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(380, 380)
        
        self.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {T('BG_CARD')}, stop:1 #0f0f18);
                border-radius: 20px;
            }}
        """)
        
        self.door_fl_closed = True
        self.door_fr_closed = True
        self.door_rl_closed = True
        self.door_rr_closed = True
        self.door_bk_closed = True
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        title_label = QLabel("Door Status")
        title_label.setStyleSheet("""
            color: #6af;
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.image_container = QWidget()
        self.image_container.setFixedSize(340, 280)
        self.image_container.setStyleSheet("background: transparent;")
        
        self.base_layer = QLabel(self.image_container)
        self.base_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.fl_handle_layer = QLabel(self.image_container)
        self.fl_handle_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.fr_handle_layer = QLabel(self.image_container)
        self.fr_handle_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.fl_open_layer = QLabel(self.image_container)
        self.fl_open_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.fr_open_layer = QLabel(self.image_container)
        self.fr_open_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.rl_open_layer = QLabel(self.image_container)
        self.rl_open_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.rr_open_layer = QLabel(self.image_container)
        self.rr_open_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.bk_open_layer = QLabel(self.image_container)
        self.bk_open_layer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.radar_overlay = RadarOverlay(self.image_container)
        self.radar_overlay.setParent(self)
        self.radar_overlay.setGeometry(0, 30, 380, 320)
        self.radar_overlay.raise_()
        
        QTimer.singleShot(0, lambda: self.resizeEvent(None))
        
        for layer in [self.base_layer, self.fl_handle_layer, self.fr_handle_layer,
                      self.fl_open_layer, self.fr_open_layer, self.rl_open_layer,
                      self.rr_open_layer, self.bk_open_layer]:
            layer.setGeometry(0, 0, 340, 280)
        
        self.load_images()
        
        self.status_label = QLabel("All Doors Closed")
        self.status_label.setStyleSheet("""
            color: #6f6;
            font-size: 14px;
            font-weight: bold;
            background: transparent;
        """)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        layout.addWidget(title_label)
        layout.addStretch()
        layout.addWidget(self.image_container, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(self.status_label)
        
        self.update_display()
    
    def resizeEvent(self, event):
        if event is not None:
            super().resizeEvent(event)
        
        if hasattr(self, 'radar_overlay') and hasattr(self, 'image_container'):
            geo = self.image_container.geometry()
            self.radar_overlay.setGeometry(
                geo.x() - 20,
                geo.y() - 20,
                geo.width() + 40,
                geo.height() + 40
            )

    def set_radar_status(self, radar_str):
        import re
        try:
            pattern = r"LR:(\d),RR:(\d),LF:(\d),RF:(\d)"
            match = re.search(pattern, radar_str)
            if match:
                lr = int(match.group(1))
                rr = int(match.group(2))
                lf = int(match.group(3))
                rf = int(match.group(4))
                
                print(f"[DoorCard] Radar: LF={lf}, RF={rf}, LR={lr}, RR={rr}")
                
                self.radar_overlay.set_levels(lf, rf, lr, rr)
                
                if lf > 0 or rf > 0 or lr > 0 or rr > 0:
                    self.status_label.setText("Radar Warning")
                    self.status_label.setStyleSheet("""
                        color: #ff4;
                        font-size: 14px;
                        font-weight: bold;
                        background: transparent;
                    """)
                elif self.door_fl_closed and self.door_fr_closed and \
                     self.door_rl_closed and self.door_rr_closed and self.door_bk_closed:
                    self.status_label.setText("All Doors Closed")
                    self.status_label.setStyleSheet("""
                        color: #6f6;
                        font-size: 14px;
                        font-weight: bold;
                        background: transparent;
                    """)
        except Exception as e:
            print(f"[DoorCard] Radar parse error: {e}")

    def load_images(self):
        """載入所有門狀態圖片"""
        sprite_path = os.path.join(os.path.dirname(__file__), "..", "assets", "sprites", "carSprite")
        
        base_pixmap = QPixmap(os.path.join(sprite_path, "closed_base.png"))
        if not base_pixmap.isNull():
            scaled_base = base_pixmap.scaled(340, 280, 
                                            Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
            self.base_layer.setPixmap(scaled_base)
        
        self.fl_handle_pixmap = QPixmap(os.path.join(sprite_path, "closed_fl_handle.png"))
        self.fr_handle_pixmap = QPixmap(os.path.join(sprite_path, "closed_fr_handle.png"))
        
        self.fl_open_pixmap = QPixmap(os.path.join(sprite_path, "FL.png"))
        self.fr_open_pixmap = QPixmap(os.path.join(sprite_path, "FR.png"))
        self.rl_open_pixmap = QPixmap(os.path.join(sprite_path, "RL.png"))
        self.rr_open_pixmap = QPixmap(os.path.join(sprite_path, "RR.png"))
        self.bk_open_pixmap = QPixmap(os.path.join(sprite_path, "BK.png"))
    
    def set_door_status(self, door, is_closed):
        door = door.upper()
        if door == "FL":
            self.door_fl_closed = is_closed
        elif door == "FR":
            self.door_fr_closed = is_closed
        elif door == "RL":
            self.door_rl_closed = is_closed
        elif door == "RR":
            self.door_rr_closed = is_closed
        elif door == "BK":
            self.door_bk_closed = is_closed
        
        self.update_display()
    
    def update_display(self):
        if self.door_fl_closed:
            scaled_pixmap = self.fl_handle_pixmap.scaled(340, 280,
                                                         Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation)
            self.fl_handle_layer.setPixmap(scaled_pixmap)
            self.fl_open_layer.clear()
        else:
            self.fl_handle_layer.clear()
            scaled_pixmap = self.fl_open_pixmap.scaled(340, 280,
                                                       Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation)
            self.fl_open_layer.setPixmap(scaled_pixmap)
        
        if self.door_fr_closed:
            scaled_pixmap = self.fr_handle_pixmap.scaled(340, 280,
                                                         Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation)
            self.fr_handle_layer.setPixmap(scaled_pixmap)
            self.fr_open_layer.clear()
        else:
            self.fr_handle_layer.clear()
            scaled_pixmap = self.fr_open_pixmap.scaled(340, 280,
                                                       Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation)
            self.fr_open_layer.setPixmap(scaled_pixmap)
        
        if not self.door_rl_closed:
            scaled_pixmap = self.rl_open_pixmap.scaled(340, 280,
                                                       Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation)
            self.rl_open_layer.setPixmap(scaled_pixmap)
        else:
            self.rl_open_layer.clear()
        
        if not self.door_rr_closed:
            scaled_pixmap = self.rr_open_pixmap.scaled(340, 280,
                                                       Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation)
            self.rr_open_layer.setPixmap(scaled_pixmap)
        else:
            self.rr_open_layer.clear()
        
        if not self.door_bk_closed:
            scaled_pixmap = self.bk_open_pixmap.scaled(340, 280,
                                                       Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation)
            self.bk_open_layer.setPixmap(scaled_pixmap)
        else:
            self.bk_open_layer.clear()
        
        open_doors = []
        if not self.door_fl_closed:
            open_doors.append("FL")
        if not self.door_fr_closed:
            open_doors.append("FR")
        if not self.door_rl_closed:
            open_doors.append("RL")
        if not self.door_rr_closed:
            open_doors.append("RR")
        if not self.door_bk_closed:
            open_doors.append("BK")
        
        if open_doors:
            self.status_label.setText(f"Doors Open: {', '.join(open_doors)}")
            self.status_label.setStyleSheet("""
                color: #f66;
                font-size: 14px;
                font-weight: bold;
                background: transparent;
            """)
        else:
            self.status_label.setText("All Doors Closed")
            self.status_label.setStyleSheet("""
                color: #6f6;
                font-size: 14px;
                font-weight: bold;
                background: transparent;
            """)
    
    def refresh_theme(self):
        """重新整理 UI 主題顏色（更換強調色後呼叫）"""
        pass
