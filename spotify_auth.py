"""
Spotify OAuth 認證管理模組
參考 FreekBes/spotify_web_controller 實作 OAuth 2.0 Authorization Code Flow
"""

import os
import json
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
import logging

logger = logging.getLogger(__name__)


class SpotifyAuthManager:
    """
    Spotify 認證管理器
    
    使用 Authorization Code Flow 獲取 access token
    """
    
    # Spotify API 權限範圍
    SCOPES = [
        "user-read-currently-playing",  # 讀取當前播放
        "user-read-playback-state",     # 讀取播放狀態
        "user-modify-playback-state",   # 控制播放
        "user-read-recently-played",    # 讀取最近播放
    ]
    
    def __init__(self, config_path="spotify_config.json", cache_path=".spotify_cache"):
        """
        初始化認證管理器
        
        Args:
            config_path: Spotify 配置檔路徑
            cache_path: Token 快取檔路徑
        """
        self.config_path = config_path
        self.cache_path = cache_path
        self.sp = None
        self.auth_manager = None
        
        # 載入配置
        self.config = self._load_config()
        
    def _load_config(self):
        """載入 Spotify 配置"""
        if not os.path.exists(self.config_path):
            logger.error(f"找不到配置檔: {self.config_path}")
            logger.info("請複製 spotify_config.json.example 並填入您的 Spotify API 憑證")
            return None
            
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # 驗證必要欄位
            required_fields = ['client_id', 'client_secret', 'redirect_uri']
            for field in required_fields:
                if not config.get(field):
                    logger.error(f"配置檔缺少必要欄位: {field}")
                    return None
                    
            return config
            
        except Exception as e:
            logger.error(f"載入配置檔失敗: {e}")
            return None
    
    def authenticate(self):
        """
        執行 OAuth 認證流程
        
        Returns:
            bool: 認證是否成功
        """
        if not self.config:
            return False
            
        try:
            # 建立 Spotify OAuth 管理器
            self.auth_manager = SpotifyOAuth(
                client_id=self.config['client_id'],
                client_secret=self.config['client_secret'],
                redirect_uri=self.config['redirect_uri'],
                scope=" ".join(self.SCOPES),
                cache_path=self.cache_path,
                open_browser=True  # 自動開啟瀏覽器
            )
            
            # 建立 Spotify 客戶端
            self.sp = Spotify(auth_manager=self.auth_manager)
            
            # 測試認證
            user = self.sp.current_user()
            logger.info(f"成功認證 Spotify 使用者: {user['display_name']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Spotify 認證失敗: {e}")
            return False
    
    def get_client(self):
        """
        取得已認證的 Spotify 客戶端
        
        Returns:
            Spotify: Spotify 客戶端物件，若未認證則返回 None
        """
        if not self.sp:
            logger.warning("尚未完成 Spotify 認證")
            return None
            
        # 檢查 token 是否過期並自動更新
        try:
            token_info = self.auth_manager.get_cached_token()
            if not token_info:
                logger.info("Token 已過期，重新認證中...")
                return None if not self.authenticate() else self.sp
                
            return self.sp
            
        except Exception as e:
            logger.error(f"取得 Spotify 客戶端失敗: {e}")
            return None
    
    def is_authenticated(self):
        """
        檢查是否已認證
        
        Returns:
            bool: 是否已認證
        """
        return self.sp is not None
    
    def logout(self):
        """登出並清除快取的 token"""
        try:
            if os.path.exists(self.cache_path):
                os.remove(self.cache_path)
                logger.info("已清除 Spotify 認證快取")
                
            self.sp = None
            self.auth_manager = None
            
        except Exception as e:
            logger.error(f"登出失敗: {e}")


def main():
    """測試認證流程"""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=== Spotify 認證測試 ===")
    print()
    
    # 建立認證管理器
    auth = SpotifyAuthManager()
    
    if not auth.config:
        print("❌ 請先設定 spotify_config.json")
        print("   1. 複製 spotify_config.json.example 為 spotify_config.json")
        print("   2. 前往 https://developer.spotify.com/dashboard 建立應用程式")
        print("   3. 填入 Client ID、Client Secret 和 Redirect URI")
        return
    
    # 執行認證
    print("正在開啟瀏覽器進行 Spotify 認證...")
    print("請在瀏覽器中授權應用程式存取您的 Spotify 帳號")
    print()
    
    if auth.authenticate():
        print("✅ 認證成功!")
        print()
        
        # 取得客戶端
        sp = auth.get_client()
        if sp:
            # 顯示使用者資訊
            user = sp.current_user()
            print(f"使用者: {user['display_name']}")
            print(f"帳號類型: {user.get('product', 'unknown')}")
            print()
            
            # 嘗試取得當前播放
            try:
                playback = sp.current_playback()
                if playback and playback.get('item'):
                    track = playback['item']
                    artists = ', '.join([artist['name'] for artist in track['artists']])
                    print(f"正在播放: {track['name']} - {artists}")
                    print(f"專輯: {track['album']['name']}")
                    print(f"進度: {playback['progress_ms']}ms / {track['duration_ms']}ms")
                else:
                    print("目前沒有正在播放的音樂")
                    print("請在 Spotify 開始播放音樂後再試")
                    
            except Exception as e:
                print(f"取得播放資訊失敗: {e}")
                
    else:
        print("❌ 認證失敗")
        print("   請檢查 spotify_config.json 的設定是否正確")


if __name__ == '__main__':
    main()
