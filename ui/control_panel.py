# Auto-extracted from main.py
import os
import time
import platform
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

class TurnSignalBar(QWidget):
    """方向燈漸層條 - 使用 QPainter 繪製，避免 CSS 效能問題
    
    這個 Widget 取代了原本使用 setStyleSheet 動態更新的 QWidget，
    使用 QPainter 直接繪製漸層，大幅降低 CPU 負擔。
    """
    
    def __init__(self, direction: str = "left", parent=None):
        """
        Args:
            direction: "left" 或 "right"，決定漸層方向
        """
        super().__init__(parent)
        self.direction = direction
        self.gradient_pos = 0.0  # 0.0 (熄滅) 到 1.0 (全亮)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        # 預先建立顏色，避免每次 paintEvent 都重新建立
        self._color_bright = QColor(177, 255, 0)
        self._color_mid = QColor(140, 255, 0)
        self._color_dim = QColor(120, 255, 0)
        self._color_dark = QColor(30, 30, 30)
    
    def set_gradient_pos(self, pos: float):
        """設定漸層位置並觸發重繪
        Args:
            pos: 0.0 到 1.0
        """
        if self.gradient_pos != pos:
            self.gradient_pos = max(0.0, min(1.0, pos))
            self.update()  # 觸發 paintEvent
    
    def paintEvent(self, event):
        """使用 QPainter 繪製漸層效果"""
        if self.gradient_pos <= 0:
            return  # 完全熄滅，不繪製任何東西
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        pos = self.gradient_pos
        
        # 建立漸層
        if self.direction == "left":
            # 左轉燈：從左邊（亮）到右邊（暗）
            gradient = QLinearGradient(0, 0, w, 0)
        else:
            # 右轉燈：從右邊（亮）到左邊（暗）
            gradient = QLinearGradient(w, 0, 0, 0)
        
        if pos >= 1.0:
            # 完全亮起：整條均勻亮色
            self._color_bright.setAlphaF(0.7)
            gradient.setColorAt(0, self._color_bright)
            gradient.setColorAt(1, self._color_bright)
        else:
            # 熄滅中：從邊緣向中間漸暗
            self._color_bright.setAlphaF(pos * 0.7)
            self._color_mid.setAlphaF(pos * 0.5)
            self._color_dim.setAlphaF(pos * 0.3)
            self._color_dark.setAlphaF(0.1)
            
            gradient.setColorAt(0, self._color_bright)
            gradient.setColorAt(0.3 * pos, self._color_bright)
            gradient.setColorAt(0.5 * pos, self._color_mid)
            gradient.setColorAt(0.7 * pos, self._color_dim)
            gradient.setColorAt(min(0.85 * pos, 0.99), self._color_dim)
            gradient.setColorAt(1, self._color_dark)
        
        # 繪製圓角矩形
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, h, 4, 4)
        
        painter.end()



