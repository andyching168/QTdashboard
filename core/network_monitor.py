"""網路狀態監控器

從 main.py 的 Dashboard 拆出的網路健檢與服務重連邏輯：
- 常駐 worker thread 週期性檢查對外連線（取代原本每 5 秒 spawn 一條新 daemon thread）
- 連線狀態透過 Signal 回主執行緒更新，Dashboard 只負責 UI 呈現
- 網路恢復時延遲重連 Spotify / MQTT；每 60 秒做一次服務健康檢查

跨執行緒規則：worker thread 只做 socket 檢查，結果一律透過 pyqtSignal
回主執行緒處理，不可直接碰 widget。
"""

import os
import platform
import socket
import subprocess
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot


class NetworkMonitor(QObject):
    """網路連線監控 + 服務（Spotify / MQTT）重連協調"""

    # worker thread -> 主執行緒：連線檢查結果
    signal_connectivity_result = pyqtSignal(bool)

    # 主執行緒 -> Dashboard：狀態已更新，通知 UI 刷新（每次檢查都發）
    signal_status_updated = pyqtSignal(bool)  # is_connected
    signal_wifi_status_updated = pyqtSignal(object)  # {ssid, signal, interface}

    def __init__(self, dashboard, spotify_config_path, spotify_cache_path,
                 mqtt_config_path, parent=None):
        super().__init__(parent)
        self._dashboard = dashboard
        self._spotify_config_path = spotify_config_path
        self._spotify_cache_path = spotify_cache_path
        self._mqtt_config_path = mqtt_config_path

        # 網路狀態（主執行緒讀寫；初始假設在線，檢查後更新）
        self.is_offline = False

        # 常駐 worker thread 控制
        self._wake = threading.Event()
        self._stop_requested = False
        self._worker_thread = None

        # 服務健康檢查 Timer（每 60 秒）
        self._health_timer = None

        # worker -> 主執行緒
        self.signal_connectivity_result.connect(self._on_connectivity_result)

    # === 生命週期 ===

    def start(self):
        """啟動網路檢查 worker thread 與服務健康檢查 Timer"""
        if self._worker_thread is not None:
            return

        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="NetworkMonitor"
        )
        self._worker_thread.start()

        # 啟動服務健康檢查（每 60 秒檢查一次）
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self.check_service_health)
        self._health_timer.start(60000)  # 60 秒

    def stop(self, timeout=3.0):
        """停止 worker thread"""
        self._stop_requested = True
        self._wake.set()
        if self._health_timer is not None:
            self._health_timer.stop()
        thread = self._worker_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        return thread is None or not thread.is_alive()

    def request_check_now(self):
        """喚醒 worker thread 立即做一次檢查（coalesce：重複呼叫只會觸發一次）"""
        self._wake.set()

    # === 背景檢查（worker thread） ===

    def _worker_loop(self):
        """常駐 worker：首次延遲 2 秒檢查，之後每 5 秒一次；可被 Event 提前喚醒"""
        interval = 2.0  # 對齊原本啟動後 2 秒的首次檢查
        while not self._stop_requested:
            self._wake.wait(timeout=interval)
            self._wake.clear()
            if self._stop_requested:
                break
            interval = 5.0
            is_connected = self._check_connection()
            wifi_status = self._check_wifi_status()
            # 透過 Signal 回到主執行緒更新狀態
            self.signal_connectivity_result.emit(is_connected)
            self.signal_wifi_status_updated.emit(wifi_status)

    @staticmethod
    def _check_connection():
        """實際的連線檢查（worker thread 執行）"""
        # 方法 1: 嘗試 socket 連接 Google DNS
        try:
            sock = socket.create_connection(("8.8.8.8", 53), timeout=1)
            sock.close()
            return True
        except Exception:
            pass

        # 方法 2: 嘗試 socket 連接 Cloudflare DNS
        try:
            sock = socket.create_connection(("1.1.1.1", 53), timeout=1)
            sock.close()
            return True
        except Exception:
            pass

        # 都失敗了
        return False

    @staticmethod
    def _check_wifi_status():
        """背景取得 SSID/訊號，絕不在 Qt 主執行緒執行命令。"""
        if platform.system() != 'Linux':
            return {}
        interface = None
        signal = 0
        try:
            with open('/proc/net/wireless', 'r', encoding='utf-8') as file:
                for line in file.readlines()[2:]:
                    parts = line.strip().split()
                    if ':' in line and len(parts) >= 3:
                        interface = parts[0].rstrip(':')
                        signal = min(100, max(0, int(float(parts[2].rstrip('.')) * 100 / 70)))
                        break
        except Exception:
            pass

        ssid = None
        env = os.environ.copy()
        env['LANG'] = 'C'
        env['LC_ALL'] = 'C'
        if interface:
            try:
                result = subprocess.run(
                    ['iw', 'dev', interface, 'link'], capture_output=True,
                    text=True, timeout=1, env=env,
                )
                for line in result.stdout.splitlines():
                    if line.strip().startswith('SSID:'):
                        ssid = line.split(':', 1)[1].strip()
                        break
            except Exception:
                pass
        if not ssid:
            try:
                result = subprocess.run(
                    ['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'],
                    capture_output=True, text=True, timeout=1, env=env,
                )
                for line in result.stdout.splitlines():
                    if line.lower().startswith('yes:') or line.startswith('是:'):
                        ssid = line.split(':', 1)[1].strip() or None
                        break
            except Exception:
                pass
        return {'ssid': ssid, 'signal': signal, 'interface': interface}

    # === 主執行緒處理 ===

    @pyqtSlot(bool)
    def _on_connectivity_result(self, is_connected):
        """更新網路狀態（主執行緒）"""
        was_offline = self.is_offline
        self.is_offline = not is_connected

        if self.is_offline != was_offline:
            if self.is_offline:
                print("[網路] ⚠️ 網路已斷線")
                self._dashboard.show_toast("網路已斷線", "warning", 3500)
            else:
                print("[網路] ✅ 網路已恢復連線")
                self._dashboard.show_toast("網路已恢復連線", "success", 3000)
                # 網路恢復時嘗試重新連接服務
                self._on_network_restored()

        # 通知 Dashboard 更新 UI（音樂卡片 / 導航卡片 / 下拉面板）
        self.signal_status_updated.emit(is_connected)

    def _on_network_restored(self):
        """網路恢復時的重連邏輯"""
        print("[重連] 網路已恢復，檢查服務狀態...")

        # 延遲 2 秒後重連，避免網路剛恢復就馬上連接
        QTimer.singleShot(2000, self.attempt_reconnect_services)

    def attempt_reconnect_services(self):
        """嘗試重新連接各項服務（主執行緒）"""
        # 如果目前仍是離線狀態，取消重連
        if self.is_offline:
            print("[重連] 網路仍未恢復，取消重連")
            return

        dashboard = self._dashboard

        # 1. 重連 Spotify（如果尚未連線且有設定檔）
        if not dashboard.spotify_controller.connected:
            if os.path.exists(self._spotify_config_path) and os.path.exists(self._spotify_cache_path):
                print("[重連] 嘗試重新連接 Spotify...")
                dashboard._reconnect_spotify()

        # 2. 重連 MQTT（如果有設定檔但客戶端未連線）
        if os.path.exists(self._mqtt_config_path):
            if dashboard.mqtt_controller.client is None or not dashboard.mqtt_controller.connected:
                print("[重連] 嘗試重新連接 MQTT...")
                dashboard._reconnect_mqtt()

    def check_service_health(self):
        """定時檢查服務健康狀態，必要時重連（主執行緒）"""
        # 如果離線，跳過檢查
        if self.is_offline:
            return

        dashboard = self._dashboard

        # 檢查 Spotify 狀態
        if os.path.exists(self._spotify_config_path) and os.path.exists(self._spotify_cache_path):
            if not dashboard.spotify_controller.connected and dashboard.spotify_controller.init_attempts < 3:
                print("[健康檢查] Spotify 未連線，嘗試重連...")
                dashboard._reconnect_spotify()

        # 檢查 MQTT 狀態
        if os.path.exists(self._mqtt_config_path):
            if not dashboard.mqtt_controller.connected:
                print("[健康檢查] MQTT 未連線，嘗試重連...")
                dashboard._reconnect_mqtt()
