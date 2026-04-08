# Auto-extracted from main.py
import time
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

from core.utils import OdometerStorage
from core.shutdown_monitor import get_shutdown_monitor
from ui.theme import T

# Late import to avoid circular dependency
def get_dashboard_class():
    from main import Dashboard
    return Dashboard

class OdometerCard(QWidget):
    """總里程表卡片 (Odometer) - 內嵌虛擬鍵盤"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(380, 380)
        
        # 設置背景樣式
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a25, stop:1 #0f0f18);
                border-radius: 20px;
            }
        """)
        
        # 總里程數據
        self.total_distance = 0.0  # km
        self.last_sync_time = None
        
        # 當前速度（由 Dashboard 物理心跳驅動里程計算）
        self.current_speed = 0.0
        
        # 輸入狀態
        self.current_input = ""
        self.is_editing = False
        
        # 主佈局使用 StackedWidget 切換顯示/輸入模式
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        
        # === 頁面 1: 顯示模式 ===
        self.display_page = self.create_display_page()
        self.stack.addWidget(self.display_page)
        
        # === 頁面 2: 輸入模式（虛擬鍵盤）===
        self.input_page = self.create_input_page()
        self.stack.addWidget(self.input_page)
        
        # 預設顯示模式
        self.stack.setCurrentWidget(self.display_page)
    
    def create_display_page(self):
        """創建顯示頁面"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # 標題
        title_label = QLabel("Odometer")
        title_label.setStyleSheet(f"""
            color: {T('PRIMARY')};
            font-size: 20px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # ODO 圖標
        icon_label = QLabel("🚗")
        icon_label.setStyleSheet("font-size: 60px; background: transparent;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 總里程顯示區域
        odo_container = QWidget()
        odo_container.setStyleSheet("""
            QWidget {
                background: rgba(30, 30, 40, 0.5);
                border-radius: 15px;
                border: 2px solid #2a2a35;
            }
        """)
        odo_layout = QVBoxLayout(odo_container)
        odo_layout.setContentsMargins(15, 15, 15, 15)
        odo_layout.setSpacing(10)
        
        # 里程顯示
        distance_layout = QHBoxLayout()
        distance_layout.setSpacing(10)
        
        self.odo_distance_label = QLabel("0")
        self.odo_distance_label.setStyleSheet(f"""
            color: {T('TEXT_PRIMARY')};
            font-size: 56px;
            font-weight: bold;
            background: transparent;
        """)
        self.odo_distance_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        unit_label = QLabel("km")
        unit_label.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 24px;
            background: transparent;
        """)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        
        distance_layout.addStretch()
        distance_layout.addWidget(self.odo_distance_label)
        distance_layout.addWidget(unit_label)
        distance_layout.addSpacing(10)
        
        # 同步時間顯示
        self.sync_time_label = QLabel("未同步")
        self.sync_time_label.setStyleSheet(f"""
            color: {T('TEXT_DISABLED')};
            font-size: 12px;
            background: transparent;
        """)
        self.sync_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        odo_layout.addLayout(distance_layout)
        odo_layout.addWidget(self.sync_time_label)
        
        # 同步按鈕
        sync_btn = QPushButton("同步里程")
        sync_btn.setFixedSize(200, 45)
        sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sync_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(100, 150, 255, 0.3);
                color: {T('PRIMARY')};
                border: 2px solid {T('PRIMARY')};
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(100, 150, 255, 0.5);
            }}
            QPushButton:pressed {{
                background-color: rgba(100, 150, 255, 0.7);
            }}
        """)
        sync_btn.clicked.connect(self.show_keypad)
        
        # 組合佈局
        layout.addWidget(title_label)
        layout.addWidget(icon_label)
        layout.addWidget(odo_container)
        layout.addSpacing(10)
        layout.addWidget(sync_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        
        return page
    
    def create_input_page(self):
        """創建輸入頁面（虛擬鍵盤）"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # 標題
        title = QLabel("輸入總里程")
        title.setStyleSheet(f"""
            color: {T('PRIMARY')};
            font-size: 18px;
            font-weight: bold;
            background: transparent;
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 顯示器
        self.input_display = QLabel("0")
        self.input_display.setFixedHeight(50)
        self.input_display.setStyleSheet(f"""
            QLabel {{
                background: #1a1a25;
                color: {T('TEXT_PRIMARY')};
                font-size: 32px;
                font-weight: bold;
                border: 2px solid #4a4a55;
                border-radius: 8px;
                padding: 5px 10px;
            }}
        """)
        self.input_display.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        # 單位標籤
        unit_label = QLabel("km")
        unit_label.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 12px;
            background: transparent;
        """)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        # 按鈕網格
        button_grid = QGridLayout()
        button_grid.setSpacing(8)
        
        # 數字按鈕 1-9
        for i in range(9):
            btn = self.create_number_button(str(i + 1))
            row = i // 3
            col = i % 3
            button_grid.addWidget(btn, row, col)
        
        # 第四行：0, BS
        btn_0 = self.create_number_button("0")
        button_grid.addWidget(btn_0, 3, 0, 1, 2)  # 占兩格
        
        btn_bs = self.create_function_button("⌫", self.backspace)
        button_grid.addWidget(btn_bs, 3, 2)
        
        # 操作按鈕行
        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(40)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: #555;
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #666;
            }}
            QPushButton:pressed {{
                background-color: #444;
            }}
        """)
        btn_cancel.clicked.connect(self.cancel_input)
        
        btn_ok = QPushButton("確定")
        btn_ok.setFixedHeight(40)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(f"""
            QPushButton {{
                background-color: {T('PRIMARY')};
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #5ad;
            }}
            QPushButton:pressed {{
                background-color: #49c;
            }}
        """)
        btn_ok.clicked.connect(self.confirm_input)
        
        action_layout.addWidget(btn_cancel)
        action_layout.addWidget(btn_ok)
        
        # 組合佈局
        layout.addWidget(title)
        layout.addWidget(self.input_display)
        layout.addWidget(unit_label)
        layout.addSpacing(5)
        layout.addLayout(button_grid)
        layout.addLayout(action_layout)
        
        return page
    
    def create_number_button(self, text):
        """創建數字按鈕"""
        btn = QPushButton(text)
        btn.setFixedSize(108, 50)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #3a3a45;
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: 8px;
                font-size: 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #4a4a55;
            }}
            QPushButton:pressed {{
                background-color: #2a2a35;
            }}
        """)
        btn.clicked.connect(lambda: self.append_digit(text))
        return btn
    
    def create_function_button(self, text, callback):
        """創建功能按鈕"""
        btn = QPushButton(text)
        btn.setFixedSize(108, 50)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #6a5acd;
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: 8px;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #7a6add;
            }}
            QPushButton:pressed {{
                background-color: #5a4abd;
            }}
        """)
        btn.clicked.connect(callback)
        return btn
    
    def show_keypad(self):
        """顯示虛擬鍵盤並禁用滑動"""
        self.current_input = str(int(self.total_distance)) if self.total_distance > 0 else ""
        self.input_display.setText(self.current_input if self.current_input else "0")
        self.is_editing = True
        self.stack.setCurrentWidget(self.input_page)
        
        # 通知 Dashboard 禁用滑動
        dashboard = self.get_dashboard()
        if dashboard:
            dashboard.set_swipe_enabled(False)
    
    def append_digit(self, digit):
        """追加數字"""
        if len(self.current_input) < 7:  # 限制最大7位數
            self.current_input += digit
            self.input_display.setText(self.current_input if self.current_input else "0")
    
    def backspace(self):
        """刪除最後一位"""
        if self.current_input:
            self.current_input = self.current_input[:-1]
            self.input_display.setText(self.current_input if self.current_input else "0")
    
    def confirm_input(self):
        """確認輸入"""
        try:
            self.total_distance = float(self.current_input) if self.current_input else 0.0
        except ValueError:
            self.total_distance = 0.0
        
        self.odo_distance_label.setText(f"{int(self.total_distance)}")
        self.last_sync_time = time.time()
        self.update_sync_time_display()
        print(f"里程表已同步: {int(self.total_distance)} km")
        
        self.hide_keypad()
    
    def cancel_input(self):
        """取消輸入"""
        self.hide_keypad()
    
    def hide_keypad(self):
        """隱藏虛擬鍵盤並恢復滑動"""
        self.is_editing = False
        self.stack.setCurrentWidget(self.display_page)
        
        # 通知 Dashboard 恢復滑動
        dashboard = self.get_dashboard()
        if dashboard:
            dashboard.set_swipe_enabled(True)
    
    def get_dashboard(self):
        """獲取 Dashboard 實例"""
        parent = self.parent()
        while parent:
            if isinstance(parent, Dashboard):
                return parent
            parent = parent.parent()
        return None
    
    def add_distance(self, distance_km):
        """由 Dashboard 物理心跳呼叫，累加里程"""
        self.total_distance += distance_km
        # 更新顯示（不帶小數點，模擬真實里程表）
        self.odo_distance_label.setText(f"{int(self.total_distance)}")
    
    def update_sync_time_display(self):
        """更新同步時間顯示"""
        from datetime import datetime
        
        if self.last_sync_time:
            sync_dt = datetime.fromtimestamp(self.last_sync_time)
            time_str = sync_dt.strftime("%Y-%m-%d %H:%M")
            self.sync_time_label.setText(f"上次同步: {time_str}")
        else:
            self.sync_time_label.setText("未同步")



