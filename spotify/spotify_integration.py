"""
Spotify 整合到 datagrab.py 主程式
"""

import logging
from spotify.spotify_auth import SpotifyAuthManager
from spotify.spotify_listener import SpotifyListener

logger = logging.getLogger(__name__)


class SpotifyIntegration:
    """Spotify 整合類別 - 用於 datagrab.py"""
    
    def __init__(self, dashboard):
        """
        初始化 Spotify 整合
        
        Args:
            dashboard: Dashboard 實例（main.py 的 Dashboard 類別）
        """
        self.dashboard = dashboard
        self.auth = None
        self.listener = None
        self.enabled = False
        
    def initialize(self):
        """初始化 Spotify 連線"""
        try:
            logger.info("正在初始化 Spotify 連線...")
            
            # 建立認證管理器
            self.auth = SpotifyAuthManager()
            
            # 執行認證
            if not self.auth.authenticate():
                logger.error("Spotify 認證失敗")
                return False
            
            logger.info("Spotify 認證成功")
            
            # 建立監聽器
            # update_interval=10.0 秒可減少 API 呼叫，進入音樂卡片時會立即更新
            # Spotify 的播放進度可透過本地計算補間，不需要頻繁查詢 API
            self.listener = SpotifyListener(self.auth, update_interval=10.0)
            
            # 設定回調函數
            self.listener.set_callback('on_track_change', self._on_track_change)
            self.listener.set_callback('on_album_art_loaded', self._on_album_art_loaded)
            self.listener.set_callback('on_progress_update', self._on_progress_update)
            self.listener.set_callback('on_error', self._on_error)
            
            # 啟動監聽
            self.listener.start()
            
            self.enabled = True
            logger.info("Spotify 整合已啟用")
            return True
            
        except Exception as e:
            logger.error(f"Spotify 初始化失敗: {e}")
            return False
    
    def _on_track_change(self, track_info):
        """歌曲變更回調（立即顯示文字資訊）"""
        try:
            album_name = track_info.get('album', '')
            logger.info(f"🎵 {track_info['name']} - {track_info['artists']} | Album: '{album_name}'")
            
            if self.dashboard:
                # 使用執行緒安全的方法更新
                self.dashboard.update_spotify_track(
                    track_info['name'],
                    track_info['artists'],
                    album_name
                )
        except Exception as e:
            logger.error(f"更新歌曲資訊失敗: {e}")
    
    def _on_album_art_loaded(self, album_art):
        """專輯封面載入完成回調（非同步）"""
        try:
            if self.dashboard:
                # 使用執行緒安全的方法更新
                self.dashboard.update_spotify_art(album_art)
        except Exception as e:
            logger.error(f"更新專輯封面失敗: {e}")
    
    def _on_progress_update(self, progress_data):
        """播放進度更新回調"""
        try:
            if self.dashboard:
                progress_ms = progress_data['progress_ms']
                duration_ms = progress_data['duration_ms']
                is_playing = progress_data.get('is_playing', True)
                # 使用執行緒安全的方法更新
                self.dashboard.update_spotify_progress(
                    progress_ms / 1000, 
                    duration_ms / 1000,
                    is_playing
                )
        except Exception as e:
            logger.error(f"更新播放進度失敗: {e}")
    
    def _on_error(self, error):
        """錯誤處理回調（只在嚴重錯誤時觸發）"""
        # 網路相關錯誤已在 listener 層級處理，這裡只記錄非網路錯誤
        if 'timeout' not in error.lower() and 'connection' not in error.lower():
            logger.warning(f"Spotify 錯誤: {error}")
    
    def set_update_interval(self, interval: float):
        """
        設定 Spotify 更新間隔
        
        Args:
            interval: 新的更新間隔（秒）
        """
        if self.listener:
            self.listener.set_update_interval(interval)
        else:
            logger.warning("Spotify listener 未初始化，無法設定更新間隔")
    
    def force_update_now(self):
        """強制立即更新一次 Spotify 資訊（用於進入音樂卡片時）"""
        if self.listener:
            self.listener.force_update_now()
        else:
            logger.warning("Spotify listener 未初始化，無法強制更新")
    
    def stop(self):
        """停止 Spotify 監聽"""
        if self.listener:
            self.listener.stop()
            logger.info("Spotify 監聽器已停止")
        self.enabled = False


# 提供給 datagrab.py 使用的簡單介面
def setup_spotify(dashboard):
    """
    為 datagrab.py 設定 Spotify 整合
    
    Args:
        dashboard: Dashboard 實例
        
    Returns:
        SpotifyIntegration 實例，若失敗則返回 None
    """
    try:
        integration = SpotifyIntegration(dashboard)
        if integration.initialize():
            return integration
        return None
    except Exception as e:
        logger.error(f"設定 Spotify 整合失敗: {e}")
        return None
