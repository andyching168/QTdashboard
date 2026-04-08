# Auto-extracted from main.py
import time
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

from ui.theme import T

class NavigationCard(QWidget):
    """導航資訊卡片 - 顯示導航方向、距離、時間等資訊"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(800, 380)
        
        # 設置背景樣式
        self.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {T('BG_CARD')}, stop:1 #0f0f18);
                border-radius: 20px;
            }}
        """)
        
        # 導航資料
        self.direction = ""
        self.total_distance = ""
        self.turn_distance = ""
        self.turn_direction = ""
        self.duration = ""
        self.eta = ""
        self.icon_base64 = ""
        
        # 主佈局使用 StackedWidget 切換無導航/有導航模式
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)
        
        # 頁面 1：無導航狀態
        self.no_nav_page = QWidget()
        self.setup_no_nav_ui()
        self.stack.addWidget(self.no_nav_page)
        
        # 頁面 2：導航中狀態
        self.nav_page = QWidget()
        self.setup_nav_ui()
        self.stack.addWidget(self.nav_page)
        
        # 預設顯示無導航狀態
        self.stack.setCurrentWidget(self.no_nav_page)
        
        # 網路斷線覆蓋層
        self.offline_overlay = QWidget(self)
        self.offline_overlay.setGeometry(0, 0, 800, 380)
        self.offline_overlay.setStyleSheet(f"""
            background: rgba(10, 10, 15, 0.9);
            border-radius: 20px;
        """)
        self.offline_overlay.hide()
        
        offline_layout = QVBoxLayout(self.offline_overlay)
        offline_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        offline_icon = QLabel("📡")
        offline_icon.setStyleSheet("font-size: 60px; background: transparent;")
        offline_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        offline_text = QLabel("網路已斷線")
        offline_text.setStyleSheet("color: #f66; font-size: 28px; font-weight: bold; background: transparent;")
        offline_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        offline_desc = QLabel("請檢查網路連線")
        offline_desc.setStyleSheet("color: {T('TEXT_SECONDARY')}; font-size: 16px; background: transparent;")
        offline_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        offline_layout.addWidget(offline_icon)
        offline_layout.addWidget(offline_text)
        offline_layout.addWidget(offline_desc)
    
    def set_offline(self, is_offline):
        """設定離線狀態"""
        if is_offline:
            self.offline_overlay.raise_()
            self.offline_overlay.show()
        else:
            self.offline_overlay.hide()
    
    def setup_no_nav_ui(self):
        """設置無導航狀態的 UI"""
        layout = QHBoxLayout(self.no_nav_page)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(30)
        
        # 左側大圖標
        icon_label = QLabel("🧭")
        icon_label.setStyleSheet("font-size: 120px; background: transparent;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(200, 200)
        
        # 右側文字
        right_widget = QWidget()
        right_widget.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(15)
        
        text_label = QLabel("無導航資訊")
        text_label.setStyleSheet("color: white; font-size: 32px; font-weight: bold; background: transparent;")
        
        desc_label = QLabel("開始導航後，資訊將自動顯示於此")
        desc_label.setStyleSheet("color: #aaa; font-size: 18px; background: transparent;")
        desc_label.setWordWrap(True)
        
        right_layout.addStretch()
        right_layout.addWidget(text_label)
        right_layout.addWidget(desc_label)
        right_layout.addStretch()
        
        layout.addWidget(icon_label)
        layout.addWidget(right_widget, 1)
    
    def setup_nav_ui(self):
        """設置導航中狀態的 UI"""
        layout = QHBoxLayout(self.nav_page)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(30)
        
        # === 左側：方向圖標 ===
        icon_container = QWidget()
        icon_container.setFixedSize(320, 320)
        icon_container.setStyleSheet("background: transparent;")
        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.direction_icon = QLabel()
        self.direction_icon.setFixedSize(280, 280)
        self.direction_icon.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #2a3a4a, stop:0.5 #1d2d3d, stop:1 #101a2a);
            border-radius: 20px;
            border: 3px solid #3a5a7a;
        """)
        self.direction_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 預設圖標
        self.default_icon = QLabel("↑", self.direction_icon)
        self.default_icon.setStyleSheet(f"""
            color: {{T('PRIMARY')}};
            font-size: 120px;
            background: transparent;
        """)
        self.default_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.default_icon.setGeometry(0, 0, 280, 280)
        
        icon_layout.addWidget(self.direction_icon)
        
        # === 右側：導航資訊 ===
        info_container = QWidget()
        info_container.setStyleSheet("background: transparent;")
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 10, 0, 10)
        info_layout.setSpacing(15)
        
        # Navigation 標題
        title_label = QLabel("Navigation")
        title_label.setStyleSheet(f"""
            color: {{T('PRIMARY')}};
            font-size: 16px;
            font-weight: bold;
            background: transparent;
            letter-spacing: 2px;
        """)
        
        # 方向說明（大字）- 支援自動縮小與換行
        self.direction_label = QLabel("--")
        self.direction_label.setStyleSheet(f"""
            color: white;
            font-size: 36px;
            font-weight: bold;
            background: transparent;
        """)
        self.direction_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.direction_label.setFixedHeight(60)  # 稍微增加高度以容納兩行
        self.direction_label.setWordWrap(True)  # 允許換行
        
        # 資訊區塊容器
        info_grid = QWidget()
        info_grid.setStyleSheet("background: transparent;")
        grid_layout = QGridLayout(info_grid)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(12)
        
        # 下個轉彎距離（突出顯示）
        turn_distance_title = QLabel("下個轉彎")
        turn_distance_title.setStyleSheet("color: {T('TEXT_SECONDARY')}; font-size: 14px; background: transparent;")
        self.turn_distance_value = QLabel("--")
        self.turn_distance_value.setStyleSheet("color: #6f6; font-size: 28px; font-weight: bold; background: transparent;")
        
        # 總距離
        distance_title = QLabel("總距離")
        distance_title.setStyleSheet("color: {T('TEXT_SECONDARY')}; font-size: 14px; background: transparent;")
        self.distance_value = QLabel("--")
        self.distance_value.setStyleSheet("color: #ccc; font-size: 20px; font-weight: bold; background: transparent;")
        
        # 預計時間
        duration_title = QLabel("預計時間")
        duration_title.setStyleSheet("color: {T('TEXT_SECONDARY')}; font-size: 14px; background: transparent;")
        self.duration_value = QLabel("--")
        self.duration_value.setStyleSheet("color: #ccc; font-size: 20px; font-weight: bold; background: transparent;")
        
        # 抵達時間
        eta_title = QLabel("抵達時間")
        eta_title.setStyleSheet("color: {T('TEXT_SECONDARY')}; font-size: 14px; background: transparent;")
        self.eta_value = QLabel("--")
        self.eta_value.setStyleSheet("color: {T('PRIMARY')}; font-size: 24px; font-weight: bold; background: transparent;")
        
        # 佈局：
        # Row 0: 下個轉彎(標題)  | 總距離(標題)
        # Row 1: 下個轉彎(值)    | 總距離(值)
        # Row 2: 預計時間(標題) | 抵達時間(標題)
        # Row 3: 預計時間(值)   | 抵達時間(值)
        grid_layout.addWidget(turn_distance_title, 0, 0)
        grid_layout.addWidget(self.turn_distance_value, 1, 0)
        grid_layout.addWidget(distance_title, 0, 1)
        grid_layout.addWidget(self.distance_value, 1, 1)
        grid_layout.addWidget(duration_title, 2, 0)
        grid_layout.addWidget(self.duration_value, 3, 0)
        grid_layout.addWidget(eta_title, 2, 1)
        grid_layout.addWidget(self.eta_value, 3, 1)
        
        # 組合右側佈局
        info_layout.addWidget(title_label)
        info_layout.addSpacing(10)
        info_layout.addWidget(self.direction_label)
        info_layout.addSpacing(10)
        info_layout.addWidget(info_grid)
        info_layout.addStretch()
        
        # 組合主佈局
        layout.addWidget(icon_container)
        layout.addWidget(info_container, 1)
    
    def show_no_nav_ui(self):
        """顯示無導航狀態"""
        self.stack.setCurrentWidget(self.no_nav_page)
    
    def show_nav_ui(self):
        """顯示導航中狀態"""
        self.stack.setCurrentWidget(self.nav_page)
    
    def update_navigation(self, nav_data: dict):
        """
        更新導航資訊
        
        Args:
            nav_data: 包含以下欄位的字典
                - direction: 方向說明（如 "往南"）
                - totalDistance: 總距離（如 "9.3 公里"）
                - turnDistance: 下一個轉彎距離（如 "500 公尺"）
                - turnDirection: 轉彎方向（如 "左轉"）
                - duration: 預計時間（如 "24 分鐘"）
                - eta: 抵達時間（如 "12:32"）
                - iconBase64: 方向圖標的 base64 編碼 PNG
        """
        if not nav_data:
            self.show_no_nav_ui()
            return
        
        # 檢查關鍵欄位是否都為空，若是則顯示無導航狀態
        direction = nav_data.get('direction', '').strip()
        total_distance = nav_data.get('totalDistance', '').strip()
        turn_distance = nav_data.get('turnDistance', '').strip()
        turn_direction = nav_data.get('turnDirection', '').strip()
        
        if not direction and not total_distance and not turn_distance and not turn_direction:
            self.show_no_nav_ui()
            return
        
        # 更新資料
        self.direction = nav_data.get('direction', '')
        self.total_distance = nav_data.get('totalDistance', '')
        self.turn_distance = nav_data.get('turnDistance', '')
        self.turn_direction = nav_data.get('turnDirection', '')
        self.duration = nav_data.get('duration', '')
        self.eta = nav_data.get('eta', '')
        self.icon_base64 = nav_data.get('iconBase64', '')
        
        # 更新顯示
        self._update_direction_label(self.direction if self.direction else "--")
        self.turn_distance_value.setText(self.turn_distance if self.turn_distance else "--")
        self.distance_value.setText(self.total_distance if self.total_distance else "--")
        self.duration_value.setText(self.duration if self.duration else "--")
        self.eta_value.setText(self.eta if self.eta else "--")
        
        # 更新圖標
        if self.icon_base64:
            self._set_icon_from_base64(self.icon_base64)
        else:
            self._reset_icon()
        
        # 切換到導航頁面
        self.show_nav_ui()
    
    def _set_icon_from_base64(self, base64_data: str):
        """從 base64 編碼設置方向圖標"""
        try:
            import base64
            
            # 移除可能的換行符和空白
            base64_data = base64_data.replace('\n', '').replace(' ', '')
            
            # 解碼 base64
            image_data = base64.b64decode(base64_data)
            
            # 創建 QPixmap
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            
            if not pixmap.isNull():
                # 縮放圖片
                scaled_pixmap = pixmap.scaled(
                    240, 240,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                # 創建圓角遮罩
                rounded_pixmap = QPixmap(280, 280)
                rounded_pixmap.fill(Qt.GlobalColor.transparent)
                
                painter = QPainter(rounded_pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                
                # 背景
                path = QPainterPath()
                path.addRoundedRect(0, 0, 280, 280, 20, 20)
                
                bg_gradient = QLinearGradient(0, 0, 280, 280)
                bg_gradient.setColorAt(0, QColor(42, 58, 74))
                bg_gradient.setColorAt(0.5, QColor(29, 45, 61))
                bg_gradient.setColorAt(1, QColor(16, 26, 42))
                painter.fillPath(path, bg_gradient)
                
                # 繪製圖標（居中）
                x = (280 - scaled_pixmap.width()) // 2
                y = (280 - scaled_pixmap.height()) // 2
                painter.drawPixmap(x, y, scaled_pixmap)
                
                # 邊框
                pen = QPen(QColor("#3a5a7a"))
                pen.setWidth(6)
                painter.strokePath(path, pen)
                
                painter.end()
                
                self.direction_icon.setPixmap(rounded_pixmap)
                self.direction_icon.setStyleSheet("background: transparent; border: none;")
                self.default_icon.hide()
            else:
                self._reset_icon()
        except Exception as e:
            print(f"[NavigationCard] 載入圖標失敗: {e}")
            self._reset_icon()
    
    def _reset_icon(self):
        """重置為預設圖標"""
        self.direction_icon.clear()
        self.direction_icon.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #2a3a4a, stop:0.5 #1d2d3d, stop:1 #101a2a);
            border-radius: 20px;
            border: 3px solid #3a5a7a;
        """)
        self.default_icon.show()
    
    def _update_direction_label(self, text):
        """更新方向說明標籤，根據文字長度自動調整字體大小和換行"""
        # 計算文字長度（中文字算 1，英數字算 0.5）
        def calc_display_length(s):
            length = 0
            for char in s:
                if ord(char) > 127:  # 中文或全形字
                    length += 1
                else:
                    length += 0.5
            return length
        
        display_len = calc_display_length(text)
        
        if display_len <= 10:
            # 短文字：單行大字
            self.direction_label.setStyleSheet("""
                color: white;
                font-size: 36px;
                font-weight: bold;
                background: transparent;
            """)
            self.direction_label.setText(text)
        else:
            # 長文字：縮小字體，允許換行
            wrapped_text = text
            
            # 優先在空格處換行（如「土城出口 台3線/台65線」→「土城出口\n台3線/台65線」）
            if " " in text:
                # 找到最接近中間的空格
                spaces = [i for i, c in enumerate(text) if c == " "]
                mid = len(text) // 2
                best_space = min(spaces, key=lambda x: abs(x - mid))
                wrapped_text = text[:best_space] + "\n" + text[best_space + 1:]
            elif "/" in text:
                # 沒有空格時，才在 "/" 後換行
                # 找到最接近中間的 "/"
                slashes = [i for i, c in enumerate(text) if c == "/"]
                mid = len(text) // 2
                best_slash = min(slashes, key=lambda x: abs(x - mid))
                wrapped_text = text[:best_slash + 1] + "\n" + text[best_slash + 1:]
            
            self.direction_label.setStyleSheet("""
                color: white;
                font-size: 22px;
                font-weight: bold;
                background: transparent;
                line-height: 1.1;
            """)
            self.direction_label.setText(wrapped_text)
    
    def clear_navigation(self):
        """清除導航資訊，回到無導航狀態"""
        self.direction = ""
        self.total_distance = ""
        self.turn_distance = ""
        self.turn_direction = ""
        self.duration = ""
        self.eta = ""
        self.icon_base64 = ""
        self._reset_icon()
        self.show_no_nav_ui()
    
    def refresh_theme(self):
        """重新整理 UI 主題顏色（更換強調色後呼叫）"""
        if hasattr(self, 'no_nav_page'):
            self.setup_no_nav_ui()
        if hasattr(self, 'nav_page'):
            self.setup_nav_ui()



