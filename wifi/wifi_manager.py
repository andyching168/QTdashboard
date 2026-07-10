#!/usr/bin/env python3
"""
WiFi 管理器 - 用於樹莓派的觸控友好介面
支援掃描、連線、儲存設定
"""

import subprocess
import re
import json
import os
import threading
import time
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QListWidget, QListWidgetItem, 
                             QLineEdit, QDialog, QMessageBox, QProgressBar,
                             QCheckBox, QGridLayout, QScroller, QScrollerProperties,
                             QAbstractItemView)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QFont


class VirtualKeyboard(QWidget):
    """內建虛擬鍵盤"""
    
    key_pressed = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.caps_lock = False
        self.key_buttons: list[QPushButton] = []  # 保存所有按鍵的引用
        self.caps_button: QPushButton | None = None  # Caps Lock 按鈕
        self.setup_ui()
    
    def setup_ui(self):
        """設置鍵盤 UI"""
        self.setStyleSheet("""
            QPushButton {
                background-color: #2a2a35;
                color: white;
                border: 1px solid #4a4a55;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
                min-height: 45px;
            }
            QPushButton:hover {
                background-color: #3a3a45;
            }
            QPushButton:pressed {
                background-color: #1a1a25;
            }
            QPushButton#specialKey {
                background-color: #4a4a55;
                font-size: 14px;
            }
            QPushButton#specialKey:hover {
                background-color: #5a5a65;
            }
            QPushButton#capsActive {
                background-color: #6af;
                color: white;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton#capsActive:hover {
                background-color: #5ae;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(3)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 鍵盤佈局 - 每個按鍵包含 [小寫/普通, 大寫/符號]
        self.keyboard_layout = [
            [('1', '!'), ('2', '@'), ('3', '#'), ('4', '$'), ('5', '%'), 
             ('6', '^'), ('7', '&'), ('8', '*'), ('9', '('), ('0', ')'), 
             ('-', '_'), ('=', '+')],
            [('q', 'Q'), ('w', 'W'), ('e', 'E'), ('r', 'R'), ('t', 'T'), 
             ('y', 'Y'), ('u', 'U'), ('i', 'I'), ('o', 'O'), ('p', 'P'), 
             ('[', '{'), (']', '}')],
            [('a', 'A'), ('s', 'S'), ('d', 'D'), ('f', 'F'), ('g', 'G'), 
             ('h', 'H'), ('j', 'J'), ('k', 'K'), ('l', 'L'), (';', ':'), 
             ("'", '"')],
            [('z', 'Z'), ('x', 'X'), ('c', 'C'), ('v', 'V'), ('b', 'B'), 
             ('n', 'N'), ('m', 'M'), (',', '<'), ('.', '>'), ('/', '?')],
        ]
        
        # 創建按鍵
        for row in self.keyboard_layout:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(3)
            
            for key_pair in row:
                normal_key, shift_key = key_pair
                btn = QPushButton(normal_key)
                btn.setProperty('key_pair', key_pair)  # 保存按鍵對 (普通, Caps/Shift)
                btn.clicked.connect(lambda checked, kp=key_pair: self.on_key_click(kp))
                row_layout.addWidget(btn)
                self.key_buttons.append(btn)  # 保存按鈕引用
            
            layout.addLayout(row_layout)
        
        # 最後一行：特殊按鍵
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(3)
        
        # Caps Lock
        self.caps_button = QPushButton("⇪ Caps Lock")
        self.caps_button.setObjectName("specialKey")
        self.caps_button.clicked.connect(self.toggle_caps)
        bottom_layout.addWidget(self.caps_button)
        
        # 空格鍵
        space_btn = QPushButton("Space")
        space_btn.setObjectName("specialKey")
        space_btn.clicked.connect(lambda: self.key_pressed.emit(' '))
        bottom_layout.addWidget(space_btn, 3)  # 空格鍵較寬
        
        # 退格鍵
        backspace_btn = QPushButton("⌫ Back")
        backspace_btn.setObjectName("specialKey")
        backspace_btn.clicked.connect(lambda: self.key_pressed.emit('BACKSPACE'))
        bottom_layout.addWidget(backspace_btn)
        
        # 清除鍵
        clear_btn = QPushButton("✖ Clear")
        clear_btn.setObjectName("specialKey")
        clear_btn.clicked.connect(lambda: self.key_pressed.emit('CLEAR'))
        bottom_layout.addWidget(clear_btn)
        
        layout.addLayout(bottom_layout)
    
    def on_key_click(self, key_pair):
        """按鍵點擊"""
        normal_key, shift_key = key_pair
        # 根據 Caps Lock 狀態選擇對應的字符
        key_to_emit = shift_key if self.caps_lock else normal_key
        self.key_pressed.emit(key_to_emit)
    
    def toggle_caps(self):
        """切換大小寫/符號模式"""
        self.caps_lock = not self.caps_lock
        
        # 更新所有按鍵的顯示文字
        for btn in self.key_buttons:
            key_pair = btn.property('key_pair')
            if key_pair:
                normal_key, shift_key = key_pair
                if self.caps_lock:
                    btn.setText(shift_key)
                else:
                    btn.setText(normal_key)
        
        # 更新 Caps Lock 按鈕樣式和文字
        if self.caps_button is None:
            return
            
        if self.caps_lock:
            self.caps_button.setObjectName("capsActive")
            self.caps_button.setText("⇪ SHIFT ON")
        else:
            self.caps_button.setObjectName("specialKey")
            self.caps_button.setText("⇪ Shift")
        
        # 刷新樣式
        style = self.caps_button.style()
        if style:
            style.unpolish(self.caps_button)
            style.polish(self.caps_button)


class CancellableProcessThread(QThread):
    """可在視窗關閉時終止目前 subprocess 的 QThread。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancel_event = threading.Event()
        self._process = None
        self._process_lock = threading.Lock()

    def cancel(self):
        self._cancel_event.set()
        self.requestInterruption()
        with self._process_lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

    def _wait(self, seconds):
        return self._cancel_event.wait(seconds)

    def _run_command(self, args, *, timeout, text=False, env=None):
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            env=env,
        )
        with self._process_lock:
            self._process = process
        started = time.monotonic()
        try:
            while True:
                if self._cancel_event.is_set():
                    process.terminate()
                    raise InterruptedError("WiFi operation cancelled")
                try:
                    stdout, stderr = process.communicate(timeout=0.1)
                    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    if time.monotonic() - started >= timeout:
                        process.kill()
                        stdout, stderr = process.communicate()
                        raise subprocess.TimeoutExpired(args, timeout, stdout, stderr)
        finally:
            with self._process_lock:
                self._process = None


