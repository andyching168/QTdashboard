#!/usr/bin/env python3
"""
啟動進度視窗 - 在 Splash 影片播放前顯示系統初始化進度

使用方式（命令列模式）：
    # 啟動進度視窗服務（背景執行）
    python startup_progress.py --serve &
    
    # 更新進度
    python startup_progress.py --update "訊息" "詳細" 進度百分比
    
    # 關閉視窗
    python startup_progress.py --close
"""

import sys
import os
import time
import socket
import json
import threading

# === 垂直同步 (VSync) 設定 ===
# 針對 480x1920 直式螢幕旋轉 90 度使用 (1920x480)
os.environ.setdefault('QSG_RENDER_LOOP', 'basic')
os.environ.setdefault('QT_QPA_EGLFS_FORCE_VSYNC', '1')

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QProgressBar
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QFont


# IPC 通訊設定
IPC_SOCKET_PATH = "/tmp/qtdashboard_startup_progress.sock"


class StartupProgressWindow(QWidget):
    """啟動進度視窗"""
    
    # 信號：所有步驟完成
    finished = pyqtSignal()
    
    # 信號：更新進度（用於跨執行緒更新）
    update_signal = pyqtSignal(str, str, int)
    close_signal = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        
        # 設置為全螢幕無邊框
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        # 設置黑色背景
        self.setStyleSheet("background-color: #0a0a10;")
        
        # 初始化 UI
        self._init_ui()
        
        # 當前步驟
        self.current_step = 0
        self.steps = []
        
        # 連接信號
        self.update_signal.connect(self._do_update)
        self.close_signal.connect(self._do_close)
        
    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setSpacing(20)
        
        # 上方留空
        layout.addStretch(2)
        
        # 標題
        self.title_label = QLabel("🚗 Luxgen M7 儀表板")
        self.title_label.setStyleSheet("""
            color: #6af;
            font-size: 32px;
            font-weight: bold;
        """)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)
        
        layout.addSpacing(30)
        
        # 當前狀態
        self.status_label = QLabel("正在初始化...")
        self.status_label.setStyleSheet("""
            color: white;
            font-size: 20px;
        """)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        layout.addSpacing(20)
        
        # 進度條
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: #2a2a35;
                border-radius: 10px;
                border: 2px solid #3a3a45;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a9eff, stop:1 #6af);
                border-radius: 8px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # 詳細資訊
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("""
            color: #666;
            font-size: 14px;
        """)
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.detail_label)
        
        # 下方留空
        layout.addStretch(3)
        
        # 版權/提示
        footer_label = QLabel("系統啟動中，請稍候...")
        footer_label.setStyleSheet("""
            color: #444;
            font-size: 12px;
        """)
        footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer_label)
    
    def set_steps(self, steps):
        """設置步驟列表
        
        Args:
            steps: list of (step_name, detail_text) tuples
        """
        self.steps = steps
        self.current_step = 0
        self.progress_bar.setMaximum(len(steps))
        self.progress_bar.setValue(0)
    
    def show_step(self, step_index, status_text=None, detail_text=None):
        """顯示指定步驟
        
        Args:
            step_index: 步驟索引 (0-based)
            status_text: 狀態文字（可選，不提供則使用步驟名稱）
            detail_text: 詳細資訊（可選）
        """
        self.current_step = step_index
        
        if step_index < len(self.steps):
            step_name, default_detail = self.steps[step_index]
            self.status_label.setText(status_text or step_name)
            self.detail_label.setText(detail_text or default_detail)
        else:
            self.status_label.setText(status_text or "完成")
            self.detail_label.setText(detail_text or "")
        
        # 更新進度條（百分比）
        progress = int((step_index + 1) / len(self.steps) * 100) if self.steps else 0
        self.progress_bar.setValue(progress)
        
        # 強制更新 UI
        QApplication.processEvents()
    
    def update_progress(self, message, detail="", progress=0):
        """更新進度（通用介面）"""
        self.status_label.setText(message)
        self.detail_label.setText(detail)
        self.progress_bar.setValue(min(100, max(0, progress)))
        QApplication.processEvents()
    
    def _do_update(self, message, detail, progress):
        """執行更新（在主執行緒中）"""
        self.update_progress(message, detail, progress)
    
    def _do_close(self):
        """執行關閉（在主執行緒中）"""
        self.complete()
    
    def advance_step(self, status_text=None, detail_text=None):
        """前進到下一步"""
        self.show_step(self.current_step + 1, status_text, detail_text)
    
    def complete(self):
        """完成所有步驟"""
        self.progress_bar.setValue(100)
        self.status_label.setText("✅ 啟動完成")
        self.detail_label.setText("正在載入儀表板...")
        QApplication.processEvents()
        
        # 延遲關閉
        QTimer.singleShot(500, self._finish_and_close)
    
    def _finish_and_close(self):
        """實際關閉視窗"""
        self.finished.emit()
        self.close()
    
    def keyPressEvent(self, a0):
        """按任意鍵跳過"""
        if a0 and a0.key() == Qt.Key.Key_Escape:
            self.complete()


