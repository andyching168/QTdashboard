"""
Spotify 播放狀態監聽器
定期查詢當前播放資訊並更新 UI
"""

import threading
import time
import logging
from typing import Optional, Dict, Any, Callable
from io import BytesIO
import requests
from PIL import Image

logger = logging.getLogger(__name__)


class SpotifyListener:
    """
    Spotify 播放狀態監聽器
    
    定期查詢 Spotify API 獲取當前播放資訊，並通過回調函數更新 UI
    """
    
    def __init__(self, auth_manager, update_interval=1.0):
        """
        初始化監聽器
        
        Args:
            auth_manager: SpotifyAuthManager 實例
            update_interval: API 查詢間隔（秒），預設 1 秒
                           建議設為 2.0 秒以減少 API 呼叫，進度條會透過本地補間保持流暢
        """
        self.auth_manager = auth_manager
        self.update_interval = update_interval
        
        # 監聽器狀態
        self.running = False
        self.thread = None
        self.interpolation_thread = None  # 進度補間執行緒
        
        # 快取上次的播放資訊
        self.last_track_id = None
        self.last_playback = None
        self.last_album_art = None
        
        # 本地進度追蹤（用於補間）
        self.local_progress_ms = 0
        self.local_duration_ms = 0
        self.local_is_playing = False
        self.last_sync_time = 0  # 上次同步的時間戳
        
        # 錯誤處理
        self.consecutive_errors = 0
        self.max_silent_errors = 5  # 連續錯誤超過此數才輸出警告
        self.error_backoff = 1.0  # 錯誤後的延遲倍數
        
        # 回調函數
        self.callbacks = {
            'on_track_change': None,     # 歌曲變更時（不含專輯封面）
            'on_album_art_loaded': None, # 專輯封面載入完成時
            'on_progress_update': None,  # 播放進度更新時
            'on_playback_state': None,   # 播放狀態變更時
            'on_error': None,            # 發生錯誤時
        }
    
    def set_callback(self, event_name: str, callback: Callable):
        """
        設定事件回調函數
        
        Args:
            event_name: 事件名稱
                - 'on_track_change': 歌曲變更（不含專輯封面）
                - 'on_album_art_loaded': 專輯封面載入完成
                - 'on_progress_update': 播放進度更新
                - 'on_playback_state': 播放狀態變更
                - 'on_error': 錯誤發生
            callback: 回調函數
        """
        if event_name in self.callbacks:
            self.callbacks[event_name] = callback
        else:
            logger.warning(f"未知的事件名稱: {event_name}")
    
    def start(self):
        """啟動監聽器"""
        if self.running:
            logger.warning("監聽器已在運行中")
            return
            
        self.running = True
        
        # 啟動 API 輪詢執行緒
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        
        # 啟動本地進度補間執行緒（每 200ms 更新一次進度條，不需要 API 呼叫）
        self.interpolation_thread = threading.Thread(target=self._interpolation_loop, daemon=True)
        self.interpolation_thread.start()
        
        logger.info(f"Spotify 監聽器已啟動（API 間隔: {self.update_interval}秒）")
    
    def stop(self):
        """停止監聽器"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.interpolation_thread:
            self.interpolation_thread.join(timeout=1)
        logger.info("Spotify 監聽器已停止")
    
    def _interpolation_loop(self):
        """本地進度補間循環（不呼叫 API，只更新進度條）"""
        while self.running:
            try:
                if self.local_is_playing and self.local_duration_ms > 0:
                    # 計算經過的時間
                    elapsed = (time.time() - self.last_sync_time) * 1000
                    interpolated_progress = min(
                        self.local_progress_ms + elapsed,
                        self.local_duration_ms
                    )
                    
                    # 透過回調更新進度
                    if self.callbacks['on_progress_update']:
                        progress_data = {
                            'progress_ms': interpolated_progress,
                            'duration_ms': self.local_duration_ms,
                            'is_playing': self.local_is_playing,
                        }
                        self.callbacks['on_progress_update'](progress_data)
                
                time.sleep(0.2)  # 每 200ms 更新一次，足夠流暢
                
            except Exception as e:
                logger.debug(f"進度補間錯誤: {e}")
                time.sleep(0.5)
    
    def _listen_loop(self):
        """監聽循環（在背景執行緒運行）"""
        while self.running:
            try:
                self._update_playback_state()
                # 成功後重置錯誤計數和退避
                self.consecutive_errors = 0
                self.error_backoff = 1.0
                time.sleep(self.update_interval)
                
            except Exception as e:
                self.consecutive_errors += 1
                
                # 只在錯誤累積到一定數量後才輸出警告
                if self.consecutive_errors <= self.max_silent_errors:
                    logger.debug(f"Spotify 連線錯誤 ({self.consecutive_errors}/{self.max_silent_errors}): {e}")
                elif self.consecutive_errors == self.max_silent_errors + 1:
                    logger.warning(f"Spotify 持續連線失敗，將降低更新頻率")
                
                # 指數退避：錯誤次數越多，等待時間越長
                self.error_backoff = min(self.error_backoff * 1.5, 30.0)  # 最多 30 秒
                time.sleep(self.update_interval * self.error_backoff)
    
    def _update_playback_state(self):
        """更新播放狀態（從 Spotify API 同步）"""
        sp = self.auth_manager.get_client()
        if not sp:
            return
            
        try:
            # 查詢當前播放狀態
            playback = sp.current_playback()
            
            if not playback or not playback.get('item'):
                # 沒有正在播放的內容
                self.local_is_playing = False
                if self.last_playback is not None:
                    logger.info("播放已停止")
                    if self.callbacks['on_playback_state']:
                        self.callbacks['on_playback_state'](None)
                    self.last_playback = None
                    self.last_track_id = None
                return
            
            track = playback['item']
            track_id = track['id']
            
            # 同步本地進度追蹤（供補間使用）
            self.local_progress_ms = playback['progress_ms']
            self.local_duration_ms = track['duration_ms']
            self.local_is_playing = playback['is_playing']
            self.last_sync_time = time.time()
            
            # 檢查是否為新歌曲
            if track_id != self.last_track_id:
                logger.info(f"歌曲變更: {track['name']}")
                self.last_track_id = track_id
                self._handle_track_change(track, playback)
            
            # 注意：進度更新現在由 _interpolation_loop 處理，這裡不再重複呼叫
            # 但仍然透過同步更新 local_* 變數來校正進度
            
            # 更新播放狀態
            if self.callbacks['on_playback_state']:
                self.callbacks['on_playback_state'](playback)
            
            self.last_playback = playback
            
        except Exception as e:
            # 網路相關錯誤使用 DEBUG 級別，避免刷屏
            if 'timeout' in str(e).lower() or 'connection' in str(e).lower() or 'no route to host' in str(e).lower():
                logger.debug(f"網路連線問題: {e}")
            else:
                logger.error(f"更新播放狀態失敗: {e}")
            
            # 只在嚴重錯誤時才觸發回調
            if self.callbacks['on_error'] and self.consecutive_errors > self.max_silent_errors:
                self.callbacks['on_error'](str(e))
            
            raise  # 重新拋出異常給 _listen_loop 處理
    
    def _handle_track_change(self, track: Dict[str, Any], playback: Dict[str, Any]):
        """處理歌曲變更"""
        try:
            # 提取歌曲資訊
            track_info = {
                'id': track['id'],
                'name': track['name'],
                'artists': ', '.join([artist['name'] for artist in track['artists']]),
                'album': track['album']['name'],
                'duration_ms': track['duration_ms'],
                'progress_ms': playback['progress_ms'],
                'is_playing': playback['is_playing'],
                'album_art_url': None,
                'album_art': None,
            }
            
            # 先發送基本資訊（不含圖片）
            if self.callbacks['on_track_change']:
                self.callbacks['on_track_change'](track_info)
            
            # 在獨立執行緒中非同步下載專輯封面
            if track['album']['images']:
                # 選擇中等大小的圖片（通常是 300x300）
                image_url = track['album']['images'][0]['url']  # 最大尺寸
                if len(track['album']['images']) > 1:
                    image_url = track['album']['images'][1]['url']  # 中等尺寸
                
                track_info['album_art_url'] = image_url
                
                # 啟動非同步下載
                download_thread = threading.Thread(
                    target=self._download_album_art_async,
                    args=(image_url, track_info['id']),
                    daemon=True
                )
                download_thread.start()
                
        except Exception as e:
            logger.error(f"處理歌曲變更失敗: {e}")
    
    def _download_album_art_async(self, url: str, track_id: str):
        """
        非同步下載專輯封面
        
        Args:
            url: 圖片 URL
            track_id: 歌曲 ID（用於驗證是否仍是當前歌曲）
        """
        try:
            # 下載圖片
            image = self._download_album_art(url)
            
            if image and self.last_track_id == track_id:
                # 確認仍是當前歌曲才更新
                if self.callbacks['on_album_art_loaded']:
                    self.callbacks['on_album_art_loaded'](image)
                    
        except Exception as e:
            logger.error(f"非同步下載專輯封面失敗: {e}")
    
    def _download_album_art(self, url: str) -> Optional[Image.Image]:
        """
        下載專輯封面圖片（優化版本：在背景縮小圖片）
        
        Args:
            url: 圖片 URL
            
        Returns:
            PIL.Image.Image: 縮小後的圖片物件，失敗則返回 None
        """
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            
            image = Image.open(BytesIO(response.content))
            
            # 在背景執行緒先縮小圖片，減少主執行緒的工作量
            # 目標大小 300x300（MusicCardWide 使用的尺寸）
            target_size = 300
            if image.size[0] > target_size or image.size[1] > target_size:
                # 使用 LANCZOS (高品質) 縮放，因為這是在背景執行緒
                image = image.resize((target_size, target_size), resample=Image.Resampling.LANCZOS)
            
            # 轉換為 RGB 模式（避免 RGBA 轉換問題）
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            self.last_album_art = image
            return image
            
        except Exception as e:
            logger.error(f"下載專輯封面失敗: {e}")
            return None
    
    def get_current_track(self) -> Optional[Dict[str, Any]]:
        """
        取得當前歌曲資訊
        
        Returns:
            dict: 歌曲資訊，若無則返回 None
        """
        if not self.last_playback:
            return None
            
        track = self.last_playback['item']
        return {
            'id': track['id'],
            'name': track['name'],
            'artists': ', '.join([artist['name'] for artist in track['artists']]),
            'album': track['album']['name'],
            'duration_ms': track['duration_ms'],
            'progress_ms': self.last_playback['progress_ms'],
            'is_playing': self.last_playback['is_playing'],
            'album_art': self.last_album_art,
        }


def main():
    """測試監聽器"""
    import logging
    from spotify_auth import SpotifyAuthManager
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 降低第三方套件的日誌級別
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    logging.getLogger('requests').setLevel(logging.ERROR)
    
    print("=== Spotify 監聽器測試 ===")
    print()
    
    # 建立認證管理器
    auth = SpotifyAuthManager()
    if not auth.authenticate():
        print("❌ 認證失敗")
        return
    
    print("✅ 認證成功")
    print()
    
    # 定義回調函數
    def on_track_change(track_info):
        print(f"\n🎵 新歌曲:")
        print(f"   標題: {track_info['name']}")
        print(f"   藝人: {track_info['artists']}")
        print(f"   專輯: {track_info['album']}")
        print(f"   時長: {track_info['duration_ms']/1000:.1f} 秒")
        print(f"   ⏳ 專輯封面下載中...")
    
    def on_album_art_loaded(album_art):
        print(f"   ✅ 封面已載入: {album_art.size}")
    
    def on_progress_update(progress_data):
        progress = progress_data['progress_ms']
        duration = progress_data['duration_ms']
        percentage = (progress / duration) * 100 if duration > 0 else 0
        is_playing = progress_data['is_playing']
        
        status = "▶️ " if is_playing else "⏸️ "
        print(f"\r{status} 進度: {progress/1000:.1f}/{duration/1000:.1f}s ({percentage:.1f}%)", end='', flush=True)
    
    def on_error(error):
        print(f"\n❌ 錯誤: {error}")
    
    # 建立監聽器
    listener = SpotifyListener(auth, update_interval=1.0)
    listener.set_callback('on_track_change', on_track_change)
    listener.set_callback('on_album_art_loaded', on_album_art_loaded)
    listener.set_callback('on_progress_update', on_progress_update)
    listener.set_callback('on_error', on_error)
    
    # 啟動監聽
    print("開始監聽 Spotify 播放狀態...")
    print("請在 Spotify 開始播放音樂")
    print("按 Ctrl+C 停止監聽")
    print()
    
    listener.start()
    
    try:
        # 保持運行
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n停止監聽...")
        listener.stop()
        print("✅ 已停止")


if __name__ == '__main__':
    main()
