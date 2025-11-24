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
                              QHBoxLayout, QPushButton, QProgressBar, QStackedWidget)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap, QImage, QFont

from spotify_auth import SpotifyAuthManager

logger = logging.getLogger(__name__)


class AuthCallbackHandler(BaseHTTPRequestHandler):
    """處理 OAuth 回調的 HTTP 伺服器"""
    
    auth_code = None
    
    def do_GET(self):
        """處理 GET 請求"""
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        if 'code' in params:
            AuthCallbackHandler.auth_code = params['code'][0]
            
            # 回傳成功頁面
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
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                        background: linear-gradient(135deg, #1DB954 0%, #191414 100%);
                        color: white;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                    }
                    .container {
                        text-align: center;
                        background: rgba(0,0,0,0.5);
                        padding: 40px;
                        border-radius: 20px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.5);
                    }
                    h1 { font-size: 48px; margin: 0 0 20px 0; }
                    p { font-size: 20px; opacity: 0.8; }
                    .checkmark {
                        font-size: 80px;
                        color: #1DB954;
                        margin-bottom: 20px;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="checkmark">✓</div>
                    <h1>授權成功！</h1>
                    <p>您可以關閉此頁面，回到車機繼續操作</p>
                </div>
                <script>
                    setTimeout(() => window.close(), 3000);
                </script>
            </body>
            </html>
            """
            self.wfile.write(success_html.encode())
        else:
            self.send_response(400)
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
        
        # 預先取得 IP 和 Redirect URI
        self.local_ip = self.get_local_ip()
        self.redirect_uri = f"http://{self.local_ip}:8888/callback"
        
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
        
        # === 左側：資訊切換區 ===
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setSpacing(10)
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
        
        # Stacked Widget 用於切換內容
        self.info_stack = QStackedWidget()
        
        # 頁面 1: Redirect URI QR
        page1 = QWidget()
        p1_layout = QHBoxLayout(page1)
        p1_layout.setContentsMargins(0, 0, 0, 0)
        p1_layout.setSpacing(20)
        
        # 左側：標題 + 說明文字
        p1_left_container = QWidget()
        p1_left_layout = QVBoxLayout(p1_left_container)
        p1_left_layout.setContentsMargins(0, 0, 0, 0)
        p1_left_layout.setSpacing(10)
        p1_left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        p1_title = QLabel("步驟 1/3: 設定 Redirect URI")
        p1_title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        p1_title.setStyleSheet("color: #1DB954;")
        
        p1_desc = QLabel("請掃描右側 QR Code 複製網址，\n並新增至 Spotify Dashboard 的 Redirect URIs")
        p1_desc.setFont(QFont("Arial", 16))
        p1_desc.setStyleSheet("color: #B3B3B3;")
        p1_desc.setWordWrap(True)
        
        p1_url = QLabel(self.redirect_uri)
        p1_url.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        p1_url.setStyleSheet("color: #FFFF00; background: rgba(255,255,255,0.1); padding: 8px; border-radius: 5px;")
        p1_url.setWordWrap(True)
        
        p1_left_layout.addWidget(p1_title)
        p1_left_layout.addWidget(p1_desc)
        p1_left_layout.addSpacing(10)
        p1_left_layout.addWidget(p1_url)
        p1_left_layout.addStretch()
        
        # 右側：QR Code
        p1_qr_container = QWidget()
        p1_qr_container.setStyleSheet("background-color: white; border-radius: 10px;")
        p1_qr_container.setFixedSize(200, 200)
        p1_qr_layout = QVBoxLayout(p1_qr_container)
        p1_qr_layout.setContentsMargins(5, 5, 5, 5)
        p1_qr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        p1_qr_label = QLabel()
        p1_qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p1_qr_label.setScaledContents(True)
        p1_qr_label.setFixedSize(190, 190)
        p1_qr_label.setPixmap(self.create_qr_pixmap(self.redirect_uri, 190))
        p1_qr_layout.addWidget(p1_qr_label)
        
        p1_layout.addWidget(p1_left_container)
        p1_layout.addWidget(p1_qr_container)
        p1_layout.addStretch()
        
        # 頁面 2: Dashboard Link
        page2 = QWidget()
        p2_layout = QHBoxLayout(page2)
        p2_layout.setContentsMargins(0, 0, 0, 0)
        p2_layout.setSpacing(20)
        
        # 左側：標題 + 說明文字
        p2_left_container = QWidget()
        p2_left_layout = QVBoxLayout(p2_left_container)
        p2_left_layout.setContentsMargins(0, 0, 0, 0)
        p2_left_layout.setSpacing(10)
        p2_left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        p2_title = QLabel("步驟 2/3: 前往 Dashboard")
        p2_title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        p2_title.setStyleSheet("color: #1DB954;")
        
        p2_desc = QLabel("掃描右側 QR Code 前往\nSpotify Developer Dashboard 進行設定")
        p2_desc.setFont(QFont("Arial", 16))
        p2_desc.setStyleSheet("color: #B3B3B3;")
        p2_desc.setWordWrap(True)
        
        p2_left_layout.addWidget(p2_title)
        p2_left_layout.addWidget(p2_desc)
        p2_left_layout.addStretch()

        # 右側：QR Code
        p2_qr_container = QWidget()
        p2_qr_container.setStyleSheet("background-color: white; border-radius: 10px;")
        p2_qr_container.setFixedSize(200, 200)
        p2_qr_layout = QVBoxLayout(p2_qr_container)
        p2_qr_layout.setContentsMargins(5, 5, 5, 5)
        p2_qr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        dashboard_url = "https://developer.spotify.com/dashboard"
        p2_qr_label = QLabel()
        p2_qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p2_qr_label.setScaledContents(True)
        p2_qr_label.setFixedSize(190, 190)
        p2_qr_label.setPixmap(self.create_qr_pixmap(dashboard_url, 190))
        p2_qr_layout.addWidget(p2_qr_label)
        
        p2_layout.addWidget(p2_left_container)
        p2_layout.addWidget(p2_qr_container)
        p2_layout.addStretch()
        
        # 頁面 3: 授權說明
        page3 = QWidget()
        p3_layout = QVBoxLayout(page3)
        p3_layout.setContentsMargins(0, 0, 0, 0)
        
        p3_title = QLabel("步驟 3/3: 進行授權")
        p3_title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        p3_title.setStyleSheet("color: #1DB954;")
        
        steps_container = QWidget()
        steps_container.setStyleSheet("background-color: #181818; border-radius: 10px;")
        steps_layout = QVBoxLayout(steps_container)
        steps_layout.setContentsMargins(15, 15, 15, 15)
        steps_layout.setSpacing(5)
        
        step1 = QLabel("1. 開啟手機相機")
        step2 = QLabel("2. 掃描右側 QR Code")
        step3 = QLabel("3. 同意授權")
        
        for step in [step1, step2, step3]:
            step.setFont(QFont("Arial", 16))
            step.setStyleSheet("color: #FFFFFF;")
            steps_layout.addWidget(step)
            
        p3_layout.addWidget(p3_title)
        p3_layout.addWidget(steps_container)
        p3_layout.addSpacing(20)
        
        # 加入頁面到 Stack
        self.info_stack.addWidget(page1)
        self.info_stack.addWidget(page2)
        self.info_stack.addWidget(page3)
        
        # 切換按鈕
        self.toggle_btn = QPushButton("下一步")
        self.toggle_btn.setFixedWidth(150)
        self.toggle_btn.clicked.connect(self.toggle_info_view)
        
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
        left_layout.addWidget(self.info_stack)
        left_layout.addWidget(self.toggle_btn)
        left_layout.addSpacing(10)
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
        
        # 預設顯示第一頁
        self.info_stack.setCurrentIndex(0)
    
    def toggle_info_view(self):
        """切換資訊頁面"""
        current = self.info_stack.currentIndex()
        next_idx = (current + 1) % self.info_stack.count()
        self.info_stack.setCurrentIndex(next_idx)
        
        # 更新按鈕文字
        if next_idx == 2:  # 最後一步
            self.toggle_btn.setText("回到第一步")
        else:
            self.toggle_btn.setText("下一步")

    def start_auth_flow(self):
        """啟動授權流程"""
        try:
            # 啟動 HTTP 伺服器
            self.server_thread = threading.Thread(target=self.run_server, daemon=True)
            self.server_thread.start()
            
            # 生成授權 URL
            auth_url = self.get_auth_url()
            
            # 生成 QR Code
            self.generate_qr_code(auth_url)
            
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
        """取得授權 URL"""
        from spotipy.oauth2 import SpotifyOAuth
        
        # 檢查 config 是否存在
        if not self.auth_manager.config:
            raise ValueError("Spotify 配置檔未正確載入，請檢查 spotify_config.json")
        
        # 使用預先計算的 redirect_uri
        print(f"Redirect URI: {self.redirect_uri}")
        
        # 更新 auth_manager 的 config
        self.auth_manager.config['redirect_uri'] = self.redirect_uri
        
        # 更新 UI 提示
        if hasattr(self, 'ip_label'):
            msg = f"Redirect URI: {self.redirect_uri}"
            self.ip_label.setText(msg)
        
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
        return f"{self.oauth.OAUTH_AUTHORIZE_URL}?{query_string}"
    
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