class WiFiScanner(CancellableProcessThread):
    """WiFi 掃描執行緒"""
    scan_completed = pyqtSignal(list)
    
    def run(self):
        """掃描可用的 WiFi 網路"""
        try:
            # 先執行重新掃描（需要 root 權限或 polkit 授權）
            self._run_command(
                ['nmcli', 'dev', 'wifi', 'rescan'],
                timeout=10
            )
            # 等待掃描完成
            if self._wait(2):
                return
            
            # 使用 nmcli 列出 WiFi（--rescan yes 會自動重新掃描）
            result = self._run_command(
                ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list', '--rescan', 'yes'],
                text=True,
                timeout=15
            )
            
            networks = []
            seen_ssids = set()  # 用於去重
            
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split(':')
                    if len(parts) >= 3:
                        ssid = parts[0]
                        signal = parts[1]
                        security = parts[2]
                        
                        # 忽略隱藏的 SSID 和重複的 SSID
                        if ssid and ssid not in seen_ssids:
                            seen_ssids.add(ssid)
                            networks.append({
                                'ssid': ssid,
                                'signal': int(signal) if signal.isdigit() else 0,
                                'security': security,
                                'secured': 'WPA' in security or 'WEP' in security
                            })
            
            # 按信號強度排序
            networks.sort(key=lambda x: x['signal'], reverse=True)
            self.scan_completed.emit(networks)
            
        except InterruptedError:
            return
        except Exception as e:
            print(f"WiFi 掃描錯誤: {e}")
            self.scan_completed.emit([])