class TripInfoCardWide(QWidget):
    """本次行程資訊卡片（寬版 800x380）- 顯示啟動時間、行駛距離、瞬時/平均油耗"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(800, 380)
        
        # 設置背景樣式
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a25, stop:1 #0f0f18);
                border-radius: 20px;
            }
        """)
        
        # 行程數據
        self.start_time = time.time()  # 啟動時間戳
        self.trip_distance = 0.0        # 本次行駛距離 (km)
        self.instant_fuel = 0.0         # 瞬時油耗 (L/100km)
        self.avg_fuel = 0.0             # 平均油耗 (L/100km)
        self.last_speed = 0.0           # 上次車速
        self.last_update_time = time.time()  # 上次更新時間
        
        # 油耗計算用緩存
        self.rpm = 0.0                  # 當前 RPM
        self.speed = 0.0                # 當前車速 (km/h)
        self.turbo = 0.0                # 渦輪負壓 (bar)
        self.total_fuel_used = 0.0      # 累計燃油消耗 (L)
        self.total_distance = 0.0       # 累計行駛距離 (km)
        self.last_calc_time = time.time()  # 上次計算時間
        self.has_valid_data = False     # 是否有有效數據
        
        # 主佈局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 25, 30, 25)
        main_layout.setSpacing(15)
        
        # 標題
        title_label = QLabel("本次行程")
        title_label.setStyleSheet(f"""
            color: {T('PRIMARY')};
            font-size: 28px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 內容區域 - 2x2 網格
        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        content_layout = QGridLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(20)
        
        # === 左上：運行時間（經過時間）===
        self.elapsed_time_panel, self.elapsed_time_label = self._create_value_panel(
            "運行時間",
            "00:00",
            "",
            "#4ecdc4"  # 青綠色
        )
        content_layout.addWidget(self.elapsed_time_panel, 0, 0)
        
        # === 右上：行駛距離 ===
        self.distance_panel, self.distance_label = self._create_value_panel(
            "行駛距離",
            "0.0",
            "km",
            "#f39c12"  # 橙色
        )
        content_layout.addWidget(self.distance_panel, 0, 1)
        
        # === 左下：瞬時油耗 ===
        self.instant_fuel_panel, self.instant_fuel_label = self._create_value_panel(
            "瞬時油耗",
            "--",
            "L/100km",
            "#e74c3c"  # 紅色
        )
        content_layout.addWidget(self.instant_fuel_panel, 1, 0)
        
        # === 右下：平均油耗 ===
        self.avg_fuel_panel, self.avg_fuel_label = self._create_value_panel(
            "平均油耗",
            "--",
            "L/100km",
            "#2ecc71"  # 綠色
        )
        content_layout.addWidget(self.avg_fuel_panel, 1, 1)
        
        main_layout.addWidget(content_widget, 1)
        
        # 定時器：每分鐘更新經過時間（顯示格式為 hh:mm，無需每秒更新）
        self.elapsed_timer = QTimer()
        self.elapsed_timer.timeout.connect(self._update_elapsed_time)
        self.elapsed_timer.start(60000)  # 每 60 秒更新
        
        # 里程計算由 Dashboard._physics_tick() 統一處理
        # 使用與 Trip A/B 相同的梯形積分法計算邏輯
    
    def _format_elapsed_time(self):
        """格式化經過時間為 hh:mm"""
        elapsed_seconds = int(time.time() - self.start_time)
        hours = elapsed_seconds // 3600
        minutes = (elapsed_seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"
    
    def _update_elapsed_time(self):
        """更新經過時間顯示"""
        self.elapsed_time_label.setText(self._format_elapsed_time())
    
    def _create_value_panel(self, title, value, unit, color):
        """創建數值面板（帶有標題、值和單位）- 無外框"""
        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        # 標題
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"""
            color: {color};
            font-size: 18px;
            font-weight: bold;
            background: transparent;
        """)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 值 + 單位 (水平排列)
        value_widget = QWidget()
        value_widget.setStyleSheet("background: transparent;")
        value_layout = QHBoxLayout(value_widget)
        value_layout.setContentsMargins(0, 0, 0, 0)
        value_layout.setSpacing(8)
        
        value_lbl = QLabel(value)
        value_lbl.setStyleSheet(f"""
            color: {T('TEXT_PRIMARY')};
            font-size: 42px;
            font-weight: bold;
            background: transparent;
        """)
        value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        unit_lbl = QLabel(unit)
        unit_lbl.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 16px;
            background: transparent;
        """)
        unit_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        
        value_layout.addStretch()
        value_layout.addWidget(value_lbl)
        value_layout.addWidget(unit_lbl)
        value_layout.addStretch()
        
        layout.addWidget(title_lbl)
        layout.addWidget(value_widget)
        
        return panel, value_lbl
    
    def update_fuel_consumption(self, instant, avg):
        """更新油耗顯示"""
        self.instant_fuel = instant
        self.avg_fuel = avg
        
        # 更新瞬時油耗顯示
        if instant > 0:
            display_instant = min(19.9, instant)
            self.instant_fuel_label.setText(f"{display_instant:.1f}")
        else:
            self.instant_fuel_label.setText("--")
        
        # 更新平均油耗顯示
        if avg > 0:
            display_avg = min(19.9, avg)
            self.avg_fuel_label.setText(f"{display_avg:.1f}")
        else:
            self.avg_fuel_label.setText("--")
    
    def add_distance(self, distance_km):
        """累加行駛距離"""
        self.trip_distance += distance_km
        self.distance_label.setText(f"{self.trip_distance:.1f}")
    
    def update_from_speed(self, speed_kmh):
        """根據車速更新行駛距離"""
        current_time = time.time()
        delta_time = current_time - self.last_update_time
        
        # 合理的時間間隔內計算距離
        if 0 < delta_time < 2:
            # 使用平均速度計算距離
            avg_speed = (self.last_speed + speed_kmh) / 2
            distance = avg_speed * (delta_time / 3600)  # km
            self.trip_distance += distance
            self.distance_label.setText(f"{self.trip_distance:.1f}")
        
        self.last_speed = speed_kmh
        self.last_update_time = current_time
    
    def update_rpm(self, rpm):
        """接收 RPM 更新並計算油耗"""
        self.rpm = rpm * 1000  # 轉換回 RPM
        self._calculate_fuel()
    
    def update_speed(self, speed_kmh):
        """接收 Speed 更新並計算油耗"""
        self.speed = speed_kmh
        self._calculate_fuel()
        # 里程計算改由定時器處理，這裡只更新速度緩存
        self.last_speed = speed_kmh
    
    def update_turbo(self, turbo_bar):
        """接收渦輪負壓更新並計算油耗"""
        self.turbo = turbo_bar
        self._calculate_fuel()
    
    def _calculate_fuel(self):
        """
        計算油耗 (修正版：基於 Speed-Density 法，加入渦輪增壓補償與 DFCO)
        適用：Luxgen M7 2.2T
        """
        # 1. 基礎過濾：RPM 過低或速度為 0 不計算
        if self.rpm < 50 or self.speed < 1:
            self.instant_fuel = 0.0
            self.instant_fuel_label.setText("--")
            return

        # --- 常數設定 ---
        ENGINE_DISPLACEMENT = 2.2   # 排氣量 (L)
        # 汽油密度 (kg/L), 一般約 0.72~0.75
        FUEL_DENSITY = 0.74         
        # 空氣密度 (kg/m^3 或 g/L), 假設進氣溫約 40-50度C 的平均值
        # 如果有 IAT (進氣溫) 數據，公式為: 1.293 * (273 / (273 + T_celsius))
        AIR_DENSITY_BASE = 1.15     

        # --- 步驟 A: 計算 MAP (進氣壓力) ---
        # turbo 為 bar (例如 -0.6 或 +0.8)
        # 轉為絕對壓力 (Bar) -> 1.013 是標準大氣壓
        map_bar = max(0.1, 1.013 + self.turbo)

        # --- 步驟 B: 判斷減速斷油 (DFCO - Deceleration Fuel Cut Off) ---
        # 條件：轉速高於 1100 且 真空值極低 (例如低於 -0.65 bar，代表節氣門全關)
        # 注意：M7 的怠速真空約在 -0.6 左右，滑行通常更低
        is_dfco = (self.rpm > 1100) and (self.turbo < -0.65)
        
        if is_dfco:
            fuel_rate_lph = 0.0
            ve = 0.0
            target_afr = 0.0
        else:
            # --- 步驟 C: 計算動態 VE (容積效率) ---
            # 簡單模擬：峰值扭力區間 (2400-4000rpm) VE 最高
            # 基礎 VE
            if self.rpm < 2000:
                ve = 0.80 + (self.rpm / 2000) * 0.10  # 0.80 -> 0.90
            elif 2000 <= self.rpm <= 4500:
                ve = 0.90 + (self.turbo * 0.05)       # 增壓時 VE 會略升
            else:
                ve = 0.85 # 高轉衰退
            
            # 限制 VE 範圍 (渦輪車打高增壓時 VE 可能超過 1.0，但在計算油量時保守點)
            ve = max(0.7, min(1.05, ve))

            # --- 步驟 D: 計算動態 AFR (空燃比) ---
            # 這是修正誤差的關鍵：增壓時要噴濃
            if self.turbo > 0.1:
                # 增壓狀態 (Boost): 線性從 14.7 降到 11.5 (全增壓保護)
                target_afr = 14.7 - (self.turbo * 2.5) 
                target_afr = max(11.0, target_afr)
            elif self.turbo < -0.1:
                # 巡航/輕負載: 稍微稀薄燃燒或標準
                target_afr = 14.7
            else:
                target_afr = 14.7

            # --- 步驟 E: 物理公式計算噴油量 ---
            # 1. 進氣量 (L/hr) = (RPM/2 * 60) * 排氣量 * VE * (MAP壓力比)
            # 2. 進氣質量 (kg/hr) = 進氣量 * 空氣密度 / 1000
            # 3. 燃油質量 (kg/hr) = 進氣質量 / AFR
            # 4. 燃油體積 (L/hr)  = 燃油質量 / 汽油密度

            # 簡化合併後的公式：
            # Fuel(L/h) = (RPM * Disp * VE * MAP_bar * Air_Const) / (AFR * Fuel_Density)
            # Air_Const 包含了 RPM/2, *60, 以及空氣密度修正
            
            # 理論進氣體積流率 (m^3/hr at ambient pressure) -> 換算有點複雜，直接用質量流法
            # 質量流率 (Mass Air Flow) g/s approx = RPM/60 * Disp/2 * VE * AirDensity * PressureRatio
            
            pressure_ratio = map_bar / 1.013
            air_mass_flow_g_sec = (self.rpm / 60) * (ENGINE_DISPLACEMENT / 2) * ve * AIR_DENSITY_BASE * pressure_ratio
            
            # 換算成燃油 (L/h)
            fuel_mass_g_sec = air_mass_flow_g_sec / target_afr
            fuel_rate_lph = (fuel_mass_g_sec * 3600) / (FUEL_DENSITY * 1000)

            # --- 全局校正因子 (Global Adjustment) ---
            # 根據實際加油數據調整此值。如果儀表顯示比實際耗油，調低此值 (例如 0.95)
            # Luxgen 舊引擎效率較差，可能需要補償
            CALIBRATION_FACTOR = 1.05 
            fuel_rate_lph *= CALIBRATION_FACTOR

        # 限制合理範圍 (M7 怠速約 1.2-1.5L/h, 全油門可能達 30-40L/h)
        fuel_rate_lph = max(0.0, min(50.0, fuel_rate_lph))

        # --- 以下為顯示邏輯 (與原程式類似) ---
        
        # 瞬時油耗 (L/100km) = (L/h / km/h) * 100
        if self.speed > 3:
            instant = (fuel_rate_lph / self.speed) * 100
            # 限制顯示範圍 (避免剛起步數值爆表)
            instant = max(0.0, min(50.0, instant))
        elif fuel_rate_lph == 0:
            instant = 0.0 # DFCO
        else:
            instant = 99.9 # 怠速或極低速顯示無限大

        # 更新 UI
        # 更新 UI
        self.instant_fuel = instant
        
        # 限制顯示上限 19.9
        display_instant = min(19.9, instant)
        self.instant_fuel_label.setText(f"{display_instant:.1f}")

        # --- 平均油耗累積計算 ---
        current_time = time.time()
        
        if not self.has_valid_data:
            self.last_calc_time = current_time
            self.has_valid_data = True
            self.total_fuel_used = 0.0
            self.total_distance = 0.0
        else:
            delta_time = current_time - self.last_calc_time
            # 只有在時間差合理時才積分 (避免休眠喚醒後的爆量)
            if 0 < delta_time < 2: 
                # 積分：油量 (L)
                step_fuel = fuel_rate_lph * (delta_time / 3600)
                # 積分：距離 (km)
                step_dist = self.speed * (delta_time / 3600)
                
                self.total_fuel_used += step_fuel
                self.total_distance += step_dist
                
            self.last_calc_time = current_time

        # 更新平均油耗 (至少行駛 0.5km 後才顯示)
        if self.total_distance > 0.5:
            avg = (self.total_fuel_used / self.total_distance) * 100
            self.avg_fuel = avg

            # Update ShutdownMonitor with all trip info
            elapsed_time = self._format_elapsed_time()
            get_shutdown_monitor().update_trip_info(elapsed_time, self.trip_distance, avg)

            # 限制顯示上限 19.9
            display_avg = min(19.9, avg)
            self.avg_fuel_label.setText(f"{display_avg:.1f}")
            
        # DEBUG (建議保留一陣子觀察 Turbo 與 AFR 的關係)
        # print(f"RPM:{self.rpm} MAP:{map_bar:.2f} VE:{ve:.2f} AFR:{target_afr:.1f} Fuel:{fuel_rate_lph:.2f}L/h")

    def get_trip_info(self):
        """取得本次行程資訊（用於熄火通知）"""
        elapsed_time = self._format_elapsed_time()
        return {
            'elapsed_time': elapsed_time,
            'trip_distance': self.trip_distance,
            'avg_fuel': self.avg_fuel
        }
    
    def refresh_theme(self):
        """重新整理 UI 主題顏色（更換強調色後呼叫）"""
        saved_trip_distance = self.trip_distance
        saved_instant_fuel = self.instant_fuel
        saved_avg_fuel = self.avg_fuel
        saved_start_time = self.start_time
        saved_has_valid_data = self.has_valid_data
        saved_total_fuel_used = self.total_fuel_used
        saved_total_distance = self.total_distance
        
        layout = self.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 25, 30, 25)
        main_layout.setSpacing(15)
        
        title_label = QLabel("本次行程")
        title_label.setStyleSheet(f"""
            color: {T('PRIMARY')};
            font-size: 28px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        content_layout = QGridLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(20)
        
        self.elapsed_time_panel, self.elapsed_time_label = self._create_value_panel(
            "運行時間",
            "00:00",
            "",
            "#4ecdc4"
        )
        content_layout.addWidget(self.elapsed_time_panel, 0, 0)
        
        self.distance_panel, self.distance_label = self._create_value_panel(
            "行駛距離",
            "0.0",
            "km",
            "#f39c12"
        )
        content_layout.addWidget(self.distance_panel, 0, 1)
        
        self.instant_fuel_panel, self.instant_fuel_label = self._create_value_panel(
            "瞬時油耗",
            "--",
            "L/100km",
            "#e74c3c"
        )
        content_layout.addWidget(self.instant_fuel_panel, 1, 0)
        
        self.avg_fuel_panel, self.avg_fuel_label = self._create_value_panel(
            "平均油耗",
            "--",
            "L/100km",
            "#2ecc71"
        )
        content_layout.addWidget(self.avg_fuel_panel, 1, 1)
        
        main_layout.addWidget(content_widget, 1)
        
        self.start_time = saved_start_time
        self.trip_distance = saved_trip_distance
        self.instant_fuel = saved_instant_fuel
        self.avg_fuel = saved_avg_fuel
        self.has_valid_data = saved_has_valid_data
        self.total_fuel_used = saved_total_fuel_used
        self.total_distance = saved_total_distance



class OdometerCardWide(QWidget):
    """總里程表卡片（寬版 800x380）- 顯示模式 / 輸入模式切換"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(800, 380)
        
        # 設置背景樣式
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a25, stop:1 #0f0f18);
                border-radius: 20px;
            }
        """)
        
        # 持久化存儲
        self.storage = OdometerStorage()
        
        # 總里程數據（從存儲載入）
        self.total_distance = self.storage.get_odo()
        self.last_sync_time = None
        
        # 輸入狀態
        self.current_input = ""
        self.is_editing = False
        
        # 主佈局使用 StackedWidget 切換模式
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        
        # === 頁面 1: 顯示模式 ===
        self.display_page = self._create_display_page()
        self.stack.addWidget(self.display_page)
        
        # === 頁面 2: 輸入模式（虛擬鍵盤）===
        self.input_page = self._create_input_page()
        self.stack.addWidget(self.input_page)
        
        # 預設顯示模式
        self.stack.setCurrentWidget(self.display_page)
        
        # 初始化顯示（載入的值）
        self.odo_distance_label.setText(f"{int(self.total_distance)}")
    
    def _create_display_page(self):
        """創建顯示頁面 - 水平佈局"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(40)
        
        # === 左側：圖示 ===
        icon_container = QWidget()
        icon_container.setFixedWidth(100)
        icon_container.setStyleSheet("background: transparent;")
        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        
        icon_label = QLabel("🚗")
        icon_label.setStyleSheet("font-size: 48px; background: transparent;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_layout.addStretch()
        icon_layout.addWidget(icon_label)
        icon_layout.addStretch()
        
        # === 中央：里程顯示 ===
        center_container = QWidget()
        center_container.setStyleSheet("background: transparent;")
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)
        
        # 標題
        title_label = QLabel("Odometer")
        title_label.setStyleSheet(f"""
            color: {T('PRIMARY')};
            font-size: 28px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 里程數字 + 單位
        distance_widget = QWidget()
        distance_widget.setStyleSheet("""
            background: rgba(30, 30, 40, 0.5);
            border-radius: 15px;
            border: 2px solid #2a2a35;
        """)
        distance_layout = QHBoxLayout(distance_widget)
        distance_layout.setContentsMargins(20, 20, 20, 20)
        distance_layout.setSpacing(8)
        
        self.odo_distance_label = QLabel("0")
        self.odo_distance_label.setStyleSheet(f"""
            color: {T('TEXT_PRIMARY')};
            font-size: 56px;
            font-weight: bold;
            background: transparent;
        """)
        self.odo_distance_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        unit_label = QLabel("km")
        unit_label.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 24px;
            background: transparent;
        """)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        
        distance_layout.addStretch()
        distance_layout.addWidget(self.odo_distance_label)
        distance_layout.addWidget(unit_label)
        distance_layout.addStretch()
        
        # 同步時間
        self.sync_time_label = QLabel("未同步")
        self.sync_time_label.setStyleSheet(f"""
            color: {T('TEXT_DISABLED')};
            font-size: 16px;
            background: transparent;
        """)
        self.sync_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        center_layout.addStretch()
        center_layout.addWidget(title_label)
        center_layout.addSpacing(10)
        center_layout.addWidget(distance_widget)
        center_layout.addWidget(self.sync_time_label)
        center_layout.addStretch()
        
        # === 右側：同步按鈕 ===
        right_container = QWidget()
        right_container.setFixedWidth(120)
        right_container.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        sync_btn = QPushButton("同步\n里程")
        sync_btn.setFixedSize(90, 90)
        sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sync_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(100, 150, 255, 0.2);
                color: {T('PRIMARY')};
                border: 3px solid {T('PRIMARY')};
                border-radius: 45px;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(100, 150, 255, 0.4);
            }}
            QPushButton:pressed {{
                background-color: rgba(100, 150, 255, 0.6);
            }}
        """)
        sync_btn.clicked.connect(self._show_keypad)
        
        right_layout.addStretch()
        right_layout.addWidget(sync_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        right_layout.addStretch()
        
        # 組合佈局
        layout.addWidget(icon_container)
        layout.addWidget(center_container, 1)
        layout.addWidget(right_container)
        
        return page
    
    def _create_input_page(self):
        """創建輸入頁面（虛擬鍵盤）- 左右並排"""
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(page)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(30)
        
        # === 左側：當前里程 + 輸入預覽 ===
        left_panel = QWidget()
        left_panel.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(15)
        
        # 標題
        title_label = QLabel("同步里程")
        title_label.setStyleSheet(f"""
            color: {T('PRIMARY')};
            font-size: 28px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 當前里程顯示
        current_container = QWidget()
        current_container.setStyleSheet("""
            QWidget {
                background: rgba(30, 30, 40, 0.5);
                border-radius: 15px;
                border: 2px solid #2a2a35;
            }
        """)
        current_layout = QVBoxLayout(current_container)
        current_layout.setContentsMargins(20, 20, 20, 20)
        current_layout.setSpacing(10)
        
        current_title = QLabel("目前里程")
        current_title.setStyleSheet(f"color: {T('TEXT_SECONDARY')}; font-size: 16px; background: transparent;")
        current_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.current_odo_label = QLabel("0 km")
        self.current_odo_label.setStyleSheet(f"""
            color: {T('TEXT_DISABLED')};
            font-size: 36px;
            font-weight: bold;
            background: transparent;
        """)
        self.current_odo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        current_layout.addWidget(current_title)
        current_layout.addWidget(self.current_odo_label)
        
        # 新里程輸入預覽
        new_container = QWidget()
        new_container.setStyleSheet(f"""
            QWidget {{
                background: rgba(100, 150, 255, 0.1);
                border-radius: 15px;
                border: 2px solid {T('PRIMARY')};
            }}
        """)
        new_layout = QVBoxLayout(new_container)
        new_layout.setContentsMargins(20, 20, 20, 20)
        new_layout.setSpacing(10)
        
        new_title = QLabel("新里程")
        new_title.setStyleSheet(f"color: {T('PRIMARY')}; font-size: 16px; background: transparent;")
        new_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.input_display = QLabel("_ _ _ _ _ _")
        self.input_display.setStyleSheet(f"""
            color: {T('TEXT_PRIMARY')};
            font-size: 42px;
            font-weight: bold;
            background: transparent;
        """)
        self.input_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        new_layout.addWidget(new_title)
        new_layout.addWidget(self.input_display)
        
        left_layout.addWidget(title_label)
        left_layout.addWidget(current_container, 1)
        left_layout.addWidget(new_container, 1)
        
        # 中央分隔線
        separator = QWidget()
        separator.setFixedWidth(2)
        separator.setStyleSheet("background: #333;")
        
        # === 右側：虛擬鍵盤 ===
        right_panel = QWidget()
        right_panel.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(10)
        
        # 按鈕網格
        button_grid = QGridLayout()
        button_grid.setSpacing(10)
        
        # 數字按鈕 1-9
        for i in range(9):
            btn = self._create_number_button(str(i + 1))
            row = i // 3
            col = i % 3
            button_grid.addWidget(btn, row, col)
        
        # 第四行：清除, 0, 退格
        btn_clear = self._create_function_button("C", self._clear_input, "#cc5555")
        button_grid.addWidget(btn_clear, 3, 0)
        
        btn_0 = self._create_number_button("0")
        button_grid.addWidget(btn_0, 3, 1)
        
        btn_bs = self._create_function_button("⌫", self._backspace, "#555555")
        button_grid.addWidget(btn_bs, 3, 2)
        
        # 操作按鈕行
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(50)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: #555;
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #666; }}
            QPushButton:pressed {{ background-color: #444; }}
        """)
        btn_cancel.clicked.connect(self._cancel_input)
        
        btn_ok = QPushButton("確定")
        btn_ok.setFixedHeight(50)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(f"""
            QPushButton {{
                background-color: #55aa55;
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #66bb66; }}
            QPushButton:pressed {{ background-color: #449944; }}
        """)
        btn_ok.clicked.connect(self._confirm_input)
        
        action_layout.addWidget(btn_cancel)
        action_layout.addWidget(btn_ok)
        
        right_layout.addLayout(button_grid)
        right_layout.addLayout(action_layout)
        
        layout.addWidget(left_panel, 1)
        layout.addWidget(separator)
        layout.addWidget(right_panel, 1)
        
        return page
    
    def _create_number_button(self, text):
        """創建數字按鈕"""
        btn = QPushButton(text)
        btn.setFixedSize(95, 55)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #3a3a45;
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: 10px;
                font-size: 26px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #4a4a55; }}
            QPushButton:pressed {{ background-color: #2a2a35; }}
        """)
        btn.clicked.connect(lambda: self._append_digit(text))
        return btn
    
    def _create_function_button(self, text, callback, color="#6a5acd"):
        """創建功能按鈕"""
        btn = QPushButton(text)
        btn.setFixedSize(95, 55)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: {T('TEXT_PRIMARY')};
                border: none;
                border-radius: 10px;
                font-size: 22px;
                font-weight: bold;
            }}
            QPushButton:hover {{ opacity: 0.8; }}
            QPushButton:pressed {{ opacity: 0.6; }}
        """)
        btn.clicked.connect(callback)
        return btn
    
    def _show_keypad(self):
        """顯示虛擬鍵盤"""
        self.current_input = ""
        self.current_odo_label.setText(f"{int(self.total_distance)} km")
        self._update_input_display()
        self.is_editing = True
        self.stack.setCurrentWidget(self.input_page)
        
        # 通知 Dashboard 禁用滑動
        dashboard = self._get_dashboard()
        if dashboard:
            dashboard.set_swipe_enabled(False)
    
    def _hide_keypad(self):
        """隱藏虛擬鍵盤"""
        self.is_editing = False
        self.stack.setCurrentWidget(self.display_page)
        
        # 通知 Dashboard 恢復滑動
        dashboard = self._get_dashboard()
        if dashboard:
            dashboard.set_swipe_enabled(True)
    
    def _append_digit(self, digit):
        """追加數字"""
        if len(self.current_input) < 7:
            self.current_input += digit
            self._update_input_display()
    
    def _backspace(self):
        """刪除最後一位"""
        if self.current_input:
            self.current_input = self.current_input[:-1]
            self._update_input_display()
    
    def _clear_input(self):
        """清除輸入"""
        self.current_input = ""
        self._update_input_display()
    
    def _update_input_display(self):
        """更新輸入顯示"""
        if self.current_input:
            self.input_display.setText(f"{self.current_input} km")
        else:
            self.input_display.setText("_ _ _ _ _ _")
    
    def _confirm_input(self):
        """確認輸入"""
        if self.current_input:
            try:
                self.total_distance = float(self.current_input)
            except ValueError:
                self.total_distance = 0.0
            
            self.odo_distance_label.setText(f"{int(self.total_distance)}")
            self.last_sync_time = time.time()
            self._update_sync_time_display()
            
            # 儲存到儲存系統
            self.storage.update_odo(self.total_distance)
            self.storage.save_now()  # 立即儲存，確保手動修改不會丟失
            
            print(f"里程表已同步: {int(self.total_distance)} km")
        
        self._hide_keypad()
    
    def _cancel_input(self):
        """取消輸入"""
        self._hide_keypad()
    
    def _get_dashboard(self):
        """獲取 Dashboard 實例"""
        Dashboard = get_dashboard_class()
        parent = self.parent()
        while parent:
            if isinstance(parent, Dashboard):
                return parent
            parent = parent.parent()
        return None
    
    def add_distance(self, distance_km):
        """由 Dashboard 物理心跳呼叫，累加里程"""
        self.total_distance += distance_km
        self.odo_distance_label.setText(f"{int(self.total_distance)}")
        # 每累加一次就儲存（實際上 Dashboard 每秒呼叫一次）
        self.storage.update_odo(self.total_distance)
    
    def _update_sync_time_display(self):
        """更新同步時間顯示"""
        from datetime import datetime
        
        if self.last_sync_time:
            sync_dt = datetime.fromtimestamp(self.last_sync_time)
            time_str = sync_dt.strftime("%Y-%m-%d %H:%M")
            self.sync_time_label.setText(f"同步: {time_str}")
        else:
            self.sync_time_label.setText("未同步")
    
    def refresh_theme(self):
        """重新整理 UI 主題顏色（更換強調色後呼叫）"""
        saved_distance = self.total_distance
        saved_input = self.current_input
        saved_editing = self.is_editing
        saved_sync_time = self.last_sync_time
        
        main_layout = self.layout()
        while main_layout.count():
            item = main_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)
        
        self.display_page = self._create_display_page()
        self.stack.addWidget(self.display_page)
        
        self.input_page = self._create_input_page()
        self.stack.addWidget(self.input_page)
        
        self.total_distance = saved_distance
        self.current_input = saved_input
        self.is_editing = saved_editing
        self.last_sync_time = saved_sync_time
        
        self.odo_distance_label.setText(f"{int(self.total_distance)}")
        self._update_sync_time_display()
        
        if self.is_editing:
            self.stack.setCurrentWidget(self.input_page)
        else:
            self.stack.setCurrentWidget(self.display_page)



class TripCard(QWidget):
    """Trip 里程卡片 - 顯示 Trip 1 和 Trip 2 的里程數、reset按鈕和reset時間"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(380, 380)
        
        # 設置背景樣式
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a25, stop:1 #0f0f18);
                border-radius: 20px;
            }
        """)
        
        # Trip 數據
        self.trip1_distance = 0.0  # km
        self.trip2_distance = 0.0  # km
        self.trip1_reset_time = None
        self.trip2_reset_time = None
        
        # 當前速度（由 Dashboard 物理心跳驅動里程計算）
        self.current_speed = 0.0
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 標題
        title_label = QLabel("Trip Computer")
        title_label.setStyleSheet(f"""
            color: {T('PRIMARY')};
            font-size: 18px;
            font-weight: bold;
            background: transparent;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # === Trip 1 區域 ===
        trip1_container = self.create_trip_widget(
            "Trip 1", 
            is_trip1=True
        )
        
        # === Trip 2 區域 ===
        trip2_container = self.create_trip_widget(
            "Trip 2", 
            is_trip1=False
        )
        
        # 組合佈局
        layout.addWidget(title_label)
        layout.addSpacing(10)
        layout.addWidget(trip1_container)
        layout.addSpacing(5)
        layout.addWidget(trip2_container)
        layout.addStretch()
    
    def create_trip_widget(self, title, is_trip1=True):
        """創建單個Trip顯示區域"""
        container = QWidget()
        container.setFixedHeight(140)
        container.setStyleSheet("""
            QWidget {
                background: rgba(30, 30, 40, 0.5);
                border-radius: 15px;
                border: 2px solid #2a2a35;
            }
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(5)
        
        # 標題和Reset按鈕行
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        
        trip_title = QLabel(title)
        trip_title.setStyleSheet(f"""
            color: {T('PRIMARY')};
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        
        reset_btn = QPushButton("Reset")
        reset_btn.setFixedSize(70, 28)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(100, 150, 255, 0.3);
                color: {T('PRIMARY')};
                border: 1px solid {T('PRIMARY')};
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(100, 150, 255, 0.5);
            }}
            QPushButton:pressed {{
                background-color: rgba(100, 150, 255, 0.7);
            }}
        """)
        
        if is_trip1:
            reset_btn.clicked.connect(self.reset_trip1)
        else:
            reset_btn.clicked.connect(self.reset_trip2)
        
        header_layout.addWidget(trip_title)
        header_layout.addStretch()
        header_layout.addWidget(reset_btn)
        
        # 里程顯示
        distance_layout = QHBoxLayout()
        distance_layout.setSpacing(5)
        
        if is_trip1:
            self.trip1_distance_label = QLabel("0.0")
            distance_label = self.trip1_distance_label
        else:
            self.trip2_distance_label = QLabel("0.0")
            distance_label = self.trip2_distance_label
            
        distance_label.setStyleSheet(f"""
            color: {T('TEXT_PRIMARY')};
            font-size: 48px;
            font-weight: bold;
            background: transparent;
        """)
        distance_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        unit_label = QLabel("km")
        unit_label.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 20px;
            background: transparent;
        """)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        
        distance_layout.addStretch()
        distance_layout.addWidget(distance_label)
        distance_layout.addWidget(unit_label)
        distance_layout.addSpacing(10)
        
        # Reset時間顯示
        if is_trip1:
            self.trip1_reset_label = QLabel("Never reset")
            reset_time_label = self.trip1_reset_label
        else:
            self.trip2_reset_label = QLabel("Never reset")
            reset_time_label = self.trip2_reset_label
            
        reset_time_label.setStyleSheet(f"""
            color: {T('TEXT_DISABLED')};
            font-size: 24px;
            background: transparent;
        """)
        reset_time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        # 組合佈局
        layout.addLayout(header_layout)
        layout.addSpacing(5)
        layout.addLayout(distance_layout)
        layout.addWidget(reset_time_label)
        
        return container
    
    def add_distance(self, distance_km):
        """由 Dashboard 物理心跳呼叫，累加里程"""
        self.trip1_distance += distance_km
        self.trip2_distance += distance_km
        
        # 更新顯示
        self.trip1_distance_label.setText(f"{self.trip1_distance:.1f}")
        self.trip2_distance_label.setText(f"{self.trip2_distance:.1f}")
    
    def reset_trip1(self):
        """重置 Trip 1"""
        self.trip1_distance = 0.0
        self.trip1_distance_label.setText("0.0")
        self.trip1_reset_time = time.time()
        self.update_reset_time_display(True)
        print("Trip 1 已重置")
    
    def reset_trip2(self):
        """重置 Trip 2"""
        self.trip2_distance = 0.0
        self.trip2_distance_label.setText("0.0")
        self.trip2_reset_time = time.time()
        self.update_reset_time_display(False)
        print("Trip 2 已重置")
    
    def update_reset_time_display(self, is_trip1=True):
        """更新reset時間顯示"""
        from datetime import datetime
        
        if is_trip1:
            if self.trip1_reset_time:
                reset_dt = datetime.fromtimestamp(self.trip1_reset_time)
                time_str = reset_dt.strftime("%Y-%m-%d %H:%M")
                self.trip1_reset_label.setText(f"Reset: {time_str}")
            else:
                self.trip1_reset_label.setText("Never reset")
        else:
            if self.trip2_reset_time:
                reset_dt = datetime.fromtimestamp(self.trip2_reset_time)
                time_str = reset_dt.strftime("%Y-%m-%d %H:%M")
                self.trip2_reset_label.setText(f"Reset: {time_str}")
            else:
                self.trip2_reset_label.setText("Never reset")



