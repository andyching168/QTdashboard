# Auto-extracted from main.py
import time
import os
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

class MQTTSettingsSignals(QObject):
    """MQTT 設定對話框的訊號"""
    settings_saved = pyqtSignal(bool)
    status_update = pyqtSignal(str)



class MQTTSettingsDialog(QWidget):
    """MQTT 設定對話框 - 透過 QR Code 讓使用者用手機填寫設定"""
    
    CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mqtt_config.json")
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = MQTTSettingsSignals()
        self.server = None
        self.server_thread = None
        self._is_closing = False
        self._settings_received = False
        self._parent_ref = parent  # 保存父視窗參考用於計算縮放
        
        # 預先取得本機 IP
        self.local_ip = self._get_local_ip()
        self.server_port = 8889  # 使用不同於 Spotify 的 port
        
        self.init_ui()
        self.start_server()
    
    def _get_window_scale(self):
        """取得視窗縮放比例"""
        from PyQt6.QtWidgets import QApplication, QMainWindow
        
        parent_width = 1920
        parent_height = 480
        
        # 嘗試找到 ScalableWindow（QMainWindow 類型的父視窗）
        widget = self._parent_ref
        while widget:
            parent = widget.parent() if hasattr(widget, 'parent') else None
            if parent is None:
                # 檢查當前 widget 是否是 QMainWindow
                if isinstance(widget, QMainWindow):
                    parent_width = widget.width()
                    parent_height = widget.height()
                    print(f"[MQTT設定] 找到 ScalableWindow: {parent_width}x{parent_height}")
                break
            if isinstance(parent, QMainWindow):
                parent_width = parent.width()
                parent_height = parent.height()
                print(f"[MQTT設定] 找到 ScalableWindow: {parent_width}x{parent_height}")
                break
            widget = parent
        
        # 如果找不到 ScalableWindow，檢查螢幕大小
        if parent_width == 1920 and parent_height == 480:
            screen = QApplication.primaryScreen()
            if screen:
                geometry = screen.availableGeometry()
                if geometry.width() < 1920 or geometry.height() < 480:
                    parent_width = geometry.width()
                    parent_height = min(geometry.height(), int(geometry.width() / 4))
                    print(f"[MQTT設定] 使用螢幕大小: {parent_width}x{parent_height}")
        
        print(f"[MQTT設定] 最終視窗大小: {parent_width}x{parent_height}")
        scale = min(parent_width / 1920, parent_height / 480)
        print(f"[MQTT設定] 縮放比例: {scale}")
        return scale, parent_width, parent_height
    
    def _get_local_ip(self):
        """取得本機 IP"""
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip
    
    def _create_qr_pixmap(self, data: str, size: int) -> QPixmap:
        """生成 QR Code 圖片"""
        try:
            import qrcode
            from io import BytesIO
            
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=8,
                border=2,
            )
            qr.add_data(data)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            
            from PyQt6.QtGui import QImage
            qimage = QImage.fromData(buffer.read())
            pixmap = QPixmap.fromImage(qimage)
            
            return pixmap.scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        except ImportError:
            # qrcode 未安裝，返回空 pixmap
            return QPixmap()
    
    def init_ui(self):
        """初始化 UI"""
        # 取得縮放比例
        scale, window_width, window_height = self._get_window_scale()
        
        # 計算縮放後的尺寸
        title_font = max(12, int(36 * scale))
        desc_font = max(10, int(18 * scale))
        step_font = max(9, int(16 * scale))
        status_font = max(10, int(18 * scale))
        url_font = max(9, int(14 * scale))
        btn_font = max(10, int(18 * scale))
        btn_radius = max(10, int(25 * scale))
        btn_width = max(80, int(150 * scale))
        qr_card_size = max(150, int(300 * scale))
        qr_size = max(135, int(270 * scale))
        margin_h = max(20, int(60 * scale))
        margin_v = max(15, int(30 * scale))
        spacing = max(20, int(50 * scale))
        steps_margin = max(10, int(20 * scale))
        steps_radius = max(8, int(15 * scale))
        
        self.setWindowTitle("MQTT 設定")
        self.setFixedSize(window_width, window_height)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: #121212;
                color: white;
                font-family: "Arial";
            }}
            QLabel {{
                color: #FFFFFF;
            }}
            QPushButton {{
                background-color: transparent;
                border: 2px solid #535353;
                border-radius: {btn_radius}px;
                color: white;
                font-size: {btn_font}px;
                font-weight: bold;
                padding: {max(5, int(10 * scale))}px {max(15, int(30 * scale))}px;
            }}
            QPushButton:hover {{
                border-color: white;
                background-color: #2a2a2a;
            }}
        """)
        
        # 主佈局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(margin_h, margin_v, margin_h, margin_v)
        main_layout.setSpacing(spacing)
        
        # === 左側：說明區 ===
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setSpacing(max(8, int(15 * scale)))
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 標題
        title_layout = QHBoxLayout()
        logo_label = QLabel("⚙")
        logo_label.setFont(QFont("Arial", title_font))
        title = QLabel("MQTT 設定")
        title.setFont(QFont("Arial", title_font, QFont.Weight.Bold))
        title_layout.addWidget(logo_label)
        title_layout.addWidget(title)
        title_layout.addStretch()
        
        # 說明文字
        desc_label = QLabel("請使用手機掃描右側 QR Code，\n連接到設定頁面填寫 MQTT Broker 資訊")
        desc_label.setFont(QFont("Arial", desc_font))
        desc_label.setStyleSheet("color: #B3B3B3;")
        desc_label.setWordWrap(True)
        
        # 步驟說明
        steps_container = QWidget()
        steps_container.setStyleSheet(f"""
            QWidget {{
                background-color: #181818;
                border-radius: {steps_radius}px;
            }}
        """)
        steps_layout = QVBoxLayout(steps_container)
        steps_layout.setContentsMargins(steps_margin, steps_margin, steps_margin, steps_margin)
        steps_layout.setSpacing(max(6, int(12 * scale)))
        
        steps = [
            "1. 確認手機與車機連接同一 WiFi",
            "2. 開啟手機相機掃描 QR Code",
            "3. 在網頁中填寫 MQTT 連線資訊",
            "4. 點擊「儲存設定」按鈕",
            "5. 系統將自動驗證連線"
        ]
        
        for step in steps:
            step_label = QLabel(step)
            step_label.setFont(QFont("Arial", step_font))
            step_label.setStyleSheet("color: #FFFFFF; background: transparent;")
            steps_layout.addWidget(step_label)
        
        # 狀態顯示
        self.status_label = QLabel("等待掃描...")
        self.status_label.setFont(QFont("Arial", status_font))
        self.status_label.setStyleSheet("color: #9C27B0;")
        
        # 取消按鈕
        cancel_btn = QPushButton("取消")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setFixedWidth(btn_width)
        cancel_btn.clicked.connect(self.cancel_settings)
        
        left_layout.addLayout(title_layout)
        left_layout.addWidget(desc_label)
        left_layout.addSpacing(max(5, int(10 * scale)))
        left_layout.addWidget(steps_container)
        left_layout.addSpacing(max(8, int(15 * scale)))
        left_layout.addWidget(self.status_label)
        left_layout.addStretch()
        left_layout.addWidget(cancel_btn)
        
        # === 右側：QR Code 區 ===
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.setSpacing(max(10, int(20 * scale)))
        
        # QR Code 卡片
        qr_card = QWidget()
        qr_card.setFixedSize(qr_card_size, qr_card_size)
        qr_card.setStyleSheet(f"""
            QWidget {{
                background-color: white;
                border-radius: {max(10, int(20 * scale))}px;
            }}
        """)
        
        qr_layout = QVBoxLayout(qr_card)
        qr_layout.setContentsMargins(max(8, int(15 * scale)), max(8, int(15 * scale)), 
                                      max(8, int(15 * scale)), max(8, int(15 * scale)))
        qr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setScaledContents(True)
        self.qr_label.setFixedSize(qr_size, qr_size)
        qr_layout.addWidget(self.qr_label)
        
        # URL 提示
        self.url_label = QLabel(f"http://{self.local_ip}:{self.server_port}")
        self.url_label.setFont(QFont("Arial", url_font))
        self.url_label.setStyleSheet(f"""
            QLabel {{
                color: #B3B3B3;
                background-color: #181818;
                padding: {max(6, int(12 * scale))}px {max(10, int(20 * scale))}px;
                border-radius: {max(5, int(10 * scale))}px;
            }}
        """)
        self.url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        right_layout.addWidget(qr_card)
        right_layout.addWidget(self.url_label)
        
        # 加入主佈局
        main_layout.addWidget(left_container, 5)
        main_layout.addWidget(right_container, 4)
        
        # 連接訊號
        self.signals.settings_saved.connect(self.on_settings_saved)
        self.signals.status_update.connect(self.on_status_update)
        
        # 生成 QR Code
        url = f"http://{self.local_ip}:{self.server_port}"
        pixmap = self._create_qr_pixmap(url, qr_size)
        if not pixmap.isNull():
            self.qr_label.setPixmap(pixmap)
        else:
            self.qr_label.setText("QR Code\n生成失敗")
            self.qr_label.setStyleSheet("color: #666; font-size: 18px;")
    
    def start_server(self):
        """啟動 HTTP 伺服器"""
        import threading
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()
    
    def _run_server(self):
        """運行 HTTP 伺服器"""
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import urllib.parse
        
        dialog = self  # 閉包引用
        
        class MQTTSettingsHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                """處理 GET 請求 - 返回設定表單"""
                # 讀取現有設定
                existing_config = dialog._load_existing_config()
                
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                
                html = f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
                    <title>MQTT 設定</title>
                    <style>
                        * {{ box-sizing: border-box; }}
                        body {{
                            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            min-height: 100vh;
                            margin: 0;
                            padding: 20px;
                        }}
                        .container {{
                            max-width: 500px;
                            margin: 0 auto;
                            background: white;
                            border-radius: 20px;
                            padding: 30px;
                            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                        }}
                        h1 {{
                            text-align: center;
                            color: #333;
                            margin-bottom: 30px;
                            font-size: 24px;
                        }}
                        .form-group {{
                            margin-bottom: 20px;
                        }}
                        label {{
                            display: block;
                            margin-bottom: 8px;
                            font-weight: 600;
                            color: #555;
                        }}
                        input {{
                            width: 100%;
                            padding: 15px;
                            border: 2px solid #ddd;
                            border-radius: 10px;
                            font-size: 16px;
                            transition: border-color 0.3s;
                        }}
                        input:focus {{
                            outline: none;
                            border-color: #667eea;
                        }}
                        button {{
                            width: 100%;
                            padding: 18px;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            border: none;
                            border-radius: 10px;
                            font-size: 18px;
                            font-weight: bold;
                            cursor: pointer;
                            margin-top: 20px;
                        }}
                        button:hover {{
                            opacity: 0.9;
                        }}
                        button:disabled {{
                            background: #ccc;
                            cursor: not-allowed;
                        }}
                        .status {{
                            text-align: center;
                            margin-top: 20px;
                            padding: 15px;
                            border-radius: 10px;
                            display: none;
                        }}
                        .status.success {{
                            background: #d4edda;
                            color: #155724;
                            display: block;
                        }}
                        .status.error {{
                            background: #f8d7da;
                            color: #721c24;
                            display: block;
                        }}
                        .status.loading {{
                            background: #e2e3e5;
                            color: #383d41;
                            display: block;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>🚗 車機 MQTT 設定</h1>
                        <form id="mqttForm">
                            <div class="form-group">
                                <label for="broker">Broker 位址</label>
                                <input type="text" id="broker" name="broker" 
                                    placeholder="例如: mqtt.example.com" 
                                    value="{existing_config.get('broker', '')}" required>
                            </div>
                            <div class="form-group">
                                <label for="port">Port</label>
                                <input type="number" id="port" name="port" 
                                    placeholder="1883" 
                                    value="{existing_config.get('port', '1883')}" required>
                            </div>
                            <div class="form-group">
                                <label for="username">使用者名稱 (選填)</label>
                                <input type="text" id="username" name="username" 
                                    placeholder="留空表示無需驗證"
                                    value="{existing_config.get('username', '')}">
                            </div>
                            <div class="form-group">
                                <label for="password">密碼 (選填)</label>
                                <input type="password" id="password" name="password" 
                                    placeholder="留空表示無需驗證"
                                    value="{existing_config.get('password', '')}">
                            </div>
                            <div class="form-group">
                                <label for="topic">訂閱主題</label>
                                <input type="text" id="topic" name="topic" 
                                    placeholder="例如: car/navigation/#"
                                    value="{existing_config.get('topic', 'car/#')}" required>
                            </div>
                            <button type="submit" id="submitBtn">儲存設定</button>
                        </form>
                        <div id="status" class="status"></div>
                    </div>
                    <script>
                        document.getElementById('mqttForm').addEventListener('submit', async function(e) {{
                            e.preventDefault();
                            
                            const btn = document.getElementById('submitBtn');
                            const status = document.getElementById('status');
                            
                            btn.disabled = true;
                            btn.textContent = '正在驗證...';
                            status.className = 'status loading';
                            status.textContent = '正在連接 MQTT Broker...';
                            
                            const formData = new FormData(this);
                            const data = Object.fromEntries(formData.entries());
                            
                            try {{
                                const response = await fetch('/save', {{
                                    method: 'POST',
                                    headers: {{ 'Content-Type': 'application/json' }},
                                    body: JSON.stringify(data)
                                }});
                                
                                const result = await response.json();
                                
                                if (result.success) {{
                                    status.className = 'status success';
                                    status.textContent = '✅ ' + result.message;
                                    btn.textContent = '設定完成！';
                                    
                                    setTimeout(() => {{
                                        status.textContent += '\\n此頁面將自動關閉...';
                                    }}, 2000);
                                }} else {{
                                    status.className = 'status error';
                                    status.textContent = '❌ ' + result.message;
                                    btn.disabled = false;
                                    btn.textContent = '重新嘗試';
                                }}
                            }} catch (error) {{
                                status.className = 'status error';
                                status.textContent = '❌ 連線錯誤：' + error.message;
                                btn.disabled = false;
                                btn.textContent = '重新嘗試';
                            }}
                        }});
                    </script>
                </body>
                </html>
                '''
                self.wfile.write(html.encode())
            
            def do_POST(self):
                """處理 POST 請求 - 儲存設定並驗證連線"""
                if self.path == '/save':
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    
                    try:
                        data = json.loads(post_data.decode())
                        
                        # 更新狀態
                        try:
                            dialog.signals.status_update.emit("收到設定，正在驗證...")
                        except RuntimeError:
                            pass
                        
                        # 驗證連線
                        success, message = dialog._test_mqtt_connection(data)
                        
                        if success:
                            # 儲存設定
                            dialog._save_config(data)
                            dialog._settings_received = True
                            
                            try:
                                dialog.signals.status_update.emit("設定已儲存！5秒後關閉...")
                                dialog.signals.settings_saved.emit(True)
                            except RuntimeError:
                                pass
                        
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        
                        response = json.dumps({
                            'success': success,
                            'message': message
                        })
                        self.wfile.write(response.encode())
                        
                    except Exception as e:
                        self.send_response(500)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        response = json.dumps({
                            'success': False,
                            'message': f'伺服器錯誤：{str(e)}'
                        })
                        self.wfile.write(response.encode())
                else:
                    self.send_response(404)
                    self.end_headers()
            
            def log_message(self, format, *args):
                """關閉日誌輸出"""
                pass
        
        try:
            self.server = HTTPServer(('0.0.0.0', self.server_port), MQTTSettingsHandler)
            if not self._is_closing:
                try:
                    self.signals.status_update.emit("伺服器已啟動，等待掃描...")
                except RuntimeError:
                    return
            self.server.serve_forever()
        except Exception as e:
            if not self._is_closing:
                try:
                    self.signals.status_update.emit(f"伺服器錯誤: {e}")
                except RuntimeError:
                    pass
    
    def _load_existing_config(self) -> dict:
        """讀取現有設定"""
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
    
    def _save_config(self, data: dict):
        """儲存設定到檔案"""
        try:
            config = {
                'broker': data.get('broker', ''),
                'port': int(data.get('port', 1883)),
                'username': data.get('username', ''),
                'password': data.get('password', ''),
                'topic': data.get('topic', 'car/#')
            }
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"[MQTT] 設定已儲存到 {self.CONFIG_FILE}")
        except Exception as e:
            print(f"[MQTT] 儲存設定失敗: {e}")
    
    def _test_mqtt_connection(self, data: dict) -> tuple:
        """
        測試 MQTT 連線
        Returns: (success: bool, message: str)
        """
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            return False, "paho-mqtt 未安裝，請執行: pip install paho-mqtt"
        
        broker = data.get('broker', '').strip()
        port = int(data.get('port', 1883))
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not broker:
            return False, "請填寫 Broker 位址"
        
        # 連線測試
        connected = False
        error_message = ""
        
        def on_connect(client, userdata, flags, rc, properties=None):
            nonlocal connected, error_message
            if rc == 0:
                connected = True
            else:
                error_codes = {
                    1: "協議版本錯誤",
                    2: "無效的客戶端 ID",
                    3: "伺服器不可用",
                    4: "使用者名稱或密碼錯誤",
                    5: "未授權"
                }
                error_message = error_codes.get(rc, f"連線失敗 (錯誤碼: {rc})")
        
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            client.on_connect = on_connect
            
            if username:
                client.username_pw_set(username, password)
            
            # 設定超時
            client.connect(broker, port, keepalive=10)
            
            # 等待連線結果（最多 5 秒）
            start_time = time.time()
            client.loop_start()
            
            while not connected and (time.time() - start_time) < 5:
                if error_message:
                    break
                time.sleep(0.1)
            
            client.loop_stop()
            client.disconnect()
            
            if connected:
                return True, "連線成功！設定已儲存"
            elif error_message:
                return False, error_message
            else:
                return False, "連線逾時，請檢查 Broker 位址和 Port"
                
        except Exception as e:
            error_str = str(e)
            if "Connection refused" in error_str:
                return False, "連線被拒絕，請檢查 Broker 位址和 Port"
            elif "timed out" in error_str.lower():
                return False, "連線逾時，請檢查網路連線"
            elif "Name or service not known" in error_str:
                return False, "無法解析 Broker 位址"
            else:
                return False, f"連線錯誤：{error_str}"
    
    def on_settings_saved(self, success: bool):
        """設定儲存完成"""
        if success:
            # 5秒後關閉
            QTimer.singleShot(5000, self.cleanup_and_close)
    
    def on_status_update(self, message: str):
        """更新狀態文字"""
        self.status_label.setText(message)
    
    def cancel_settings(self):
        """取消設定"""
        self.cleanup_and_close()
    
    def cleanup_and_close(self):
        """清理資源並關閉視窗"""
        self._is_closing = True
        
        # 在背景執行緒中關閉伺服器
        if self.server:
            import threading
            def shutdown_server():
                try:
                    self.server.shutdown()
                    self.server.server_close()
                except:
                    pass
            threading.Thread(target=shutdown_server, daemon=True).start()
        
        self.close()
    
    def closeEvent(self, event):
        """關閉事件"""
        if not self._is_closing:
            self.cleanup_and_close()
        event.accept()



