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
    signal_init_result = pyqtSignal(object, str, int)

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
        self._operation_lock = threading.Lock()
        self._setup_lock = threading.Lock()
        self._operation_generation = 0

        self.signal_init_result.connect(self._on_init_result)

    # === 初始化入口 ===

    def check_config(self):
        """檢查 Spotify 設定並初始化"""
        # 只有當配置檔和快取都存在時才自動初始化
        if os.path.exists(self._config_path) and os.path.exists(self._cache_path):
            print("發現 Spotify 設定檔和快取，正在初始化...")
            self._dashboard.music_card.show_player_ui()
            # 在背景執行緒初始化，避免卡住 UI
            self._start_operation("initial")
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
        self._start_operation("retry")

    def init_after_auth(self):
        """授權成功後在背景執行緒初始化 Spotify"""
        self.reauth_required = False
        self.init_attempts = 0
        self._start_operation("auth")

    def reconnect(self):
        """重新連接 Spotify（網路恢復 / 健康檢查觸發）"""
        if self.connected:
            return
        self._start_operation("reconnect")

    # === 背景初始化 worker（背景執行緒執行） ===

    def _start_operation(self, context):
        """啟動最新一代初始化；較舊結果會被丟棄並清理。"""
        with self._operation_lock:
            self._operation_generation += 1
            generation = self._operation_generation
        threading.Thread(
            target=self._init_worker,
            args=(context, generation),
            daemon=True,
            name=f"Spotify-{context}-{generation}",
        ).start()

    def _init_worker(self, context, generation):
        try:
            with self._setup_lock:
                with self._operation_lock:
                    if generation != self._operation_generation:
                        return
                result = setup_spotify(self._dashboard)
        except Exception as e:
            print(f"[Spotify] {context} 初始化錯誤: {e}")
            result = None
        self.signal_init_result.emit(result, context, generation)

    # === 主執行緒處理 ===

    @pyqtSlot(object, str, int)
    def _on_init_result(self, result, context, generation):
        """初始化結果處理（主執行緒）：UI 進度啟停與重試排程"""
        with self._operation_lock:
            is_latest = generation == self._operation_generation
        if not is_latest:
            if result is not None:
                threading.Thread(target=result.stop, daemon=True).start()
            return

        if result is not None:
            old_integration = self.integration
            self.integration = result
            self.connected = True
            self.init_attempts = 0
            if old_integration is not None and old_integration is not result:
                threading.Thread(target=old_integration.stop, daemon=True).start()
            print(f"[Spotify] ✅ {context} 初始化成功")
            # 依音樂卡片可見狀態啟停進度更新
            self._dashboard._set_spotify_progress_active(
                self._dashboard._is_music_card_visible()
            )
            return

        self.connected = False
        self.init_attempts += 1
        print(f"[Spotify] ❌ {context} 初始化失敗 (嘗試 {self.init_attempts})")

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
        with self._operation_lock:
            self._operation_generation += 1
        self.reauth_required = True
        self.connected = False
        self.init_attempts = 3

        integration = self.integration
        if integration:
            integration.enabled = False
            if integration.listener:
                integration.listener.running = False
        return True