class ControlPanel(QWidget):
    """下拉控制面板（類似 Android 狀態列）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(1920, 300)
        
        # 設置半透明背景 - 使用 AutoFillBackground
        self.setAutoFillBackground(True)
        
        # WiFi 狀態
        self.wifi_ssid = None
        self.wifi_signal = 0
        self.speed_sync_mode = "calibrated"  # 速度同步初始模式
        
        # 主佈局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)
        
        # 標題列
        title_layout = QHBoxLayout()
        title_label = QLabel("快速設定")
        title_label.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: bold;
            background: transparent;
        """)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        # 關閉按鈕
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(40, 40)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
                border-radius: 20px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.3);
            }
        """)
        close_btn.clicked.connect(self.hide_panel)
        title_layout.addWidget(close_btn)
        
        layout.addLayout(title_layout)
        
        # === 內容區域：左側快捷按鈕 + 右側系統狀態 ===
        content_layout = QHBoxLayout()
        content_layout.setSpacing(30)
        
        # === 左側：快捷按鈕 ===
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        
        self.buttons = []
        self.button_widgets = {}  # 用於存取特定按鈕
        # 三段速度模式：校正 / 固定1.05 / OBD+GPS
        self.speed_sync_modes = ["calibrated", "fixed", "gps"]
        self.speed_sync_mode_index = 0
        self.speed_sync_mode = self.speed_sync_modes[self.speed_sync_mode_index]
        button_configs = [
            ("WiFi", "📶", "#1DB954"),
            ("時間", "🕐", "#4285F4"),
            ("亮度", "☀", "#FF9800"),
            ("更新", "🔄", "#00BCD4"),
            ("電源", "🔌", "#E91E63"),
            ("設定", "⚙", "#9C27B0")
        ]
        
        for title, icon, color in button_configs:
            btn = self.create_control_button(title, icon, color)
            self.buttons.append(btn)
            self.button_widgets[title] = btn
            button_layout.addWidget(btn)

        # 速度同步（三段模式）
        speed_sync_btn = self.create_speed_sync_button()
        self.buttons.append(speed_sync_btn)
        self.button_widgets["速度同步"] = speed_sync_btn
        button_layout.addWidget(speed_sync_btn)
        
        content_layout.addLayout(button_layout)
        content_layout.addStretch()
        
        # === 右側：系統狀態資訊（水平排列兩個卡片）===
        status_layout = QHBoxLayout()
        status_layout.setSpacing(20)
        
        # WiFi 狀態卡片
        wifi_card = QWidget()
        wifi_card.setFixedSize(280, 80)
        wifi_card.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
        """)
        wifi_card_layout = QHBoxLayout(wifi_card)
        wifi_card_layout.setContentsMargins(15, 10, 15, 10)
        wifi_card_layout.setSpacing(12)
        
        # WiFi 圖示
        wifi_icon = QLabel("📶")
        wifi_icon.setFixedSize(40, 40)
        wifi_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wifi_icon.setStyleSheet("font-size: 28px; background: transparent;")
        wifi_card_layout.addWidget(wifi_icon)
        
        # WiFi 資訊
        wifi_info_layout = QVBoxLayout()
        wifi_info_layout.setSpacing(2)
        wifi_info_layout.setContentsMargins(0, 0, 0, 0)
        
        self.wifi_status_label = QLabel("檢查中...")
        self.wifi_status_label.setStyleSheet("""
            color: white;
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        
        self.wifi_detail_label = QLabel("取得連線資訊")
        self.wifi_detail_label.setStyleSheet("""
            color: #aaa;
            font-size: 12px;
            background: transparent;
        """)
        
        wifi_info_layout.addWidget(self.wifi_status_label)
        wifi_info_layout.addWidget(self.wifi_detail_label)
        wifi_card_layout.addLayout(wifi_info_layout)
        wifi_card_layout.addStretch()
        
        # WiFi 信號強度指示
        self.wifi_signal_label = QLabel("")
        self.wifi_signal_label.setStyleSheet("""
            color: #6f6;
            font-size: 18px;
            font-weight: bold;
            background: transparent;
        """)
        wifi_card_layout.addWidget(self.wifi_signal_label)
        
        status_layout.addWidget(wifi_card)
        
        # 日期時間卡片
        datetime_card = QWidget()
        datetime_card.setFixedSize(220, 80)
        datetime_card.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
        """)
        datetime_card_layout = QHBoxLayout(datetime_card)
        datetime_card_layout.setContentsMargins(15, 10, 15, 10)
        datetime_card_layout.setSpacing(12)
        
        # 日曆圖示
        calendar_icon = QLabel("📅")
        calendar_icon.setFixedSize(40, 40)
        calendar_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        calendar_icon.setStyleSheet("font-size: 28px; background: transparent;")
        datetime_card_layout.addWidget(calendar_icon)
        
        # 日期時間資訊
        datetime_info_layout = QVBoxLayout()
        datetime_info_layout.setSpacing(2)
        datetime_info_layout.setContentsMargins(0, 0, 0, 0)
        
        self.date_label = QLabel("")
        self.date_label.setStyleSheet("""
            color: white;
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        
        self.weekday_label = QLabel("")
        self.weekday_label.setStyleSheet("""
            color: #aaa;
            font-size: 12px;
            background: transparent;
        """)
        
        datetime_info_layout.addWidget(self.date_label)
        datetime_info_layout.addWidget(self.weekday_label)
        datetime_card_layout.addLayout(datetime_info_layout)
        datetime_card_layout.addStretch()
        
        status_layout.addWidget(datetime_card)
        
        content_layout.addLayout(status_layout)
        
        layout.addLayout(content_layout)
        layout.addStretch()
        
        # 隱藏指示
        hint_label = QLabel("向上滑動以關閉")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet("""
            color: #888;
            font-size: 14px;
            background: transparent;
        """)
        layout.addWidget(hint_label)
        
        # 啟動狀態更新定時器
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status_info)
        self.status_timer.start(5000)  # 每5秒更新
        
        # 立即更新一次
        QTimer.singleShot(100, self.update_status_info)
        
    def update_status_info(self):
        """更新狀態資訊"""
        from datetime import datetime
        
        # 更新日期時間
        now = datetime.now()
        self.date_label.setText(now.strftime("%Y年%m月%d日"))
        
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        self.weekday_label.setText(weekday_names[now.weekday()])
        
        # 更新 WiFi 狀態
        self.update_wifi_status()
    
    def update_wifi_status(self):
        """更新 WiFi 狀態 - 使用 /proc/net/wireless + iw（輕量快速）"""
        import random
        
        # 檢查是否在 Linux 環境
        if platform.system() != 'Linux':
            # macOS/Windows: 顯示模擬資料
            dummy_networks = ["Home-WiFi", "Office-5G", "Starbucks_Free", "iPhone 熱點"]
            ssid = random.choice(dummy_networks)
            signal = random.randint(60, 95)
            
            self.wifi_ssid = ssid
            self.wifi_signal = signal
            self.wifi_status_label.setText(ssid)
            
            if signal >= 80:
                signal_text = "信號極佳"
                signal_color = "#6f6"
            elif signal >= 60:
                signal_text = "信號良好"
                signal_color = "#6f6"
            else:
                signal_text = "信號普通"
                signal_color = "#fa0"
            
            self.wifi_detail_label.setText(signal_text)
            self.wifi_signal_label.setText(f"{signal}%")
            self.wifi_signal_label.setStyleSheet(f"""
                color: {signal_color};
                font-size: 18px;
                font-weight: bold;
                background: transparent;
            """)
            return
        
        # Linux: 使用 /proc/net/wireless 讀取信號強度（超快，<1ms）
        try:
            ssid = None
            signal = 0
            interface = None
            
            # 1. 從 /proc/net/wireless 讀取信號強度和介面名稱
            # 格式：Inter-| sta-|   Quality        |   Discarded packets
            #        face | tus | link level noise |  nwid  crypt   frag  retry   misc
            #       wlp6s0: 0000   57.  -53.  -256        0      0      0      0    578
            if os.path.exists('/proc/net/wireless'):
                with open('/proc/net/wireless', 'r') as f:
                    lines = f.readlines()
                    for line in lines[2:]:  # 跳過標題行
                        line = line.strip()
                        if ':' in line:
                            parts = line.split()
                            if len(parts) >= 3:
                                interface = parts[0].rstrip(':')
                                # link quality 通常是 0-70，轉換為百分比
                                try:
                                    link_quality = float(parts[2].rstrip('.'))
                                    signal = min(100, int(link_quality * 100 / 70))
                                except (ValueError, IndexError):
                                    signal = 0
                                break
            
            # 2. 使用 iw 取得 SSID（比 iwgetid 更常見，不會觸發掃描）
            if interface and signal > 0:
                import subprocess
                try:
                    # iw dev <interface> link 可以取得當前連接的 SSID
                    result = subprocess.run(
                        ['iw', 'dev', interface, 'link'],
                        capture_output=True,
                        text=True,
                        timeout=1  # 1秒超時
                    )
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            line = line.strip()
                            if line.startswith('SSID:'):
                                ssid = line[5:].strip()
                                break
                except FileNotFoundError:
                    # iw 不存在，嘗試使用 nmcli（只查詢當前連接，不掃描）
                    try:
                        result = subprocess.run(
                            ['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'],
                            capture_output=True,
                            text=True,
                            timeout=1
                        )
                        if result.returncode == 0:
                            for line in result.stdout.strip().split('\n'):
                                # 格式: 是:SSID 或 yes:SSID
                                if line.startswith('是:') or line.lower().startswith('yes:'):
                                    ssid = line.split(':', 1)[1]
                                    break
                    except Exception:
                        ssid = None
                except Exception:
                    ssid = None
            
            # 3. 更新 UI
            if ssid and signal > 0:
                self.wifi_ssid = ssid
                self.wifi_signal = signal
                self.wifi_status_label.setText(ssid)
                
                if signal >= 80:
                    signal_text = "信號極佳"
                    signal_color = "#6f6"
                elif signal >= 60:
                    signal_text = "信號良好"
                    signal_color = "#6f6"
                elif signal >= 40:
                    signal_text = "信號普通"
                    signal_color = "#fa0"
                else:
                    signal_text = "信號較弱"
                    signal_color = "#f66"
                
                self.wifi_detail_label.setText(signal_text)
                self.wifi_signal_label.setText(f"{signal}%")
                self.wifi_signal_label.setStyleSheet(f"""
                    color: {signal_color};
                    font-size: 16px;
                    font-weight: bold;
                    background: transparent;
                """)
            else:
                # 未連線或無法取得
                self.wifi_ssid = None
                self.wifi_signal = 0
                self.wifi_status_label.setText("未連線")
                self.wifi_detail_label.setText("點擊 WiFi 按鈕進行連線")
                self.wifi_signal_label.setText("")
                self.wifi_detail_label.setStyleSheet("""
                    color: #f66;
                    font-size: 14px;
                    background: transparent;
                """)
                
        except Exception as e:
            self.wifi_status_label.setText("無法取得狀態")
            self.wifi_detail_label.setText(str(e)[:30])
            self.wifi_signal_label.setText("")
        
        # 更新「更新」按鈕狀態 (只在有網路時啟用)
        self._update_update_button_state()
    
    def _update_update_button_state(self):
        """根據網路狀態更新「更新」按鈕"""
        # 檢查父視窗的網路狀態
        parent = self.parent()
        is_online = True
        if parent and hasattr(parent, 'is_offline'):
            is_online = not parent.is_offline
        
        self.set_update_button_enabled(is_online)
        
    def paintEvent(self, a0):  # type: ignore
        """自定義繪製半透明背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 繪製圓角矩形背景（底部圓角）
        rect = self.rect()
        path = QPainterPath()
        radius = 20
        
        # 從左上開始，順時針繪製
        path.moveTo(0, 0)  # 左上
        path.lineTo(rect.width(), 0)  # 右上
        path.lineTo(rect.width(), rect.height() - radius)  # 右側到圓角
        path.arcTo(rect.width() - radius * 2, rect.height() - radius * 2, 
                   radius * 2, radius * 2, 0, -90)  # 右下圓角
        path.lineTo(radius, rect.height())  # 底部
        path.arcTo(0, rect.height() - radius * 2, 
                   radius * 2, radius * 2, -90, -90)  # 左下圓角
        path.closeSubpath()
        
        # 漸層背景
        gradient = QLinearGradient(0, 0, 0, rect.height())
        gradient.setColorAt(0, QColor(42, 42, 53, 220))
        gradient.setColorAt(1, QColor(26, 26, 37, 230))
        
        painter.fillPath(path, QBrush(gradient))
    
    def create_control_button(self, title, icon, color):
        """創建控制按鈕"""
        container = QWidget()
        container.setFixedSize(150, 150)
        container.setCursor(Qt.CursorShape.PointingHandCursor)
        container.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # 按鈕主體
        btn = QPushButton()
        btn.setFixedSize(120, 120)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                border: none;
                border-radius: 20px;
                font-size: 48px;
                color: white;
            }}
            QPushButton:hover {{
                background-color: {self.adjust_color(color, 1.2)};
            }}
            QPushButton:pressed {{
                background-color: {self.adjust_color(color, 0.8)};
            }}
        """)
        btn.setText(icon)
        btn.clicked.connect(lambda checked=False, t=title: self.on_button_clicked(t, checked))
        # 標籤
        label = QLabel(title)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 16px;
                background: transparent;
            }
        """)
        
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        
        return container

    def create_speed_sync_button(self):
        """創建速度同步開關按鈕（反向控制 gps_speed_mode）"""
        container = QWidget()
        container.setFixedSize(150, 150)
        container.setCursor(Qt.CursorShape.PointingHandCursor)
        container.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        btn = QPushButton()
        btn.setFixedSize(120, 120)
        btn.clicked.connect(lambda checked=False: self.on_button_clicked("速度同步", checked))
        
        # 長按檢測（1.5 秒）
        btn._long_press_timer = QTimer()
        btn._long_press_timer.setSingleShot(True)
        btn._long_press_timer.timeout.connect(lambda: self._on_speed_sync_long_press(btn))
        btn._is_long_press = False
        
        def on_pressed():
            btn._is_long_press = False
            btn._long_press_timer.start(1500)  # 1.5 秒長按
        
        def on_released():
            btn._long_press_timer.stop()
        
        btn.pressed.connect(on_pressed)
        btn.released.connect(on_released)

        label = QLabel("速度同步")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 16px;
                background: transparent;
            }
        """)

        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        # 套用預設狀態樣式
        self._apply_speed_sync_style(btn, self.speed_sync_mode)
        return container
    
    def _on_speed_sync_long_press(self, btn):
        """速度同步按鈕長按：切換速度校正模式"""
        btn._is_long_press = True
        
        try:
            import datagrab
            current_enabled = datagrab.is_speed_calibration_enabled()
            current_val = datagrab.get_speed_correction()
        except Exception:
            current_enabled = False
            current_val = 1.01
        
        # 彈出確認對話框
        from PyQt6.QtWidgets import QMessageBox
        
        msg = QMessageBox()
        
        if current_enabled:
            # 已開啟 → 長按 = 存檔並關閉
            msg.setWindowTitle("💾 儲存速度校正")
            msg.setText(f"速度校正模式執行中\n\n目前校正係數：{current_val:.4f}\n\n是否儲存並關閉校正模式？")
            msg.setIcon(QMessageBox.Icon.Question)
        else:
            # 未開啟 → 長按 = 開啟校正模式
            msg.setWindowTitle("🔧 速度校正模式")
            msg.setText(f"是否啟用速度校正模式？\n\n目前校正係數：{current_val:.4f}\n\n啟用後，系統會根據 GPS 速度\n逐漸修正 OBD 速度係數。\n\n💡 再次長按可手動儲存")
            msg.setIcon(QMessageBox.Icon.Question)
        
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        
        result = msg.exec()
        
        if result == QMessageBox.StandardButton.Yes:
            try:
                import datagrab
                new_state = not current_enabled
                datagrab.set_speed_calibration_enabled(new_state)
                
                # 顯示結果
                status_msg = QMessageBox()
                if new_state:
                    # 開啟校正模式
                    status_msg.setWindowTitle("🔧 校正模式已啟用")
                    status_msg.setText(f"✅ 速度校正模式已啟用\n\n目前校正係數：{current_val:.4f}\n\n請在 GPS 訊號良好的情況下行駛，\n系統會自動調整校正值。\n\n💡 完成後長按此按鈕可儲存")
                    status_msg.setIcon(QMessageBox.Icon.Information)
                else:
                    # 關閉並儲存
                    datagrab.persist_speed_correction()
                    final_val = datagrab.get_speed_correction()
                    status_msg.setWindowTitle("💾 校正已儲存")
                    status_msg.setText(f"✅ 速度校正係數已儲存！\n\n最終校正係數：{final_val:.4f}\n\n校正模式已關閉")
                    status_msg.setIcon(QMessageBox.Icon.Information)
                status_msg.setWindowFlags(status_msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
                status_msg.exec()
                
            except Exception as e:
                print(f"[速度校正] 切換失敗: {e}")
    
    def adjust_color(self, hex_color, factor):
        """調整顏色亮度"""
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))
        return f'#{r:02x}{g:02x}{b:02x}'
    
    def _get_button_by_title(self, title):
        """取得指定標題的 QPushButton 物件"""
        if title not in self.button_widgets:
            return None
        container = self.button_widgets[title]
        for child in container.findChildren(QPushButton):
            return child
        return None

    def _apply_speed_sync_style(self, btn: QPushButton, mode: str):
        """套用速度同步按鈕的樣式與文字"""
        label_map = {
            "calibrated": "OBD\n(校正)",
            "fixed": "OBD\n(同步)",
            "gps": "OBD\n(GPS)",
        }
        color_map = {
            "calibrated": "#4CAF50",
            "fixed": "#FF9800",
            "gps": "#2196F3",
        }
        text = label_map.get(mode, mode)
        color = color_map.get(mode, "#555555")
        btn.setText(text)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                border: none;
                border-radius: 20px;
                font-size: 28px;
                color: white;
            }}
            QPushButton:hover {{
                background-color: {self.adjust_color(color, 1.15)};
            }}
            QPushButton:pressed {{
                background-color: {self.adjust_color(color, 0.85)};
            }}
        """)

    def set_speed_sync_state(self, mode: str):
        """更新速度同步按鈕狀態（UI）"""
        self.speed_sync_mode = mode
        btn = self._get_button_by_title("速度同步")
        if btn:
            btn.blockSignals(True)
            self._apply_speed_sync_style(btn, mode)
            btn.blockSignals(False)

    def on_button_clicked(self, title, checked=False):
        """按鈕點擊處理"""
        print(f"控制面板按鈕被點擊: {title}")
        # 這裡可以添加具體功能
        if title == "WiFi":
            # 可以觸發 WiFi 管理器
            parent = self.parent()
            if parent and hasattr(parent, 'show_wifi_manager'):
                parent.show_wifi_manager()  # type: ignore
        elif title == "時間":
            self.do_time_sync()
        elif title == "亮度":
            self.cycle_brightness()
        elif title == "更新":
            self.do_auto_update()
        elif title == "電源":
            self.show_power_menu()
        elif title == "設定":
            # 開啟 MQTT 設定對話框
            parent = self.parent()
            if parent and hasattr(parent, 'show_mqtt_settings'):
                parent.show_mqtt_settings()  # type: ignore
        elif title == "速度同步":
            # 檢查是否為長按（長按已處理，不要觸發普通點擊）
            btn = self._get_button_by_title("速度同步")
            if btn and hasattr(btn, '_is_long_press') and btn._is_long_press:
                btn._is_long_press = False
                return  # 長按已處理，跳過
            
            parent = self.parent()
            if parent and hasattr(parent, 'cycle_speed_sync_mode'):
                parent.cycle_speed_sync_mode()  # type: ignore
            else:
                # 後備：僅更新當前模式的 UI 樣式
                self.set_speed_sync_state(getattr(self, "speed_sync_mode", "calibrated"))
    
    def do_time_sync(self):
        """執行 NTP 時間校正"""
        from PyQt6.QtWidgets import QMessageBox
        import subprocess
        
        # 檢查網路狀態
        main_window = self.parent()
        if main_window and hasattr(main_window, 'is_offline') and main_window.is_offline:
            msg = QMessageBox()
            msg.setWindowTitle("無法校正時間")
            msg.setText("網路未連線，無法執行 NTP 時間校正。\n請先連接網路後再試。")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            msg.exec()
            return
        
        # 更新按鈕狀態為同步中
        self._update_time_button_syncing(True)
        
        try:
            result_text = ""
            success = False
            
            # 嘗試使用 timedatectl (systemd-timesyncd)
            if os.path.exists('/usr/bin/timedatectl'):
                print("[時間校正] 使用 timedatectl...")
                
                # 啟用 NTP
                subprocess.run(['sudo', 'timedatectl', 'set-ntp', 'true'], 
                              capture_output=True, timeout=5)
                
                # 重啟 timesyncd 強制同步
                subprocess.run(['sudo', 'systemctl', 'restart', 'systemd-timesyncd'],
                              capture_output=True, timeout=10)
                
                # 等待同步
                import time
                time.sleep(2)
                
                # 檢查同步狀態
                result = subprocess.run(['timedatectl', 'show', '--property=NTPSynchronized'],
                                       capture_output=True, text=True, timeout=5)
                
                if 'NTPSynchronized=yes' in result.stdout:
                    success = True
                    result_text = "NTP 同步成功"
                else:
                    # 即使沒有顯示同步成功，也可能已經更新
                    success = True
                    result_text = "已嘗試 NTP 同步"
                    
            # 備用：嘗試使用 ntpdate
            elif os.path.exists('/usr/sbin/ntpdate'):
                print("[時間校正] 使用 ntpdate...")
                result = subprocess.run(
                    ['sudo', 'ntpdate', '-u', 'pool.ntp.org'],
                    capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0:
                    success = True
                    result_text = "NTP 同步成功"
                else:
                    # 嘗試備用伺服器
                    result = subprocess.run(
                        ['sudo', 'ntpdate', '-u', 'time.google.com'],
                        capture_output=True, text=True, timeout=15
                    )
                    success = result.returncode == 0
                    result_text = "NTP 同步成功" if success else "同步失敗"
            else:
                result_text = "未找到 NTP 工具"
                success = False
            
            # 如果有 RTC，也同步到 RTC
            if success and os.path.exists('/dev/rtc0'):
                print("[時間校正] 同步時間到 RTC...")
                subprocess.run(['sudo', 'hwclock', '-w'], capture_output=True, timeout=5)
                result_text += "\n已同步到 RTC"
            
            # 顯示結果
            from datetime import datetime
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            msg = QMessageBox()
            if success:
                msg.setWindowTitle("時間校正完成")
                msg.setText(f"{result_text}\n\n目前時間：{current_time}")
                msg.setIcon(QMessageBox.Icon.Information)
            else:
                msg.setWindowTitle("時間校正失敗")
                msg.setText(f"{result_text}\n\n請檢查網路連線後重試。")
                msg.setIcon(QMessageBox.Icon.Warning)
            
            msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            msg.exec()
            
            # 更新日期時間顯示
            self.update_status_info()
            
        except subprocess.TimeoutExpired:
            msg = QMessageBox()
            msg.setWindowTitle("時間校正逾時")
            msg.setText("NTP 同步逾時，請檢查網路連線後重試。")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            msg.exec()
        except Exception as e:
            msg = QMessageBox()
            msg.setWindowTitle("時間校正錯誤")
            msg.setText(f"發生錯誤：{str(e)}")
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            msg.exec()
        finally:
            # 恢復按鈕狀態
            self._update_time_button_syncing(False)
    
    def _update_time_button_syncing(self, syncing):
        """更新時間按鈕的同步狀態"""
        if "時間" not in self.button_widgets:
            return
        
        btn_container = self.button_widgets["時間"]
        for child in btn_container.findChildren(QPushButton):
            if syncing:
                child.setText("⏳")
                child.setEnabled(False)
                child.setStyleSheet("""
                    QPushButton {
                        background-color: #666;
                        border: none;
                        border-radius: 20px;
                        font-size: 48px;
                        color: white;
                    }
                """)
            else:
                child.setText("🕐")
                child.setEnabled(True)
                child.setStyleSheet("""
                    QPushButton {
                        background-color: #4285F4;
                        border: none;
                        border-radius: 20px;
                        font-size: 48px;
                        color: white;
                    }
                    QPushButton:hover {
                        background-color: #5a9cf4;
                    }
                    QPushButton:pressed {
                        background-color: #3367d6;
                    }
                """)

    def cycle_brightness(self):
        """循環切換亮度"""
        parent = self.parent()
        if parent and hasattr(parent, 'cycle_brightness'):
            level = parent.cycle_brightness()
            # 更新按鈕顯示
            self._update_brightness_button(level)
    
    def _update_brightness_button(self, level):
        """更新亮度按鈕的顯示"""
        if "亮度" not in self.button_widgets:
            return
        
        btn_container = self.button_widgets["亮度"]
        for child in btn_container.findChildren(QPushButton):
            # 根據亮度等級更新圖示
            if level == 0:
                child.setText("☀")  # 全亮
                color = "#FF9800"
            elif level == 1:
                child.setText("🔅")  # 75%
                color = "#FFA726"
            else:
                child.setText("🔆")  # 50%
                color = "#FFB74D"
            
            child.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: none;
                    border-radius: 20px;
                    font-size: 48px;
                    color: white;
                }}
                QPushButton:hover {{
                    background-color: {self.adjust_color(color, 1.2)};
                }}
                QPushButton:pressed {{
                    background-color: {self.adjust_color(color, 0.8)};
                }}
            """)
    
    def set_update_button_enabled(self, enabled):
        """設定更新按鈕的啟用狀態"""
        if "更新" in self.button_widgets:
            btn_container = self.button_widgets["更新"]
            # 找到容器內的 QPushButton
            for child in btn_container.findChildren(QPushButton):
                child.setEnabled(enabled)
                if enabled:
                    child.setStyleSheet("""
                        QPushButton {
                            background-color: #00BCD4;
                            border: none;
                            border-radius: 20px;
                            font-size: 48px;
                            color: white;
                        }
                        QPushButton:hover {
                            background-color: #26C6DA;
                        }
                        QPushButton:pressed {
                            background-color: #0097A7;
                        }
                    """)
                else:
                    child.setStyleSheet("""
                        QPushButton {
                            background-color: #444;
                            border: none;
                            border-radius: 20px;
                            font-size: 48px;
                            color: #888;
                        }
                    """)
    
    def do_auto_update(self):
        """執行自動更新"""
        from PyQt6.QtWidgets import QMessageBox, QApplication, QComboBox, QDialog, QVBoxLayout, QLabel
        import subprocess
        import sys
        
        # 檢查網路狀態
        main_window = self.parent()
        if main_window and hasattr(main_window, 'is_offline') and main_window.is_offline:
            msg = QMessageBox()
            msg.setWindowTitle("無法更新")
            msg.setText("網路未連線，無法執行自動更新。\n請先連接網路後再試。")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            msg.exec()
            return
        
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            
            # 取得目前分支
            current_branch_result = subprocess.run(
                ['git', 'branch', '--show-current'],
                cwd=script_dir,
                capture_output=True,
                text=True
            )
            current_branch = current_branch_result.stdout.strip()
            
            # 取得所有遠端分支
            remote_branches_result = subprocess.run(
                ['git', 'branch', '-r'],
                cwd=script_dir,
                capture_output=True,
                text=True
            )
            remote_branches = []
            for line in remote_branches_result.stdout.strip().split('\n'):
                line = line.strip()
                if line and not line.startswith('HEAD'):
                    branch = line.replace('origin/', '')
                    remote_branches.append(branch)
            
            if not remote_branches:
                msg = QMessageBox()
                msg.setWindowTitle("無法更新")
                msg.setText("找不到遠端分支，請確認已設定 Git 遠端。")
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
                msg.exec()
                return
            
            # 選擇分支對話框
            dialog = QDialog()
            dialog.setWindowTitle("選擇分支")
            dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            layout = QVBoxLayout(dialog)
            
            label = QLabel("請選擇要更新的分支：")
            layout.addWidget(label)
            
            combo = QComboBox()
            combo.addItems(remote_branches)
            if current_branch in remote_branches:
                combo.setCurrentText(current_branch)
            layout.addWidget(combo)
            
            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(button_box)
            
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            
            selected_branch = combo.currentText()
            
        except Exception as e:
            err_box = QMessageBox()
            err_box.setWindowTitle("取得分支失敗")
            err_box.setText(f"無法取得分支列表：\n{str(e)}")
            err_box.setIcon(QMessageBox.Icon.Critical)
            err_box.setWindowFlags(err_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            err_box.exec()
            return
        
        # 確認對話框
        msg = QMessageBox()
        msg.setWindowTitle("自動更新")
        msg.setText(f"是否要從「{selected_branch}」分支拉取最新版本並重新啟動？")
        msg.setInformativeText(
            "這將會：\n"
            f"• 執行 git pull origin {selected_branch}\n"
            "• 關閉目前程式\n"
            "• 重新啟動儀表板"
        )
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return
        
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            
            print(f"[更新] 正在執行 git pull origin {selected_branch}...")
            result = subprocess.run(
                ['git', 'pull', 'origin', selected_branch],
                cwd=script_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "未知錯誤"
                err_box = QMessageBox()
                err_box.setWindowTitle("更新失敗")
                err_box.setText(f"Git pull 失敗:\n{error_msg}")
                err_box.setIcon(QMessageBox.Icon.Critical)
                err_box.setWindowFlags(err_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
                err_box.exec()
                return
            
            print(f"[更新] Git pull 結果: {result.stdout}")
            
            # 顯示成功訊息
            success_box = QMessageBox()
            success_box.setWindowTitle("更新完成")
            success_box.setText("已成功取得最新版本！")
            success_box.setInformativeText(f"{result.stdout}\n\n程式將在 2 秒後重新啟動...")
            success_box.setIcon(QMessageBox.Icon.Information)
            success_box.setWindowFlags(success_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            success_box.exec()
            
            # 延遲重啟 (給使用者看到訊息)
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self._restart_application(script_dir))
            
        except subprocess.TimeoutExpired:
            err_box = QMessageBox()
            err_box.setWindowTitle("更新逾時")
            err_box.setText("Git pull 執行逾時，請檢查網路連線後重試。")
            err_box.setIcon(QMessageBox.Icon.Critical)
            err_box.setWindowFlags(err_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            err_box.exec()
        except FileNotFoundError:
            err_box = QMessageBox()
            err_box.setWindowTitle("Git 未安裝")
            err_box.setText("找不到 git 指令，請確認已安裝 Git。")
            err_box.setIcon(QMessageBox.Icon.Critical)
            err_box.setWindowFlags(err_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            err_box.exec()
        except Exception as e:
            err_box = QMessageBox()
            err_box.setWindowTitle("更新錯誤")
            err_box.setText(f"更新過程發生錯誤:\n{str(e)}")
            err_box.setIcon(QMessageBox.Icon.Critical)
            err_box.setWindowFlags(err_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            err_box.exec()
    
    def show_power_menu(self):
        """顯示電源選單"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QApplication, QMainWindow
        import platform
        
        is_linux = platform.system() == 'Linux'
        
        # 取得實際顯示的視窗大小
        # 在開發環境中，Dashboard 被包在 ScalableWindow (QMainWindow) 裡面
        # Dashboard 本身永遠是 1920x480，但 ScalableWindow 是縮放過的
        parent_width = 1920
        parent_height = 480
        
        # 嘗試找到 ScalableWindow（QMainWindow 類型的父視窗）
        widget = self
        while widget:
            parent = widget.parent()
            if parent is None:
                break
            # 檢查是否是 QMainWindow（ScalableWindow）
            if isinstance(parent, QMainWindow):
                parent_width = parent.width()
                parent_height = parent.height()
                print(f"[電源選單] 找到 ScalableWindow: {parent_width}x{parent_height}")
                break
            widget = parent
        
        # 如果找不到 ScalableWindow，檢查是否在全螢幕模式
        if parent_width == 1920 and parent_height == 480:
            # 可能是全螢幕模式或直接顯示 Dashboard
            screen = QApplication.primaryScreen()
            if screen:
                geometry = screen.availableGeometry()
                # 如果螢幕小於 1920x480，使用螢幕大小
                if geometry.width() < 1920 or geometry.height() < 480:
                    parent_width = geometry.width()
                    parent_height = min(geometry.height(), int(geometry.width() / 4))
                    print(f"[電源選單] 使用螢幕大小: {parent_width}x{parent_height}")
        
        print(f"[電源選單] 最終視窗大小: {parent_width}x{parent_height}")
        
        # 計算縮放比例（以 1920x480 為基準）
        scale = min(parent_width / 1920, parent_height / 480)
        print(f"[電源選單] 縮放比例: {scale}")
        
        dialog_width = int(1920 * scale)
        dialog_height = int(480 * scale)
        btn_width = int(280 * scale)
        btn_height = int(200 * scale)
        title_font_size = max(12, int(36 * scale))
        btn_font_size = max(10, int(28 * scale))
        btn_radius = max(5, int(20 * scale))
        margin = max(10, int(60 * scale))
        spacing = max(10, int(40 * scale))
        
        # 創建電源選單對話框
        dialog = QDialog()
        dialog.setWindowTitle("電源選項")
        dialog.setFixedSize(dialog_width, dialog_height)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: #1a1a25;
            }}
            QLabel {{
                color: white;
                font-size: 18px;
                background: transparent;
            }}
            QPushButton {{
                background-color: #2a2a3a;
                color: white;
                border: none;
                border-radius: {btn_radius}px;
                font-size: {int(24 * scale)}px;
                font-weight: bold;
                padding: {int(20 * scale)}px;
            }}
            QPushButton:hover {{
                background-color: #3a3a4a;
            }}
            QPushButton:pressed {{
                background-color: #4a4a5a;
            }}
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(margin, int(40 * scale), margin, int(40 * scale))
        layout.setSpacing(int(30 * scale))
        
        # 標題
        title = QLabel("🔌 電源選項")
        title.setStyleSheet(f"font-size: {title_font_size}px; font-weight: bold; color: white;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        layout.addStretch()
        
        # 水平按鈕佈局
        button_layout = QHBoxLayout()
        button_layout.setSpacing(spacing)
        
        # 程式重啟按鈕
        btn_app_restart = QPushButton("🔄\n程式重啟")
        btn_app_restart.setFixedSize(btn_width, btn_height)
        btn_app_restart.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_app_restart.setStyleSheet(f"""
            QPushButton {{
                background-color: #00BCD4;
                font-size: {btn_font_size}px;
                border-radius: {btn_radius}px;
            }}
            QPushButton:hover {{
                background-color: #26C6DA;
            }}
        """)
        btn_app_restart.clicked.connect(lambda: self._power_action('app_restart', dialog))
        button_layout.addWidget(btn_app_restart)
        
        # 系統重啟按鈕
        btn_sys_reboot = QPushButton("🔃\n系統重啟")
        btn_sys_reboot.setFixedSize(btn_width, btn_height)
        btn_sys_reboot.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sys_reboot.setStyleSheet(f"""
            QPushButton {{
                background-color: #FF9800;
                font-size: {btn_font_size}px;
                border-radius: {btn_radius}px;
            }}
            QPushButton:hover {{
                background-color: #FFB74D;
            }}
        """)
        btn_sys_reboot.clicked.connect(lambda: self._power_action('reboot', dialog))
        button_layout.addWidget(btn_sys_reboot)
        
        # 關機按鈕
        btn_shutdown = QPushButton("🔌\n關機")
        btn_shutdown.setFixedSize(btn_width, btn_height)
        btn_shutdown.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_shutdown.setStyleSheet(f"""
            QPushButton {{
                background-color: #E91E63;
                font-size: {btn_font_size}px;
                border-radius: {btn_radius}px;
            }}
            QPushButton:hover {{
                background-color: #F06292;
            }}
        """)
        btn_shutdown.clicked.connect(lambda: self._power_action('shutdown', dialog))
        button_layout.addWidget(btn_shutdown)
        
        # 取消按鈕
        btn_cancel = QPushButton("✕\n取消")
        btn_cancel.setFixedSize(btn_width, btn_height)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: #424242;
                font-size: {btn_font_size}px;
                border-radius: {btn_radius}px;
            }}
            QPushButton:hover {{
                background-color: #616161;
            }}
        """)
        btn_cancel.clicked.connect(dialog.reject)
        button_layout.addWidget(btn_cancel)
        
        layout.addLayout(button_layout)
        
        layout.addStretch()
        
        dialog.exec()
    
    def _power_action(self, action, dialog):
        """執行電源操作"""
        from PyQt6.QtWidgets import QMessageBox, QApplication
        import subprocess
        import os
        import platform
        
        is_linux = platform.system() == 'Linux'
        dialog.close()
        
        action_names = {
            'app_restart': '程式重啟',
            'reboot': '系統重啟',
            'shutdown': '關機'
        }
        
        # 確認對話框
        msg = QMessageBox()
        msg.setWindowTitle("確認操作")
        
        if action == 'app_restart':
            # 特殊處理：提供重啟和關閉兩個選項
            msg.setText("請選擇操作：")
            msg.setInformativeText(
                "⚠️ 注意：在 Raspberry Pi 上，若關閉程式後\n"
                "需透過 SSH 才能重新啟動儀表板。\n\n"
                "建議使用「重啟程式」以確保可繼續操作。"
            )
            msg.setIcon(QMessageBox.Icon.Question)
            
            # 自訂按鈕
            btn_restart = msg.addButton("🔄 重啟程式", QMessageBox.ButtonRole.AcceptRole)
            btn_close = msg.addButton("⏹️ 關閉程式", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            
            msg.setDefaultButton(btn_restart)
            msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            msg.exec()
            
            clicked = msg.clickedButton()
            if clicked == btn_restart:
                # 執行重啟
                try:
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    print("[電源] 準備程式重啟...")
                    self._show_power_countdown("程式重啟", 1)
                    QTimer.singleShot(1000, lambda: self._restart_application(script_dir))
                except Exception as e:
                    self._show_power_error(e)
            elif clicked == btn_close:
                # 執行關閉程式
                print("[電源] 關閉程式...")
                # 建立標記檔案，防止自動重啟
                try:
                    with open('/tmp/.dashboard_manual_exit', 'w') as f:
                        f.write('manual_exit')
                except:
                    pass
                self._show_power_countdown("關閉程式", 1)
                def force_exit():
                    print("[電源] 強制退出應用程式...")
                    import os
                    os._exit(0)
                QTimer.singleShot(1000, force_exit)
            # 取消則不做任何事
            return
            
        elif action == 'reboot':
            if is_linux:
                msg.setText("是否要重新啟動系統？\n\n系統將會完全重啟。")
            else:
                msg.setText("是否要模擬系統重啟？\n\n（macOS 上僅模擬，不會真的重啟）")
        elif action == 'shutdown':
            if is_linux:
                msg.setText("是否要關閉系統？\n\n系統將會關機。")
            else:
                msg.setText("是否要模擬關機？\n\n（macOS 上僅模擬，不會真的關機）")
        
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)
        msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return
        
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            
            # app_restart 已在上面處理，這裡只處理 reboot 和 shutdown
            if action == 'reboot':
                if is_linux:
                    print("[電源] 準備系統重啟...")
                    self._show_power_countdown("系統重啟", 3)
                    QTimer.singleShot(3000, lambda: subprocess.run(['sudo', 'reboot']))
                else:
                    # macOS 模擬
                    info_box = QMessageBox()
                    info_box.setWindowTitle("模擬系統重啟")
                    info_box.setText("🔃 模擬系統重啟中...\n\n（macOS 上僅顯示此訊息）")
                    info_box.setIcon(QMessageBox.Icon.Information)
                    info_box.setWindowFlags(info_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
                    info_box.exec()
                    
            elif action == 'shutdown':
                if is_linux:
                    print("[電源] 準備關機...")
                    self._show_power_countdown("關機", 3)
                    QTimer.singleShot(3000, lambda: subprocess.run(['sudo', 'shutdown', '-h', 'now']))
                else:
                    # macOS 模擬
                    info_box = QMessageBox()
                    info_box.setWindowTitle("模擬關機")
                    info_box.setText("🔌 模擬關機中...\n\n（macOS 上僅顯示此訊息）")
                    info_box.setIcon(QMessageBox.Icon.Information)
                    info_box.setWindowFlags(info_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
                    info_box.exec()
                    
        except Exception as e:
            err_box = QMessageBox()
            err_box.setWindowTitle("錯誤")
            err_box.setText(f"操作失敗:\n{str(e)}")
            err_box.setIcon(QMessageBox.Icon.Critical)
            err_box.setWindowFlags(err_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            err_box.exec()
    
    def _show_power_error(self, error):
        """顯示電源操作錯誤"""
        from PyQt6.QtWidgets import QMessageBox
        err_box = QMessageBox()
        err_box.setWindowTitle("錯誤")
        err_box.setText(f"操作失敗:\n{str(error)}")
        err_box.setIcon(QMessageBox.Icon.Critical)
        err_box.setWindowFlags(err_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        err_box.exec()
    
    def _show_power_countdown(self, action_name, seconds):
        """顯示電源操作倒數提示"""
        from PyQt6.QtWidgets import QMessageBox, QApplication
        
        info_box = QMessageBox()
        info_box.setWindowTitle(action_name)
        info_box.setText(f"⏳ {action_name}將在 {seconds} 秒後執行...")
        info_box.setIcon(QMessageBox.Icon.Information)
        info_box.setWindowFlags(info_box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        info_box.setStandardButtons(QMessageBox.StandardButton.NoButton)
        info_box.show()
        QApplication.processEvents()
    
    def _restart_application(self, script_dir):
        """重新啟動應用程式
        
        重啟策略：
        1. 如果是從 datagrab.py 或 demo_mode.py 啟動的，重啟原始入口腳本
        2. 如果 DASHBOARD_ENTRY 環境變數有設定，使用它來判斷入口點
        3. 否則直接重啟當前入口腳本
        """
        import subprocess
        import sys
        import os
        
        python_exe = sys.executable
        env = os.environ.copy()
        
        project_root = os.path.dirname(script_dir)
        
        # 檢查入口點
        # 方法 1: 檢查 sys.argv[0] (啟動腳本)
        entry_script = os.path.basename(sys.argv[0]) if sys.argv else ''
        
        # 方法 2: 檢查環境變數 (由啟動腳本設定)
        main_entry = os.environ.get('DASHBOARD_ENTRY', '')
        
        print(f"[重啟] 偵測入口點: argv[0]={entry_script}, DASHBOARD_ENTRY={main_entry}")
        
        restart_script = None
        restart_args = []
        restart_cwd = project_root
        
        if entry_script == 'main.py':
            restart_script = os.path.join(project_root, 'main.py')
            restart_args = []
            print(f"[重啟] 使用 main.py 模式: {restart_script}")
        elif 'datagrab' in entry_script or (main_entry == 'datagrab' and entry_script != 'main.py'):
            for candidate in ['datagrab.py', 'vehicle/datagrab.py']:
                candidate_path = os.path.join(project_root, candidate)
                if os.path.exists(candidate_path):
                    restart_script = candidate_path
                    break
            restart_args = ['-m', 'vehicle.datagrab']
            print(f"[重啟] 使用 CAN Bus 模式: {restart_script}")
        elif 'demo_mode' in entry_script or main_entry == 'demo':
            for candidate in ['demo_mode.py', 'vehicle/demo_mode.py']:
                candidate_path = os.path.join(project_root, candidate)
                if os.path.exists(candidate_path):
                    restart_script = candidate_path
                    restart_args = ['--spotify']
                    break
            if not restart_script:
                restart_args = ['-m', 'vehicle.demo_mode', '--spotify']
            print(f"[重啟] 使用演示模式: {restart_script}")
        else:
            # 無法判斷入口點，嘗試使用 sys.argv[0] 的完整路徑
            if sys.argv and os.path.exists(sys.argv[0]):
                restart_script = os.path.abspath(sys.argv[0])
                restart_args = []
                restart_cwd = os.path.dirname(restart_script)
                print(f"[重啟] 使用原始啟動腳本: {restart_script}")
            else:
                # 最後手段：直接啟動 main.py
                restart_script = os.path.join(project_root, 'main.py')
                restart_args = []
                print(f"[重啟] 找不到入口點，使用 main.py: {restart_script}")
        
        use_module = False
        if restart_script and os.path.exists(restart_script):
            if restart_args and restart_args[0] == '-m':
                use_module = True
                module_name = restart_args[1]
                cmd = [python_exe, '-m', module_name] + restart_args[2:]
                print(f"[重啟] 正在啟動 module {module_name}...")
            else:
                cmd = [python_exe, restart_script] + restart_args
                print(f"[重啟] 正在啟動 {restart_script} {restart_args}...")
            
            subprocess.Popen(
                cmd,
                cwd=restart_cwd,
                env=env,
                start_new_session=True,
                stdin=subprocess.DEVNULL
            )
        else:
            print(f"[重啟] 錯誤: 找不到重啟腳本 {restart_script}")
        
        # 關閉當前應用
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()
    
    def hide_panel(self):
        """隱藏面板"""
        parent = self.parent()
        if parent and hasattr(parent, 'hide_control_panel'):
            parent.hide_control_panel()  # type: ignore



