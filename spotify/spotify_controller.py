"""Spotify 生命週期控制器

從 main.py 的 Dashboard 拆出的 Spotify 初始化 / 重試 / 重連 / 重新授權管理：
- 依設定檔與授權快取決定是否自動初始化（背景執行緒執行 setup_spotify）
- 初始化失敗時每 30 秒重試（最多 3 次）
- 網路恢復或健康檢查時可要求重連
- refresh token 失效時鎖定自動重試，交回綁定流程

跨執行緒規則：setup_spotify 在背景執行緒執行，結果透過 signal_init_result
回主執行緒，再由主執行緒處理 UI（進度條啟停）與重試排程。
"""

import os
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from spotify.spotify_integration import setup_spotify


class SpotifyController(QObject):
    """管理 Spotify 整合的連線狀態與生命週期"""

    # 背景初始化執行緒 -> 主執行緒：初始化結果 (success, context)
    # context: "initial" / "retry" / "auth" / "reconnect"
    signal_init_result = pyqtSignal(bool, str)

    def __init__(self, dashboard, config_path, cache_path, parent=None):
        super().__init__(parent)
        self._dashboard = dashboard
        self._config_path = config_path
        self._cache_path = cache_path

        # 服務連線狀態追蹤
        self.connected = False
        self.init_attempts = 0
        self.integration = None  # Spotify 整合實例引用
        self.reauth_required = False

        self.signal_init_result.connect(self._on_init_result)

    # === 初始化入口 ===

    def check_config(self):
        """檢查 Spotify 設定並初始化"""
        # 只有當配置檔和快取都存在時才自動初始化
        if os.path.exists(self._config_path) and os.path.exists(self._cache_path):
            print("發現 Spotify 設定檔和快取，正在初始化...")
            self._dashboard.music_card.show_player_ui()
            # 在背景執行緒初始化，避免卡住 UI
            threading.Thread(target=self._initial_init_worker, daemon=True).start()
        else:
            if not os.path.exists(self._config_path):
                print("未發現 Spotify 設定檔，顯示綁定介面")
            else:
                print("未發現授權快取，顯示綁定介面")
            self._dashboard.music_card.show_bind_ui()

    def retry_init(self):
        """重試 Spotify 初始化"""
        if self.connected or self._dashboard.is_offline:
            return

        print(f"[Spotify] 重試初始化 (嘗試 {self.init_attempts + 1}/3)...")
        threading.Thread(target=self._retry_init_worker, daemon=True).start()

    def init_after_auth(self):
        """授權成功後在背景執行緒初始化 Spotify"""
        self.reauth_required = False
        self.init_attempts = 0
        threading.Thread(target=self._auth_init_worker, daemon=True).start()

    def reconnect(self):
        """重新連接 Spotify（網路恢復 / 健康檢查觸發）"""
        threading.Thread(target=self._reconnect_worker, daemon=True).start()

    # === 背景初始化 worker（背景執行緒執行） ===

    def _initial_init_worker(self):
        """啟動時的初始化"""
        result = setup_spotify(self._dashboard)
        if result:
            self.connected = True
            self.integration = result  # 儲存整合實例引用
            self.init_attempts = 0
            print("Spotify 初始化成功")
            self.signal_init_result.emit(True, "initial")
        else:
            self.connected = False
            self.init_attempts += 1
            print(f"Spotify 初始化失敗 (嘗試 {self.init_attempts})")
            self.signal_init_result.emit(False, "initial")

    def _retry_init_worker(self):
        """重試初始化"""
        result = setup_spotify(self._dashboard)
        if result:
            self.connected = True
            self.integration = result  # 儲存整合實例引用
            self.init_attempts = 0
            print("[Spotify] ✅ 重試成功")
            self.signal_init_result.emit(True, "retry")
        else:
            self.connected = False
            self.init_attempts += 1
            print(f"[Spotify] ❌ 重試失敗 (嘗試 {self.init_attempts})")
            self.signal_init_result.emit(False, "retry")

    def _auth_init_worker(self):
        """授權完成後的初始化"""
        try:
            result = setup_spotify(self._dashboard)
            if result:
                self.connected = True
                self.integration = result
                self.init_attempts = 0
                print("[Spotify] ✅ 初始化成功")
                self.signal_init_result.emit(True, "auth")
            else:
                self.connected = False
                print("[Spotify] ❌ 初始化失敗")
        except Exception as e:
            self.connected = False
            print(f"Spotify 初始化失敗: {e}")

    def _reconnect_worker(self):
        """重新連接（維持原行為：不更新 integration 引用、不排程重試）"""
        try:
            result = setup_spotify(self._dashboard)
            if result:
                self.connected = True
                self.init_attempts = 0
                print("[Spotify] ✅ 重新連接成功")
            else:
                self.init_attempts += 1
                print(f"[Spotify] ❌ 重新連接失敗 (嘗試 {self.init_attempts})")
        except Exception as e:
            self.init_attempts += 1
            print(f"[Spotify] ❌ 重新連接錯誤: {e}")

    # === 主執行緒處理 ===

    @pyqtSlot(bool, str)
    def _on_init_result(self, success, context):
        """初始化結果處理（主執行緒）：UI 進度啟停與重試排程"""
        if success:
            # 依音樂卡片可見狀態啟停進度更新
            self._dashboard._set_spotify_progress_active(
                self._dashboard._is_music_card_visible()
            )
            return

        # 初始化失敗：30 秒後重試（最多 3 次，需在線且授權快取存在）
        token_cache_exists = os.path.exists(self._cache_path)
        if self.init_attempts < 3 and not self._dashboard.is_offline and token_cache_exists:
            if context == "initial":
                print("[Spotify] 將在 30 秒後重試...")
            QTimer.singleShot(30000, self.retry_init)

    def mark_reauth_required(self):
        """refresh token 失效：停止自動重試並停用整合（主執行緒）

        Returns:
            bool: True 表示狀態首次切換（呼叫端需更新 UI）；False 表示已處理過
        """
        if self.reauth_required:
            return False
        self.reauth_required = True
        self.connected = False
        self.init_attempts = 3

        integration = self.integration
        if integration:
            integration.enabled = False
            if integration.listener:
                integration.listener.running = False
        return True
