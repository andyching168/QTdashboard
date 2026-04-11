import json
import os
import threading
from datetime import datetime
from html import escape

import requests
from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget


class TelegramSettingsSignals(QObject):
    """Telegram 設定對話框的訊號"""

    settings_saved = pyqtSignal(bool)
    status_update = pyqtSignal(str)


class TelegramSettingsDialog(QWidget):
    """Telegram 設定對話框 - 透過 QR Code 讓使用者用手機填寫設定"""

    CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "telegram_config.json")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = TelegramSettingsSignals()
        self.server = None
        self.server_thread = None
        self._is_closing = False
        self._settings_received = False
        self._parent_ref = parent

        self.local_ip = self._get_local_ip()
        self.server_port = 8890

        self.init_ui()
        self.start_server()

    def _get_window_scale(self):
        """取得視窗縮放比例"""
        parent_width = 1920
        parent_height = 480

        widget = self._parent_ref
        while widget:
            parent = widget.parent() if hasattr(widget, "parent") else None
            if parent is None:
                if isinstance(widget, QMainWindow):
                    parent_width = widget.width()
                    parent_height = widget.height()
                    print(f"[Telegram設定] 找到 ScalableWindow: {parent_width}x{parent_height}")
                break
            if isinstance(parent, QMainWindow):
                parent_width = parent.width()
                parent_height = parent.height()
                print(f"[Telegram設定] 找到 ScalableWindow: {parent_width}x{parent_height}")
                break
            widget = parent

        if parent_width == 1920 and parent_height == 480:
            screen = QApplication.primaryScreen()
            if screen:
                geometry = screen.availableGeometry()
                if geometry.width() < 1920 or geometry.height() < 480:
                    parent_width = geometry.width()
                    parent_height = min(geometry.height(), int(geometry.width() / 4))
                    print(f"[Telegram設定] 使用螢幕大小: {parent_width}x{parent_height}")

        print(f"[Telegram設定] 最終視窗大小: {parent_width}x{parent_height}")
        scale = min(parent_width / 1920, parent_height / 480)
        print(f"[Telegram設定] 縮放比例: {scale}")
        return scale, parent_width, parent_height

    def _get_local_ip(self):
        """取得本機 IP"""
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("10.255.255.255", 1))
            ip = sock.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            sock.close()
        return ip

    def _create_qr_pixmap(self, data: str, size: int) -> QPixmap:
        """生成 QR Code 圖片"""
        try:
            import qrcode
            from io import BytesIO
            from PyQt6.QtGui import QImage

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
            img.save(buffer, format="PNG")
            buffer.seek(0)

            qimage = QImage.fromData(buffer.read())
            pixmap = QPixmap.fromImage(qimage)
            return pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        except ImportError:
            return QPixmap()

    def init_ui(self):
        """初始化 UI"""
        scale, window_width, window_height = self._get_window_scale()

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

        self.setWindowTitle("Telegram 設定")
        self.setFixedSize(window_width, window_height)
        self.setStyleSheet(
            f"""
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
            """
        )

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(margin_h, margin_v, margin_h, margin_v)
        main_layout.setSpacing(spacing)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setSpacing(max(8, int(15 * scale)))
        left_layout.setContentsMargins(0, 0, 0, 0)

        title_layout = QHBoxLayout()
        logo_label = QLabel("✈")
        logo_label.setFont(QFont("Arial", title_font))
        title = QLabel("Telegram 設定")
        title.setFont(QFont("Arial", title_font, QFont.Weight.Bold))
        title_layout.addWidget(logo_label)
        title_layout.addWidget(title)
        title_layout.addStretch()

        desc_label = QLabel("請使用手機掃描右側 QR Code，\n連接到設定頁面填寫 Telegram Bot 設定")
        desc_label.setFont(QFont("Arial", desc_font))
        desc_label.setStyleSheet("color: #B3B3B3;")
        desc_label.setWordWrap(True)

        steps_container = QWidget()
        steps_container.setStyleSheet(
            f"""
            QWidget {{
                background-color: #181818;
                border-radius: {steps_radius}px;
            }}
            """
        )
        steps_layout = QVBoxLayout(steps_container)
        steps_layout.setContentsMargins(steps_margin, steps_margin, steps_margin, steps_margin)
        steps_layout.setSpacing(max(6, int(12 * scale)))

        steps = [
            "1. 確認手機與車機連接同一 WiFi",
            "2. 開啟手機相機掃描 QR Code",
            "3. 填入 bot_token 與 chat_id",
            "4. 點擊「儲存設定」按鈕",
            "5. 系統驗證完成後會發送測試訊息",
        ]
        for step in steps:
            step_label = QLabel(step)
            step_label.setFont(QFont("Arial", step_font))
            step_label.setStyleSheet("color: #FFFFFF; background: transparent;")
            steps_layout.addWidget(step_label)

        self.status_label = QLabel("等待掃描...")
        self.status_label.setFont(QFont("Arial", status_font))
        self.status_label.setStyleSheet("color: #9C27B0;")

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

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.setSpacing(max(10, int(20 * scale)))

        qr_card = QWidget()
        qr_card.setFixedSize(qr_card_size, qr_card_size)
        qr_card.setStyleSheet(
            f"""
            QWidget {{
                background-color: white;
                border-radius: {max(10, int(20 * scale))}px;
            }}
            """
        )

        qr_layout = QVBoxLayout(qr_card)
        qr_layout.setContentsMargins(
            max(8, int(15 * scale)),
            max(8, int(15 * scale)),
            max(8, int(15 * scale)),
            max(8, int(15 * scale)),
        )
        qr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setScaledContents(True)
        self.qr_label.setFixedSize(qr_size, qr_size)
        qr_layout.addWidget(self.qr_label)

        self.url_label = QLabel(f"http://{self.local_ip}:{self.server_port}")
        self.url_label.setFont(QFont("Arial", url_font))
        self.url_label.setStyleSheet(
            f"""
            QLabel {{
                color: #B3B3B3;
                background-color: #181818;
                padding: {max(6, int(12 * scale))}px {max(10, int(20 * scale))}px;
                border-radius: {max(5, int(10 * scale))}px;
            }}
            """
        )
        self.url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        right_layout.addWidget(qr_card)
        right_layout.addWidget(self.url_label)

        main_layout.addWidget(left_container, 5)
        main_layout.addWidget(right_container, 4)

        self.signals.settings_saved.connect(self.on_settings_saved)
        self.signals.status_update.connect(self.on_status_update)

        url = f"http://{self.local_ip}:{self.server_port}"
        pixmap = self._create_qr_pixmap(url, qr_size)
        if not pixmap.isNull():
            self.qr_label.setPixmap(pixmap)
        else:
            self.qr_label.setText("QR Code\n生成失敗")
            self.qr_label.setStyleSheet("color: #666; font-size: 18px;")

    def start_server(self):
        """啟動 HTTP 伺服器"""
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()

    def _run_server(self):
        """運行 HTTP 伺服器"""
        from http.server import BaseHTTPRequestHandler, HTTPServer

        dialog = self

        class TelegramSettingsHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                existing_config = dialog._load_existing_config()
                bot_token = escape(str(existing_config.get("bot_token", "")), quote=True)
                chat_id = escape(str(existing_config.get("chat_id", "")), quote=True)

                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()

                html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
                    <title>Telegram 設定</title>
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
                        .form-group {{ margin-bottom: 20px; }}
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
                        button:hover {{ opacity: 0.9; }}
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
                            white-space: pre-wrap;
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
                        <h1>✈ 車機 Telegram 設定</h1>
                        <form id="telegramForm" onsubmit="return false;">
                            <div class="form-group">
                                <label for="bot_token">Bot Token</label>
                                <input type="text" id="bot_token" name="bot_token"
                                    placeholder="例如: 123456789:AA..." value="{bot_token}" required>
                            </div>
                            <div class="form-group">
                                <label for="chat_id">Chat ID</label>
                                <input type="text" id="chat_id" name="chat_id"
                                    placeholder="例如: 123456789 或 -100..." value="{chat_id}" required>
                            </div>
                            <button type="button" id="submitBtn" onclick="saveConfig()">儲存設定</button>
                        </form>
                        <div id="status" class="status"></div>
                    </div>
                    <script>
                        window.onerror = function(message, source, lineno, colno) {{
                            const status = document.getElementById('status');
                            if (status) {{
                                status.className = 'status error';
                                status.textContent = '❌ 前端腳本錯誤：' + message + ' (L' + lineno + ')';
                            }}
                        }};

                        async function saveConfig() {{
                            const form = document.getElementById('telegramForm');
                            if (!form.reportValidity()) {{
                                return;
                            }}

                            const btn = document.getElementById('submitBtn');
                            const status = document.getElementById('status');
                            console.log('[Telegram設定頁] saveConfig triggered');

                            btn.disabled = true;
                            btn.textContent = '正在驗證...';
                            status.className = 'status loading';
                            status.textContent = '已送出請求，正在測試 Telegram 連線...';

                            const formData = new FormData(form);
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
                        }}
                    </script>
                </body>
                </html>
                """
                self.wfile.write(html.encode("utf-8"))

            def do_POST(self):
                if self.path != "/save":
                    self.send_response(404)
                    self.end_headers()
                    return

                content_length = int(self.headers.get("Content-Length", 0))
                post_data = self.rfile.read(content_length)

                try:
                    data = json.loads(post_data.decode("utf-8"))
                    print("[Telegram設定] 收到 /save 請求")

                    try:
                        dialog.signals.status_update.emit("收到設定，正在驗證 Telegram API...")
                    except RuntimeError:
                        pass

                    success, message = dialog._test_telegram_connection(data)
                    print(f"[Telegram設定] 驗證結果 success={success}, message={message}")

                    if success:
                        dialog._save_config(data)
                        dialog._settings_received = True
                        try:
                            dialog.signals.status_update.emit("設定已儲存！5秒後關閉...")
                            dialog.signals.settings_saved.emit(True)
                        except RuntimeError:
                            pass

                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    response = json.dumps({"success": success, "message": message}, ensure_ascii=False)
                    self.wfile.write(response.encode("utf-8"))
                except Exception as exc:
                    print(f"[Telegram設定] /save 例外: {exc}")
                    self.send_response(500)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    response = json.dumps({"success": False, "message": f"伺服器錯誤：{exc}"}, ensure_ascii=False)
                    self.wfile.write(response.encode("utf-8"))

            def log_message(self, format, *args):
                pass

        try:
            self.server = HTTPServer(("0.0.0.0", self.server_port), TelegramSettingsHandler)
            if not self._is_closing:
                try:
                    self.signals.status_update.emit("伺服器已啟動，等待掃描...")
                except RuntimeError:
                    return
            self.server.serve_forever()
        except Exception as exc:
            if not self._is_closing:
                try:
                    self.signals.status_update.emit(f"伺服器錯誤: {exc}")
                except RuntimeError:
                    pass

    def _load_existing_config(self) -> dict:
        """讀取現有設定"""
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as file:
                    return json.load(file)
        except Exception:
            pass
        return {}

    def _save_config(self, data: dict):
        """儲存設定到檔案"""
        try:
            config = {
                "bot_token": data.get("bot_token", "").strip(),
                "chat_id": data.get("chat_id", "").strip(),
            }
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as file:
                json.dump(config, file, indent=2, ensure_ascii=False)
            print(f"[Telegram] 設定已儲存到 {self.CONFIG_FILE}")
        except Exception as exc:
            print(f"[Telegram] 儲存設定失敗: {exc}")

    def _test_telegram_connection(self, data: dict) -> tuple:
        """測試 Telegram API 連線，並在驗證後發送測試訊息"""
        token = data.get("bot_token", "").strip()
        chat_id = data.get("chat_id", "").strip()

        if not token:
            return False, "請填寫 Bot Token"
        if not chat_id:
            return False, "請填寫 Chat ID"

        base_url = f"https://api.telegram.org/bot{token}"

        try:
            me_resp = requests.get(f"{base_url}/getMe", timeout=5)
            me_json = me_resp.json()
            if me_resp.status_code != 200 or not me_json.get("ok"):
                description = me_json.get("description", "Token 驗證失敗")
                return False, f"Token 驗證失敗：{description}"

            chat_resp = requests.post(
                f"{base_url}/getChat",
                json={"chat_id": chat_id},
                timeout=5,
            )
            chat_json = chat_resp.json()
            if chat_resp.status_code != 200 or not chat_json.get("ok"):
                description = chat_json.get("description", "Chat ID 驗證失敗")
                return False, f"Chat ID 驗證失敗：{description}"

            # 驗證完成後，送一則實際測試訊息，確保此 chat_id 可接收通知。
            test_text = (
                "✅ QTdashboard Telegram 設定測試成功\n"
                f"時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            send_resp = requests.post(
                f"{base_url}/sendMessage",
                json={"chat_id": chat_id, "text": test_text},
                timeout=8,
            )
            send_json = send_resp.json()
            if send_resp.status_code != 200 or not send_json.get("ok"):
                description = send_json.get("description", "測試訊息發送失敗")
                return False, f"測試訊息發送失敗：{description}"

            return True, "Telegram 驗證成功，已發送測試訊息並儲存設定"
        except requests.Timeout:
            return False, "Telegram API 連線逾時，請稍後重試"
        except requests.RequestException as exc:
            return False, f"Telegram API 連線錯誤：{exc}"
        except Exception as exc:
            return False, f"驗證失敗：{exc}"

    def on_settings_saved(self, success: bool):
        """設定儲存完成"""
        if success:
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

        if self.server:
            def shutdown_server():
                try:
                    self.server.shutdown()
                    self.server.server_close()
                except Exception:
                    pass

            threading.Thread(target=shutdown_server, daemon=True).start()

        self.close()

    def closeEvent(self, event):
        """關閉事件"""
        if not self._is_closing:
            self.cleanup_and_close()
        event.accept()