class IPCServer(QThread):
    """IPC 伺服器執行緒 - 接收來自 shell 腳本的訊息"""
    
    update_received = pyqtSignal(str, str, int)
    close_received = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.running = True
    
    def run(self):
        """執行伺服器"""
        # 清理舊的 socket
        if os.path.exists(IPC_SOCKET_PATH):
            os.remove(IPC_SOCKET_PATH)
        
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(IPC_SOCKET_PATH)
        server.listen(1)
        server.settimeout(0.5)  # 設定超時以便能檢查 running 狀態
        
        while self.running:
            try:
                conn, _ = server.accept()
                data = conn.recv(1024).decode('utf-8')
                conn.close()
                
                if data:
                    try:
                        msg = json.loads(data)
                        cmd = msg.get('cmd', '')
                        
                        if cmd == 'update':
                            self.update_received.emit(
                                msg.get('message', ''),
                                msg.get('detail', ''),
                                msg.get('progress', 0)
                            )
                        elif cmd == 'close':
                            self.close_received.emit()
                            self.running = False
                    except json.JSONDecodeError:
                        pass
            except socket.timeout:
                continue
            except Exception as e:
                print(f"IPC 錯誤: {e}")
        
        server.close()
        if os.path.exists(IPC_SOCKET_PATH):
            os.remove(IPC_SOCKET_PATH)
    
    def stop(self):
        """停止伺服器"""
        self.running = False


def send_ipc_message(msg):
    """發送 IPC 訊息"""
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(IPC_SOCKET_PATH)
        client.send(json.dumps(msg).encode('utf-8'))
        client.close()
        return True
    except Exception as e:
        print(f"IPC 發送失敗: {e}")
        return False


def run_server_mode():
    """伺服器模式 - 顯示視窗並等待 IPC 命令"""
    app = QApplication(sys.argv)
    
    window = StartupProgressWindow()
    
    # 啟動 IPC 伺服器
    ipc_server = IPCServer()
    ipc_server.update_received.connect(window.update_signal.emit)
    ipc_server.close_received.connect(window.close_signal.emit)
    ipc_server.start()
    
    # 關閉時停止伺服器
    def on_finished():
        ipc_server.stop()
        ipc_server.wait()
        app.quit()
    
    window.finished.connect(on_finished)
    
    # 顯示視窗
    window.showFullScreen()
    window.update_progress("🚗 系統啟動中...", "請稍候", 0)
    
    # 設定超時（30秒後自動關閉）
    QTimer.singleShot(30000, window.complete)
    
    sys.exit(app.exec())


def run_update_command(message, detail, progress):
    """發送更新命令"""
    return send_ipc_message({
        'cmd': 'update',
        'message': message,
        'detail': detail,
        'progress': progress
    })


def run_close_command():
    """發送關閉命令"""
    return send_ipc_message({'cmd': 'close'})


def main():
    """主程式"""
    import argparse
    
    parser = argparse.ArgumentParser(description='啟動進度視窗')
    parser.add_argument('--serve', action='store_true', help='啟動伺服器模式')
    parser.add_argument('--update', nargs=3, metavar=('MESSAGE', 'DETAIL', 'PROGRESS'),
                        help='更新進度 (訊息 詳細 百分比)')
    parser.add_argument('--close', action='store_true', help='關閉視窗')
    parser.add_argument('--test', action='store_true', help='測試模式')
    
    args = parser.parse_args()
    
    if args.serve:
        run_server_mode()
    elif args.update:
        message, detail, progress = args.update
        run_update_command(message, detail, int(progress))
    elif args.close:
        run_close_command()
    elif args.test:
        # 測試模式
        app = QApplication(sys.argv)
        
        window = StartupProgressWindow()
        
        steps = [
            ("📺 設定螢幕顯示", "旋轉螢幕 90°"),
            ("👆 校正觸控面板", "USB2IIC_CTP_CONTROL"),
            ("🔋 設定電源管理", "禁用螢幕保護"),
            ("🪟 啟動視窗管理器", "openbox"),
            ("🔊 初始化音訊服務", "PipeWire"),
            ("🐍 啟動 Python 環境", "載入虛擬環境"),
            ("🌐 檢查網路連線", "NTP 時間校正"),
            ("🔌 掃描 CAN Bus 裝置", "偵測 CANable"),
            ("🎵 檢查 Spotify 設定", "授權狀態"),
        ]
        
        window.set_steps(steps)
        window.resize(800, 200)
        window.show()
        
        # 模擬步驟執行
        step_index = [0]
        
        def next_step():
            if step_index[0] < len(steps):
                window.show_step(step_index[0])
                step_index[0] += 1
                QTimer.singleShot(400, next_step)
            else:
                window.complete()
        
        QTimer.singleShot(100, next_step)
        window.finished.connect(app.quit)
        
        sys.exit(app.exec())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