class TripCardWide(QWidget):
    """Trip 里程卡片（寬版 800x380）- 左右並排顯示 Trip 1 和 Trip 2，支援焦點選擇"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(800, 380)
        
        # 設置背景樣式
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a1a25, stop:1 #0f0f18);
                border-radius: 20px;
            }
        """)
        
        # 持久化存儲
        self.storage = OdometerStorage()
        
        # Trip 數據（從存儲載入）
        self.trip1_distance, self.trip1_reset_time = self.storage.get_trip1()
        self.trip2_distance, self.trip2_reset_time = self.storage.get_trip2()
        
        # 焦點狀態：0=無焦點, 1=Trip1, 2=Trip2
        self.focus_index = 0
        
        # Main layout - 水平排列
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(30)
        
        # === 左側 Trip 1 ===
        self.trip1_panel = self._create_trip_panel("Trip 1", is_trip1=True)
        
        # 中央分隔線
        separator = QWidget()
        separator.setFixedWidth(2)
        separator.setStyleSheet("background: #333;")
        
        # === 右側 Trip 2 ===
        self.trip2_panel = self._create_trip_panel("Trip 2", is_trip1=False)
        
        main_layout.addWidget(self.trip1_panel, 1)
        main_layout.addWidget(separator)
        main_layout.addWidget(self.trip2_panel, 1)
        
        # 初始化顯示（載入的值）
        self.trip1_distance_label.setText(f"{self.trip1_distance:.1f}")
        self.trip2_distance_label.setText(f"{self.trip2_distance:.1f}")
        self._update_reset_time_display(True)
        self._update_reset_time_display(False)
    
    def _create_trip_panel(self, title, is_trip1=True):
        """創建單個 Trip 面板"""
        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # 標題行（標題 + Reset 按鈕）
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            color: {T('PRIMARY')};
            font-size: 28px;
            font-weight: bold;
            background: transparent;
        """)
        
        reset_btn = QPushButton("Reset")
        reset_btn.setFixedSize(80, 36)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(100, 150, 255, 0.3);
                color: {T('PRIMARY')};
                border: 1px solid {T('PRIMARY')};
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(100, 150, 255, 0.5);
            }}
            QPushButton:pressed {{
                background-color: rgba(100, 150, 255, 0.7);
            }}
        """)
        
        if is_trip1:
            reset_btn.clicked.connect(self.reset_trip1)
        else:
            reset_btn.clicked.connect(self.reset_trip2)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(reset_btn)
        
        # 里程顯示區域（作為焦點容器）
        distance_container = QWidget()
        if is_trip1:
            self.trip1_container = distance_container
        else:
            self.trip2_container = distance_container
        distance_container.setStyleSheet("""
            background: rgba(30, 30, 40, 0.5);
            border-radius: 15px;
            border: 2px solid #2a2a35;
        """)
        distance_layout = QVBoxLayout(distance_container)
        distance_layout.setContentsMargins(20, 25, 20, 25)
        distance_layout.setSpacing(10)
        
        # 里程數字 + 單位
        value_layout = QHBoxLayout()
        value_layout.setSpacing(8)
        
        if is_trip1:
            self.trip1_distance_label = QLabel("0.0")
            distance_label = self.trip1_distance_label
        else:
            self.trip2_distance_label = QLabel("0.0")
            distance_label = self.trip2_distance_label
        
        distance_label.setStyleSheet(f"""
            color: {T('TEXT_PRIMARY')};
            font-size: 72px;
            font-weight: bold;
            background: transparent;
        """)
        distance_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        unit_label = QLabel("km")
        unit_label.setStyleSheet(f"""
            color: {T('TEXT_SECONDARY')};
            font-size: 28px;
            background: transparent;
        """)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        
        value_layout.addStretch()
        value_layout.addWidget(distance_label)
        value_layout.addWidget(unit_label)
        value_layout.addSpacing(10)
        
        # Reset 時間
        if is_trip1:
            self.trip1_reset_label = QLabel("Never reset")
            reset_time_label = self.trip1_reset_label
        else:
            self.trip2_reset_label = QLabel("Never reset")
            reset_time_label = self.trip2_reset_label
        
        reset_time_label.setStyleSheet(f"""
            color: {T('TEXT_DISABLED')};
            font-size: 24px;
            background: transparent;
        """)
        reset_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        distance_layout.addLayout(value_layout)
        distance_layout.addWidget(reset_time_label)
        
        # 組合佈局
        layout.addLayout(header_layout)
        layout.addWidget(distance_container, 1)
        
        return panel
    
    def add_distance(self, distance_km):
        """由 Dashboard 物理心跳呼叫，累加里程"""
        self.trip1_distance += distance_km
        self.trip2_distance += distance_km
        
        # 更新顯示
        self.trip1_distance_label.setText(f"{self.trip1_distance:.1f}")
        self.trip2_distance_label.setText(f"{self.trip2_distance:.1f}")
        
        # 儲存到檔案
        self.storage.update_trip1(self.trip1_distance)
        self.storage.update_trip2(self.trip2_distance)
    
    def reset_trip1(self):
        """重置 Trip 1"""
        self.trip1_distance = 0.0
        self.trip1_distance_label.setText("0.0")
        self.trip1_reset_time = time.time()
        self._update_reset_time_display(True)
        # 儲存到檔案（包含 reset 時間）
        self.storage.update_trip1(self.trip1_distance, self.trip1_reset_time)
        print("Trip 1 已重置")
    
    def reset_trip2(self):
        """重置 Trip 2"""
        self.trip2_distance = 0.0
        self.trip2_distance_label.setText("0.0")
        self.trip2_reset_time = time.time()
        self._update_reset_time_display(False)
        # 儲存到檔案（包含 reset 時間）
        self.storage.update_trip2(self.trip2_distance, self.trip2_reset_time)
        print("Trip 2 已重置")
    
    def _update_reset_time_display(self, is_trip1=True):
        """更新 reset 時間顯示"""
        from datetime import datetime
        
        if is_trip1:
            if self.trip1_reset_time:
                reset_dt = datetime.fromtimestamp(self.trip1_reset_time)
                time_str = reset_dt.strftime("%Y-%m-%d %H:%M")
                self.trip1_reset_label.setText(f"Reset: {time_str}")
            else:
                self.trip1_reset_label.setText("Never reset")
        else:
            if self.trip2_reset_time:
                reset_dt = datetime.fromtimestamp(self.trip2_reset_time)
                time_str = reset_dt.strftime("%Y-%m-%d %H:%M")
                self.trip2_reset_label.setText(f"Reset: {time_str}")
            else:
                self.trip2_reset_label.setText("Never reset")
    
    def set_focus(self, focus_index):
        """
        設置焦點狀態
        
        Args:
            focus_index: 0=無焦點, 1=Trip1有焦點, 2=Trip2有焦點
        """
        self.focus_index = focus_index
        self._update_focus_style()
    
    def get_focus(self):
        """獲取當前焦點狀態"""
        return self.focus_index
    
    def next_focus(self):
        """
        切換到下一個焦點
        
        Returns:
            bool: True=還在 Trip 卡片內, False=應該離開到下一張卡片
        """
        if self.focus_index == 0:
            # 無焦點 -> Trip 1
            self.focus_index = 1
            self._update_focus_style()
            return True
        elif self.focus_index == 1:
            # Trip 1 -> Trip 2
            self.focus_index = 2
            self._update_focus_style()
            return True
        else:
            # Trip 2 -> 離開（清除焦點）
            self.focus_index = 0
            self._update_focus_style()
            return False
    
    def clear_focus(self):
        """清除焦點"""
        self.focus_index = 0
        self._update_focus_style()
    
    def reset_focused_trip(self):
        """
        重置當前有焦點的 Trip
        
        Returns:
            bool: True=成功重置, False=沒有焦點
        """
        if self.focus_index == 1:
            self.reset_trip1()
            return True
        elif self.focus_index == 2:
            self.reset_trip2()
            return True
        return False
    
    def _update_focus_style(self):
        """更新焦點視覺樣式"""
        # Trip 1 容器樣式
        if self.focus_index == 1:
            self.trip1_container.setStyleSheet("""
                background: rgba(100, 170, 255, 0.15);
                border-radius: 15px;
                border: 3px solid #6af;
            """)
        else:
            self.trip1_container.setStyleSheet("""
                background: rgba(30, 30, 40, 0.5);
                border-radius: 15px;
                border: 2px solid #2a2a35;
            """)
        
        # Trip 2 容器樣式
        if self.focus_index == 2:
            self.trip2_container.setStyleSheet("""
                background: rgba(100, 170, 255, 0.15);
                border-radius: 15px;
                border: 3px solid #6af;
            """)
        else:
            self.trip2_container.setStyleSheet("""
                background: rgba(30, 30, 40, 0.5);
                border-radius: 15px;
                border: 2px solid #2a2a35;
            """)
    
    def refresh_theme(self):
        """重新整理 UI 主題顏色（更換強調色後呼叫）"""
        saved_trip1_dist = self.trip1_distance
        saved_trip1_time = self.trip1_reset_time
        saved_trip2_dist = self.trip2_distance
        saved_trip2_time = self.trip2_reset_time
        saved_focus = self.focus_index
        
        layout = self.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.trip1_panel = self._create_trip_panel("Trip 1", is_trip1=True)
        self.trip2_panel = self._create_trip_panel("Trip 2", is_trip1=False)
        
        separator = QWidget()
        separator.setFixedWidth(2)
        separator.setStyleSheet("background: #333;")
        
        layout.addWidget(self.trip1_panel, 1)
        layout.addWidget(separator)
        layout.addWidget(self.trip2_panel, 1)
        
        self.trip1_distance = saved_trip1_dist
        self.trip1_reset_time = saved_trip1_time
        self.trip2_distance = saved_trip2_dist
        self.trip2_reset_time = saved_trip2_time
        
        self.trip1_distance_label.setText(f"{self.trip1_distance:.1f}")
        self.trip2_distance_label.setText(f"{self.trip2_distance:.1f}")
        self._update_reset_time_display(True)
        self._update_reset_time_display(False)
        
        self.focus_index = saved_focus
        self._update_focus_style()



