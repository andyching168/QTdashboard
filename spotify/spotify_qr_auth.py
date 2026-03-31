"""
Spotify QR Code 授權介面
適用於觸控螢幕，無需輸入帳號密碼
"""

import sys
import os
import socket
import qrcode
import threading
import time
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from io import BytesIO

from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                              QHBoxLayout, QPushButton, QProgressBar, QStackedWidget,
                              QLineEdit, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap, QImage, QFont, QClipboard

from spotify.spotify_auth import SpotifyAuthManager

logger = logging.getLogger(__name__)


class AuthCallbackHandler(BaseHTTPRequestHandler):
    """處理 OAuth 回調的 HTTP 伺服器"""
    
    auth_code = None
    rpi_ip = None  # RPI 的 IP 位址
    auth_url = None  # Spotify 授權 URL
    
    def do_GET(self):
        """處理 GET 請求"""
        path = urlparse(self.path).path
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        if path == '/':
            # 首頁：顯示授權引導頁面
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            rpi_ip = AuthCallbackHandler.rpi_ip or '127.0.0.1'
            
            # 手機友好的授權頁面
            auth_page = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
                <title>Spotify 授權</title>
                <style>
                    * {{ box-sizing: border-box; }}
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                        background: linear-gradient(135deg, #191414 0%, #1DB954 100%);
                        color: white;
                        min-height: 100vh;
                        margin: 0;
                        padding: 20px;
                    }}
                    .container {{
                        max-width: 400px;
                        margin: 0 auto;
                        text-align: center;
                    }}
                    .logo {{ font-size: 50px; margin: 20px 0; }}
                    h1 {{ font-size: 22px; margin: 0 0 10px 0; }}
                    .subtitle {{ font-size: 14px; opacity: 0.8; margin-bottom: 25px; }}
                    
                    .step-card {{
                        background: rgba(0,0,0,0.6);
                        border-radius: 16px;
                        padding: 20px;
                        margin-bottom: 15px;
                        text-align: left;
                    }}
                    .step-header {{
                        display: flex;
                        align-items: center;
                        margin-bottom: 12px;
                    }}
                    .step-num {{
                        background: #1DB954;
                        color: white;
                        width: 28px;
                        height: 28px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-weight: bold;
                        font-size: 14px;
                        margin-right: 12px;
                        flex-shrink: 0;
                    }}
                    .step-title {{ font-size: 16px; font-weight: 600; }}
                    .step-desc {{ font-size: 13px; opacity: 0.8; line-height: 1.5; }}
                    
                    .auth-btn {{
                        display: block;
                        background-color: #1DB954;
                        color: white;
                        text-decoration: none;
                        padding: 16px;
                        border-radius: 50px;
                        font-size: 17px;
                        font-weight: bold;
                        margin: 10px 0;
                        text-align: center;
                    }}
                    .auth-btn:active {{ background-color: #1ed760; }}
                    
                    .url-input {{
                        width: 100%;
                        padding: 14px;
                        border: 2px solid #333;
                        border-radius: 12px;
                        background: #222;
                        color: white;
                        font-size: 14px;
                        margin: 10px 0;
                    }}
                    .url-input:focus {{
                        outline: none;
                        border-color: #1DB954;
                    }}
                    .submit-btn {{
                        width: 100%;
                        padding: 14px;
                        background: #1DB954;
                        color: white;
                        border: none;
                        border-radius: 50px;
                        font-size: 16px;
                        font-weight: bold;
                        cursor: pointer;
                    }}
                    .submit-btn:disabled {{
                        background: #333;
                        color: #666;
                    }}
                    
                    .success-msg, .error-msg {{
                        padding: 15px;
                        border-radius: 12px;
                        margin: 15px 0;
                        display: none;
                    }}
                    .success-msg {{ background: rgba(29, 185, 84, 0.3); }}
                    .error-msg {{ background: rgba(255, 0, 0, 0.3); }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="logo">🎵</div>
                    <h1>車機 Spotify 連線</h1>
                    <p class="subtitle">請依照以下步驟完成授權</p>
                    
                    <div class="step-card">
                        <div class="step-header">
                            <div class="step-num">1</div>
                            <div class="step-title">點擊授權按鈕</div>
                        </div>
                        <a href="{AuthCallbackHandler.auth_url}" class="auth-btn" target="_blank">
                            🔗 前往 Spotify 授權
                        </a>
                    </div>
                    
                    <div class="step-card">
                        <div class="step-header">
                            <div class="step-num">2</div>
                            <div class="step-title">同意授權</div>
                        </div>
                        <p class="step-desc">
                            在 Spotify 頁面上點擊「同意」按鈕。<br>
                            授權後頁面會顯示「無法連線」，這是正常的。
                        </p>
                    </div>
                    
                    <div class="step-card">
                        <div class="step-header">
                            <div class="step-num">3</div>
                            <div class="step-title">複製網址並貼上</div>
                        </div>
                        <p class="step-desc">
                            複製瀏覽器網址列的完整網址，貼到下方：
                        </p>
                        <input type="text" id="urlInput" class="url-input" 
                               placeholder="貼上網址（以 http://127.0.0.1 開頭）"
                               oninput="checkInput()">
                        <button id="submitBtn" class="submit-btn" onclick="submitCode()" disabled>
                            完成授權
                        </button>
                    </div>
                    
                    <div id="successMsg" class="success-msg">
                        ✅ 授權成功！請返回車機查看
                    </div>
                    <div id="errorMsg" class="error-msg">
                        ❌ 授權碼無效，請重新複製網址
                    </div>
                </div>
                
                <script>
                    function checkInput() {{
                        const input = document.getElementById('urlInput').value;
                        const btn = document.getElementById('submitBtn');
                        btn.disabled = !input.includes('code=');
                    }}
                    
                    function submitCode() {{
                        const input = document.getElementById('urlInput').value;
                        const match = input.match(/code=([^&]+)/);
                        if (match) {{
                            const code = match[1];
                            // 發送到 RPI
                            fetch('/submit_code?code=' + encodeURIComponent(code))
                                .then(r => r.json())
                                .then(data => {{
                                    if (data.success) {{
                                        document.getElementById('successMsg').style.display = 'block';
                                        document.getElementById('errorMsg').style.display = 'none';
                                        document.getElementById('submitBtn').disabled = true;
                                        document.getElementById('submitBtn').textContent = '✓ 已完成';
                                    }} else {{
                                        document.getElementById('errorMsg').style.display = 'block';
                                    }}
                                }})
                                .catch(e => {{
                                    document.getElementById('errorMsg').style.display = 'block';
                                }});
                        }}
                    }}
                </script>
            </body>
            </html>
            """
            self.wfile.write(auth_page.encode())
            
        elif path == '/submit_code':
            # 接收手機提交的授權碼
            if 'code' in params:
                AuthCallbackHandler.auth_code = params['code'][0]
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"success": true}')
            else:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"success": false, "error": "missing code"}')
                
        elif path == '/callback':
            # Spotify OAuth 回調（如果 RPI 本機訪問會到這）
            if 'code' in params:
                AuthCallbackHandler.auth_code = params['code'][0]
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                
                success_html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <title>授權成功</title>
                    <style>
                        body {
                            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                            background: linear-gradient(135deg, #1DB954 0%, #191414 100%);
                            color: white;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            height: 100vh;
                            margin: 0;
                        }
                        .container { text-align: center; }
                        .checkmark { font-size: 80px; }
                        h1 { font-size: 24px; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="checkmark">✓</div>
                        <h1>授權成功！</h1>
                        <p>車機將自動完成連線</p>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(success_html.encode())
            else:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """關閉日誌輸出"""
        pass


class AuthSignals(QObject):
    """Qt 訊號類別"""
    auth_completed = pyqtSignal(bool)
    status_update = pyqtSignal(str)


class SpotifyQRAuthDialog(QWidget):
    """Spotify QR Code 授權對話框"""
    
    def __init__(self, auth_manager: SpotifyAuthManager):
        super().__init__()
        self.auth_manager = auth_manager
        self.signals = AuthSignals()
        self.server = None
        self.server_thread = None
        self.auth_success = False
        self._is_closing = False  # 標記是否正在關閉
        self.oauth = None  # 儲存 OAuth 管理器
        
        # 取得 RPI 的實際 IP
        self.local_ip = self.get_local_ip()
        
        # Spotify 只允許 loopback (127.0.0.1) 使用 HTTP
        # 所以 redirect_uri 必須用 127.0.0.1（手機上會失敗，但我們用 JS 攔截）
        self.redirect_uri = "http://127.0.0.1:8888/callback"
        
        self.init_ui()
        self.start_auth_flow()
    
    def get_local_ip(self):
        """取得本機 IP"""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    def create_qr_pixmap(self, data: str, size: int) -> QPixmap:
        """生成 QR Code 圖片"""
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
        
        qimage = QImage.fromData(buffer.read())
        pixmap = QPixmap.fromImage(qimage)
        
        return pixmap.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

    def init_ui(self):
        """初始化 UI"""
        self.setWindowTitle("Spotify 授權")
        self.setFixedSize(1920, 480)
        self.setStyleSheet("""
            QWidget {
                background-color: #121212;
                color: white;
                font-family: "Arial";
            }
            QLabel {
                color: #FFFFFF;
            }
            QPushButton {
                background-color: transparent;
                border: 2px solid #535353;
                border-radius: 25px;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 10px 30px;
            }
            QPushButton:hover {
                border-color: white;
                background-color: #2a2a2a;
            }
            QProgressBar {
                border: none;
                background-color: #2a2a2a;
                height: 4px;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #1DB954;
                border-radius: 2px;
            }
        """)
        
        # 主佈局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(60, 20, 60, 20)
        main_layout.setSpacing(40)
        
        # === 左側：說明區 ===
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setSpacing(15)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 標題
        title_layout = QHBoxLayout()
        logo_label = QLabel("🟢")
        logo_label.setFont(QFont("Arial", 32))
        title = QLabel("Spotify 連線")
        title.setFont(QFont("Arial", 36, QFont.Weight.Bold))
        title_layout.addWidget(logo_label)
        title_layout.addWidget(title)
        title_layout.addStretch()
        
        # 簡單說明
        desc_container = QWidget()
        desc_container.setStyleSheet("background-color: #181818; border-radius: 15px;")
        desc_layout = QVBoxLayout(desc_container)
        desc_layout.setContentsMargins(20, 20, 20, 20)
        desc_layout.setSpacing(12)
        
        step1 = QLabel("📱 用手機掃描右側 QR Code")
        step1.setFont(QFont("Arial", 18))
        step1.setStyleSheet("color: #FFFFFF;")
        
        step2 = QLabel("🔗 在手機上完成 Spotify 授權")
        step2.setFont(QFont("Arial", 18))
        step2.setStyleSheet("color: #FFFFFF;")
        
        step3 = QLabel("✅ 授權成功後車機會自動連線")
        step3.setFont(QFont("Arial", 18))
        step3.setStyleSheet("color: #FFFFFF;")
        
        desc_layout.addWidget(step1)
        desc_layout.addWidget(step2)
        desc_layout.addWidget(step3)
        
        # 首次設定提示
        first_time_hint = QLabel("⚠️ 首次使用需先在 Spotify Dashboard 設定 Redirect URI")
        first_time_hint.setFont(QFont("Arial", 12))
        first_time_hint.setStyleSheet("color: #FFA500;")
        first_time_hint.setWordWrap(True)
        
        redirect_uri_label = QLabel(f"Redirect URI: {self.redirect_uri}")
        redirect_uri_label.setFont(QFont("Arial", 11))
        redirect_uri_label.setStyleSheet("color: #888; background: rgba(255,255,255,0.05); padding: 8px; border-radius: 5px;")
        redirect_uri_label.setWordWrap(True)
        redirect_uri_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        # 狀態與進度
        self.status_label = QLabel("等待掃描...")
        self.status_label.setFont(QFont("Arial", 16))
        self.status_label.setStyleSheet("color: #1DB954;")
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        
        # 取消按鈕
        cancel_btn = QPushButton("取消")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setFixedWidth(150)
        cancel_btn.clicked.connect(self.cancel_auth)
        
        # 組合左側佈局
        left_layout.addLayout(title_layout)
        left_layout.addWidget(desc_container)
        left_layout.addWidget(first_time_hint)
        left_layout.addWidget(redirect_uri_label)
        left_layout.addStretch()
        left_layout.addWidget(self.status_label)
        left_layout.addWidget(self.progress)
        left_layout.addWidget(cancel_btn)
        
        # === 右側：Auth QR Code 區 ===
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.setSpacing(20)
        
        # QR Code 卡片背景
        qr_card = QWidget()
        qr_card.setFixedSize(280, 280)
        qr_card.setStyleSheet("""
            QWidget {
                background-color: white;
                border-radius: 16px;
            }
        """)
        
        qr_layout = QVBoxLayout(qr_card)
        qr_layout.setContentsMargins(10, 10, 10, 10)
        qr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setScaledContents(True)
        self.qr_label.setFixedSize(260, 260)
        qr_layout.addWidget(self.qr_label)
        
        # IP 提示標籤
        self.ip_label = QLabel("請先完成左側設定步驟")
        self.ip_label.setFont(QFont("Arial", 11))
        self.ip_label.setStyleSheet("""
            QLabel {
                color: #B3B3B3;
                background-color: #181818;
                padding: 8px 12px;
                border-radius: 10px;
            }
        """)
        self.ip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ip_label.setWordWrap(True)
        self.ip_label.setFixedWidth(350)
        
        right_layout.addWidget(qr_card)
        right_layout.addWidget(self.ip_label)
        
        # 加入主佈局
        main_layout.addWidget(left_container, 5)
        main_layout.addWidget(right_container, 5)
        
        # 連接訊號
        self.signals.auth_completed.connect(self.on_auth_completed)
        self.signals.status_update.connect(self.on_status_update)

    def start_auth_flow(self):
        """啟動授權流程"""
        try:
            # 先生成授權 URL（會設定 AuthCallbackHandler.auth_url）
            self.get_auth_url()
            
            # 設定 RPI IP 供 HTTP handler 使用
            AuthCallbackHandler.rpi_ip = self.local_ip
            
            # 啟動 HTTP 伺服器
            self.server_thread = threading.Thread(target=self.run_server, daemon=True)
            self.server_thread.start()
            
            # 生成 QR Code - 指向 RPI 的網頁（不是直接指向 Spotify）
            rpi_url = f"http://{self.local_ip}:8888/"
            self.generate_qr_code(rpi_url)
            
            # 更新提示文字
            self.ip_label.setText(f"用手機掃描 QR Code\n連接到 {rpi_url}")
            
            # 啟動檢查授權的定時器
            self.check_timer = QTimer()
            self.check_timer.timeout.connect(self.check_auth_status)
            self.check_timer.start(500)  # 每 0.5 秒檢查一次
            
        except Exception as e:
            # 初始化失敗
            self.signals.status_update.emit(f"初始化失敗: {e}")
            self.auth_success = False
            # 延遲關閉讓使用者看到錯誤訊息
            QTimer.singleShot(2000, self.cleanup_and_close)
    
    def run_server(self):
        """運行 HTTP 伺服器"""
        try:
            self.server = HTTPServer(('0.0.0.0', 8888), AuthCallbackHandler)
            # 檢查視窗是否已關閉
            if not self._is_closing:
                try:
                    self.signals.status_update.emit("伺服器已啟動,等待掃描...")
                except RuntimeError:
                    # 訊號對象已被刪除,視窗已關閉
                    return
            self.server.serve_forever()
        except Exception as e:
            # 檢查視窗是否已關閉
            if not self._is_closing:
                try:
                    self.signals.status_update.emit(f"伺服器錯誤: {e}")
                except RuntimeError:
                    # 訊號對象已被刪除,視窗已關閉
                    pass
    
    def get_auth_url(self) -> str:
        """取得授權 URL 並設定給 HTTP handler"""
        from spotipy.oauth2 import SpotifyOAuth
        
        # 檢查 config 是否存在
        if not self.auth_manager.config:
            raise ValueError("Spotify 配置檔未正確載入，請檢查 spotify_config.json")
        
        # 使用預先計算的 redirect_uri
        print(f"Redirect URI: {self.redirect_uri}")
        print(f"RPI IP: {self.local_ip}")
        
        # 更新 auth_manager 的 config
        self.auth_manager.config['redirect_uri'] = self.redirect_uri
        
        # 建立 OAuth 管理器並儲存
        self.oauth = SpotifyOAuth(
            client_id=self.auth_manager.config['client_id'],
            client_secret=self.auth_manager.config['client_secret'],
            redirect_uri=self.redirect_uri,
            scope=" ".join(self.auth_manager.SCOPES),
            cache_path=self.auth_manager.cache_path,
            open_browser=False,
            show_dialog=True
        )
        
        # 直接構建授權 URL，避免觸發 spotipy 的互動式提示
        import urllib.parse
        
        # 生成 state 參數（用於 CSRF 保護）
        if not self.oauth.state:
            import secrets
            self.oauth.state = secrets.token_urlsafe(16)
        
        params = {
            'client_id': self.oauth.client_id,
            'response_type': 'code',
            'redirect_uri': self.oauth.redirect_uri,
            'scope': self.oauth.scope,
            'show_dialog': 'true',
            'state': self.oauth.state
        }
        
        query_string = urllib.parse.urlencode(params)
        auth_url = f"{self.oauth.OAUTH_AUTHORIZE_URL}?{query_string}"
        
        # 設定給 HTTP handler 使用
        AuthCallbackHandler.auth_url = auth_url
        
        return auth_url
    
    def generate_qr_code(self, url: str):
        """生成 QR Code"""
        # 使用新的 helper method
        pixmap = self.create_qr_pixmap(url, 250)
        self.qr_label.setPixmap(pixmap)
    
    def check_auth_status(self):
        """檢查授權狀態"""
        if AuthCallbackHandler.auth_code:
            self.check_timer.stop()
            self.progress.show()
            self.signals.status_update.emit("授權成功！正在完成設定...")
            
            # 在背景執行緒完成授權
            threading.Thread(target=self.complete_auth, daemon=True).start()
    
    def complete_auth(self):
        """完成授權流程"""
        try:
            from spotipy import Spotify
            
            if not self.oauth:
                raise ValueError("OAuth 管理器未初始化")
            
            # 使用授權碼取得 token
            auth_code = AuthCallbackHandler.auth_code
            if not auth_code:
                raise ValueError("未取得授權碼")
            
            # 使用授權碼換取 access token
            token_info = self.oauth.get_access_token(auth_code, as_dict=True, check_cache=False)
            
            if not token_info:
                raise ValueError("無法取得 access token")
            
            # 更新 auth_manager
            self.auth_manager.auth_manager = self.oauth
            self.auth_manager.sp = Spotify(auth=token_info['access_token'])
            
            # 測試連線
            user = self.auth_manager.sp.current_user()
            logger.info(f"成功認證 Spotify 使用者: {user.get('display_name', 'Unknown')}")
            
            time.sleep(1)  # 給使用者看到成功訊息的時間
            self.signals.auth_completed.emit(True)
            
        except Exception as e:
            logger.error(f"完成授權失敗: {e}")
            self.signals.status_update.emit(f"授權失敗: {e}")
            self.signals.auth_completed.emit(False)
    
    def on_auth_completed(self, success: bool):
        """授權完成"""
        self.auth_success = success
        self.cleanup_and_close()
    
    def on_status_update(self, message: str):
        """更新狀態文字"""
        self.status_label.setText(message)
    
    def cancel_auth(self):
        """取消授權"""
        self.cleanup_and_close()
    
    def cleanup_and_close(self):
        """清理資源並關閉視窗"""
        self._is_closing = True
        
        # 停止檢查計時器
        if hasattr(self, 'check_timer'):
            self.check_timer.stop()
        
        # 在背景執行緒中關閉伺服器,避免阻塞 UI
        if self.server:
            def shutdown_server():
                try:
                    self.server.shutdown()
                    self.server.server_close()
                except:
                    pass
            
            threading.Thread(target=shutdown_server, daemon=True).start()
        
        # 關閉視窗
        self.close()
    
    def closeEvent(self, event):
        """關閉事件"""
        if not self._is_closing:
            self.cleanup_and_close()
        event.accept()


def show_qr_auth_dialog(auth_manager: SpotifyAuthManager = None) -> bool:
    """
    顯示 QR Code 授權對話框
    
    Args:
        auth_manager: SpotifyAuthManager 實例，若為 None 則自動建立
        
    Returns:
        bool: 授權是否成功
    """
    if not auth_manager:
        auth_manager = SpotifyAuthManager()
    
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    dialog = SpotifyQRAuthDialog(auth_manager)
    dialog.show()
    
    app.exec()
    
    return dialog.auth_success


def main():
    """測試 QR Code 授權介面"""
    print("=== Spotify QR Code 授權測試 ===")
    print()
    print("視窗將顯示 QR Code")
    print("請使用手機掃描 QR Code 並完成授權")
    print()
    
    success = show_qr_auth_dialog()
    
    if success:
        print("✅ 授權成功！")
        print("您現在可以使用 Spotify 整合功能")
    else:
        print("❌ 授權失敗或已取消")


if __name__ == '__main__':
    main()