class WiFiConnector(CancellableProcessThread):
    """WiFi 連線執行緒

    nmcli 連線流程的 subprocess 逾時最壞可累計約 90 秒，
    必須在背景執行緒執行，否則會凍結整個 UI。
    """
    connect_finished = pyqtSignal(bool, str, str)  # success, ssid, error_msg

    def __init__(self, ssid, password=None, test_mode=False, parent=None):
        super().__init__(parent)
        self.ssid = ssid
        self.password = password
        self.test_mode = test_mode

    def run(self):
        ssid = self.ssid
        password = self.password
        try:
            if self.test_mode:
                # 測試模式：模擬連線
                print(f"測試模式：模擬連線到 {ssid}" + (f" (密碼: {password})" if password else ""))
                if self._wait(2):
                    return

                class MockResult:
                    returncode = 0
                    stderr = ''
                result = MockResult()
            else:
                # 設置環境變數確保英文輸出
                env = os.environ.copy()
                env['LANG'] = 'C'
                env['LC_ALL'] = 'C'

                # 先檢查是否已有此網路的連線設定
                check_result = self._run_command(
                    ['nmcli', '-t', '-f', 'NAME', 'con', 'show'],
                    text=True, timeout=5, env=env
                )
                existing_connections = check_result.stdout.strip().split('\n')

                if ssid in existing_connections:
                    # 已有連線設定，先刪除舊設定再重新連線（避免 key-mgmt 問題）
                    print(f"找到現有連線設定: {ssid}，刪除舊設定...")
                    self._run_command(['nmcli', 'con', 'delete', ssid], timeout=10, env=env)

                # 建立新連線
                if password:
                    # 方法 1：嘗試使用標準 wifi connect 命令
                    cmd = ['nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password]
                    print(f"嘗試連線: {' '.join(cmd[:5])} ****")
                    result = self._run_command(cmd, text=True, timeout=30, env=env)

                    # 如果失敗，嘗試方法 2：手動建立連線設定
                    if result.returncode != 0 and 'key-mgmt' in result.stderr.lower():
                        print(f"標準連線失敗，嘗試手動建立連線設定...")

                        # 刪除可能殘留的設定
                        self._run_command(['nmcli', 'con', 'delete', ssid], timeout=10, env=env)

                        # 使用 nmcli connection add 建立連線，明確指定 key-mgmt
                        add_cmd = [
                            'nmcli', 'con', 'add',
                            'type', 'wifi',
                            'con-name', ssid,
                            'ssid', ssid,
                            'wifi-sec.key-mgmt', 'wpa-psk',
                            'wifi-sec.psk', password
                        ]
                        add_result = self._run_command(add_cmd, text=True, timeout=15, env=env)

                        if add_result.returncode == 0:
                            # 啟用連線
                            result = self._run_command(
                                ['nmcli', 'con', 'up', ssid],
                                text=True, timeout=30, env=env
                            )
                        else:
                            result = add_result
                else:
                    # 連線到開放網路
                    cmd = ['nmcli', 'dev', 'wifi', 'connect', ssid]
                    result = self._run_command(cmd, text=True, timeout=30, env=env)

            if result.returncode == 0:
                self.connect_finished.emit(True, ssid, '')
            else:
                error_msg = result.stderr or result.stdout or "連線失敗"
                self.connect_finished.emit(False, ssid, error_msg)

        except InterruptedError:
            return
        except subprocess.TimeoutExpired:
            self.connect_finished.emit(False, ssid, 'timeout: 連線逾時，請重試')

        except Exception as e:
            self.connect_finished.emit(False, ssid, f'exception: {str(e)}')


class WiFiStatusChecker(CancellableProcessThread):
    status_ready = pyqtSignal(object)

    def run(self):
        env = os.environ.copy()
        env['LANG'] = 'C'
        env['LC_ALL'] = 'C'
        try:
            result = self._run_command(
                ['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'],
                text=True,
                timeout=2,
                env=env,
            )
            ssid = None
            for line in result.stdout.strip().split('\n'):
                if line.startswith('yes:') or line.startswith('是:'):
                    candidate = line.split(':', 1)[1]
                    if candidate:
                        ssid = candidate
                        break
            self.status_ready.emit(ssid)
        except InterruptedError:
            return
        except Exception:
            self.status_ready.emit(None)


class WiFiPasswordDialog(QDialog):
    """WiFi 密碼輸入對話框"""
    
    def __init__(self, ssid, parent=None):
        super().__init__(parent)
        self.ssid = ssid
        self.password = None
        self.remember = False
        
        self.setWindowTitle(f"連線到 {ssid}")
        self.setModal(True)
        self.setFixedSize(1920, 480)  # 橫向佈局
        
        # 設置樣式
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a25;
            }
            QLabel {
                color: white;
                font-size: 16px;
            }
            QLineEdit {
                background-color: #2a2a35;
                color: white;
                border: 2px solid #4a4a55;
                border-radius: 10px;
                padding: 15px;
                font-size: 18px;
            }
            QLineEdit:focus {
                border: 2px solid #6af;
            }
            QPushButton {
                background-color: #6af;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 15px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5ae;
            }
            QPushButton:pressed {
                background-color: #49d;
            }
            QPushButton#cancelButton {
                background-color: #666;
            }
            QPushButton#cancelButton:hover {
                background-color: #777;
            }
            QCheckBox {
                color: white;
                font-size: 14px;
            }
            QCheckBox::indicator {
                width: 25px;
                height: 25px;
            }
        """)
        
        # 主佈局：橫向分為左右兩區
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 20, 30, 20)
        
        # === 左側區域：資訊和輸入框 ===
        left_layout = QVBoxLayout()
        left_layout.setSpacing(20)
        
        # 標題
        title_label = QLabel(f"WiFi 密碼輸入")
        title_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #6af;")
        left_layout.addWidget(title_label)
        
        # SSID 顯示
        ssid_container = QVBoxLayout()
        ssid_title = QLabel("網路名稱")
        ssid_title.setStyleSheet("color: #aaa; font-size: 14px;")
        ssid_container.addWidget(ssid_title)
        
        ssid_label = QLabel(ssid)
        ssid_label.setStyleSheet("color: white; font-size: 24px; font-weight: bold;")
        ssid_container.addWidget(ssid_label)
        left_layout.addLayout(ssid_container)
        
        left_layout.addSpacing(20)
        
        # 密碼輸入框
        pwd_title = QLabel("密碼")
        pwd_title.setStyleSheet("color: #aaa; font-size: 14px;")
        left_layout.addWidget(pwd_title)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("使用右側鍵盤輸入密碼")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setReadOnly(True)  # 防止實體鍵盤輸入
        self.password_input.setFixedHeight(60)
        self.password_input.setStyleSheet("font-size: 22px; padding: 15px;")
        left_layout.addWidget(self.password_input)
        
        left_layout.addSpacing(20)
        
        # 選項
        self.show_password_checkbox = QCheckBox("顯示密碼")
        self.show_password_checkbox.setStyleSheet("font-size: 16px;")
        self.show_password_checkbox.stateChanged.connect(self.toggle_password_visibility)
        left_layout.addWidget(self.show_password_checkbox)
        
        self.remember_checkbox = QCheckBox("記住此網路")
        self.remember_checkbox.setStyleSheet("font-size: 16px;")
        self.remember_checkbox.setChecked(True)
        left_layout.addWidget(self.remember_checkbox)
        
        left_layout.addStretch()
        
        # 按鈕
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancelButton")
        cancel_btn.setFixedSize(200, 60)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        connect_btn = QPushButton("連線")
        connect_btn.setFixedSize(200, 60)
        connect_btn.clicked.connect(self.accept_password)
        button_layout.addWidget(connect_btn)
        
        left_layout.addLayout(button_layout)
        
        main_layout.addLayout(left_layout, 2)  # 左側佔 2/5
        
        # === 右側區域：虛擬鍵盤 ===
        self.keyboard = VirtualKeyboard()
        self.keyboard.key_pressed.connect(self.on_virtual_key)
        main_layout.addWidget(self.keyboard, 3)  # 右側佔 3/5
    
    def on_virtual_key(self, key):
        """處理虛擬鍵盤輸入"""
        current_text = self.password_input.text()
        
        if key == 'BACKSPACE':
            self.password_input.setText(current_text[:-1])
        elif key == 'CLEAR':
            self.password_input.clear()
        else:
            self.password_input.setText(current_text + key)
    
    def toggle_password_visibility(self, state):
        """切換密碼顯示/隱藏"""
        if state == Qt.CheckState.Checked.value:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
    
    def accept_password(self):
        """確認密碼"""
        self.password = self.password_input.text()
        self.remember = self.remember_checkbox.isChecked()
        if self.password:
            self.accept()
        else:
            QMessageBox.warning(self, "錯誤", "請輸入密碼")


class WiFiManagerWidget(QWidget):
    """WiFi 管理器主界面"""
    
    connection_changed = pyqtSignal(bool, str)  # (已連線, SSID)
    
    def __init__(self, parent=None, test_mode=False):
        super().__init__(parent)
        self.networks = []
        self.current_ssid = None
        self.scanner = None
        self.connector = None
        self.status_checker = None
        self.test_mode = test_mode  # Mac 測試模式
        
        # 1920x480 儀表板尺寸
        self.setFixedSize(1920, 480)
        self.setup_ui()
        
        # 自動掃描
        self.scan_timer = QTimer(self)
        self.scan_timer.setSingleShot(True)
        self.scan_timer.timeout.connect(self.scan_networks)
        self.scan_timer.start(500)
        
        # 定期檢查連線狀態
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_connection_status)
        self.status_timer.start(5000)  # 每5秒檢查一次
    
    def setup_ui(self):
        """設置 UI - 橫向佈局適配 1920x480"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(40, 20, 40, 20)
        main_layout.setSpacing(30)
        
        # 設置樣式
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a25;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background-color: #6af;
                color: white;
                border: none;
                border-radius: 15px;
                padding: 20px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5ae;
            }
            QPushButton:pressed {
                background-color: #49d;
            }
            QPushButton:disabled {
                background-color: #444;
                color: #888;
            }
            QListWidget {
                background-color: #0a0a0f;
                border: 2px solid #2a2a35;
                border-radius: 15px;
                color: white;
                font-size: 16px;
            }
            QListWidget::item {
                padding: 20px;
                border-bottom: 1px solid #2a2a35;
            }
            QListWidget::item:hover {
                background-color: #2a2a35;
            }
            QListWidget::item:selected {
                background-color: #3a3a45;
            }
        """)
        
        # === 左側區域：網路列表 ===
        left_layout = QVBoxLayout()
        left_layout.setSpacing(15)
        
        # 標題和狀態
        header_layout = QVBoxLayout()
        title_label = QLabel("WiFi 設定")
        title_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #6af;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.status_label = QLabel("檢查連線狀態...")
        self.status_label.setStyleSheet("font-size: 16px; color: #aaa;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        header_layout.addWidget(title_label)
        header_layout.addWidget(self.status_label)
        left_layout.addLayout(header_layout)
        
        # 網路列表
        self.network_list = QListWidget()
        self.network_list.itemClicked.connect(self.on_network_selected)
        
        # 啟用觸控滾動
        self.network_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.network_list.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        
        # 使用 QScroller 啟用觸控拖動滾動
        scroller = QScroller.scroller(self.network_list.viewport())
        scroller.grabGesture(self.network_list.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        
        # 設置滾動參數，讓觸控滾動更流暢
        props = scroller.scrollerProperties()
        props.setScrollMetric(QScrollerProperties.ScrollMetric.DragStartDistance, 0.002)
        props.setScrollMetric(QScrollerProperties.ScrollMetric.OvershootDragResistanceFactor, 0.5)
        props.setScrollMetric(QScrollerProperties.ScrollMetric.OvershootScrollDistanceFactor, 0.2)
        props.setScrollMetric(QScrollerProperties.ScrollMetric.DecelerationFactor, 0.8)
        scroller.setScrollerProperties(props)
        
        left_layout.addWidget(self.network_list)
        
        # 進度條
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(30)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #2a2a35;
                border-radius: 5px;
                text-align: center;
                color: white;
                font-size: 14px;
            }
            QProgressBar::chunk {
                background-color: #6af;
            }
        """)
        left_layout.addWidget(self.progress_bar)
        
        main_layout.addLayout(left_layout, 3)  # 佔 3/4 寬度
        
        # === 右側區域：控制按鈕 ===
        right_layout = QVBoxLayout()
        right_layout.setSpacing(20)
        
        # 掃描按鈕
        scan_btn = QPushButton("🔄\n重新掃描")
        scan_btn.setFixedSize(280, 120)
        scan_btn.clicked.connect(self.scan_networks)
        right_layout.addWidget(scan_btn)
        
        # 連線按鈕
        self.connect_btn = QPushButton("📡\n連線")
        self.connect_btn.setFixedSize(280, 120)
        self.connect_btn.setEnabled(False)
        self.connect_btn.clicked.connect(self.connect_to_network)
        right_layout.addWidget(self.connect_btn)
        
        # 關閉按鈕
        close_btn = QPushButton("✖\n關閉")
        close_btn.setFixedSize(280, 120)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #666;
                color: white;
                border: none;
                border-radius: 15px;
                padding: 20px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #777;
            }
            QPushButton:pressed {
                background-color: #555;
            }
        """)
        close_btn.clicked.connect(self.close)
        right_layout.addWidget(close_btn)
        
        right_layout.addStretch()
        
        main_layout.addLayout(right_layout, 1)  # 佔 1/4 寬度
    
    def scan_networks(self):
        """掃描 WiFi 網路"""
        self.network_list.clear()
        self.network_list.addItem("正在掃描...")
        self.connect_btn.setEnabled(False)
        
        if self.test_mode:
            # Mac 測試模式：使用模擬數據
            print("測試模式：使用模擬 WiFi 數據")
            QTimer.singleShot(1000, self._load_test_networks)
        else:
            # 啟動掃描執行緒
            self.scanner = WiFiScanner()
            self.scanner.scan_completed.connect(self.on_scan_completed)
            self.scanner.start()
    
    def _load_test_networks(self):
        """載入測試用的模擬網路"""
        test_networks = [
            {'ssid': 'Home WiFi', 'signal': 95, 'security': 'WPA2', 'secured': True},
            {'ssid': 'Office Network', 'signal': 80, 'security': 'WPA2', 'secured': True},
            {'ssid': 'Guest WiFi', 'signal': 65, 'security': '', 'secured': False},
            {'ssid': 'Neighbor_5G', 'signal': 45, 'security': 'WPA2', 'secured': True},
            {'ssid': 'Public WiFi', 'signal': 30, 'security': '', 'secured': False},
            {'ssid': 'Mobile Hotspot', 'signal': 25, 'security': 'WPA2', 'secured': True},
        ]
        self.on_scan_completed(test_networks)
    
    def on_scan_completed(self, networks):
        """掃描完成"""
        self.networks = networks
        self.network_list.clear()
        
        if not networks:
            self.network_list.addItem("未找到可用網路")
            return
        
        for network in networks:
            # 顯示格式：🔒 SSID (信號強度)
            icon = "🔒" if network['secured'] else "📶"
            signal_bars = "▂▄▆█"[:int(network['signal'] / 25)]
            
            item_text = f"{icon} {network['ssid']}  {signal_bars} {network['signal']}%"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, network)
            self.network_list.addItem(item)
        
        self.update_connection_status()
    
    def on_network_selected(self, item):
        """選擇網路"""
        self.connect_btn.setEnabled(True)
    
    def connect_to_network(self):
        """連線到選擇的網路"""
        current_item = self.network_list.currentItem()
        if not current_item:
            return
        
        network = current_item.data(Qt.ItemDataRole.UserRole)
        ssid = network['ssid']
        secured = network['secured']
        
        # 如果有密碼保護，顯示密碼輸入對話框
        password = None
        if secured:
            dialog = WiFiPasswordDialog(ssid, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                password = dialog.password
            else:
                return
        
        # 開始連線（背景執行緒，UI 不阻塞）
        self.show_connecting_progress(ssid)
        self.do_connect(ssid, password)
    
    def show_connecting_progress(self, ssid):
        """顯示連線進度"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不確定進度
        self.status_label.setText(f"正在連線到 {ssid}...")
        self.connect_btn.setEnabled(False)
    
    def hide_connecting_progress(self):
        """隱藏連線進度"""
        self.progress_bar.setVisible(False)
        self.connect_btn.setEnabled(True)
    
    def do_connect(self, ssid, password=None):
        """啟動背景連線執行緒（不可在 UI 執行緒跑 nmcli，會凍結畫面）"""
        if self.connector is not None and self.connector.isRunning():
            print("WiFi 連線進行中，忽略重複請求")
            return

        self.connector = WiFiConnector(ssid, password, test_mode=self.test_mode, parent=self)
        self.connector.connect_finished.connect(self._on_connect_finished)
        self.connector.start()

    def _on_connect_finished(self, success, ssid, error_msg):
        """連線結果（WiFiConnector 執行緒經 signal 回到主執行緒）"""
        self.hide_connecting_progress()

        if success:
            self.status_label.setText(f"✅ 已連線到 {ssid}")
            self.status_label.setStyleSheet("font-size: 14px; color: #6f6;")
            self.current_ssid = ssid
            self.connection_changed.emit(True, ssid)

            QMessageBox.information(self, "成功", f"已成功連線到 {ssid}")
        else:
            self.status_label.setText(f"❌ 連線失敗")
            self.status_label.setStyleSheet("font-size: 14px; color: #f66;")

            # 解析常見錯誤並提供更友善的訊息
            friendly_msg = error_msg
            if 'password' in error_msg.lower() or 'psk' in error_msg.lower():
                friendly_msg = "密碼錯誤，請重新輸入"
            elif 'timeout' in error_msg.lower():
                friendly_msg = "連線逾時，請檢查網路是否在範圍內"
            elif 'no network' in error_msg.lower():
                friendly_msg = "找不到此網路，請重新掃描"

            QMessageBox.warning(self, "連線失敗", f"無法連線到 {ssid}\n\n{friendly_msg}")
    
    def update_connection_status(self):
        """排程背景查詢；已有查詢時直接合併。"""
        if self.test_mode:
            self.status_label.setText("📱 測試模式 - 未連線")
            self.status_label.setStyleSheet("font-size: 16px; color: #fa0;")
            return
        if self.status_checker is not None and self.status_checker.isRunning():
            return
        self.status_checker = WiFiStatusChecker(parent=self)
        self.status_checker.status_ready.connect(self._apply_connection_status)
        self.status_checker.start()

    def _apply_connection_status(self, ssid):
        if ssid:
            self.current_ssid = ssid
            self.status_label.setText(f"✅ 已連線到 {ssid}")
            self.status_label.setStyleSheet("font-size: 16px; color: #6f6;")
        else:
            self.current_ssid = None
            self.status_label.setText("❌ 未連線")
            self.status_label.setStyleSheet("font-size: 16px; color: #f66;")

    def closeEvent(self, event):
        """停止所有 timer 並取消可能正在執行的 nmcli。"""
        self.scan_timer.stop()
        self.status_timer.stop()
        for worker in (self.scanner, self.connector, self.status_checker):
            if worker is not None and worker.isRunning():
                cancel = getattr(worker, 'cancel', None)
                if callable(cancel):
                    cancel()
                worker.wait(1500)
        event.accept()


def main():
    """測試用主程式"""
    import sys
    import platform
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # 在 Mac 上自動啟用測試模式
    test_mode = platform.system() == 'Darwin'
    if test_mode:
        print("偵測到 Mac 系統，啟用測試模式")
    
    widget = WiFiManagerWidget(test_mode=test_mode)
    widget.setWindowTitle("WiFi 管理器" + (" (測試模式)" if test_mode else ""))
    widget.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
