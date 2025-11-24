#!/usr/bin/env python3
"""
演示模式 - 不需要 CAN Bus 硬體
直接運行前端並使用模擬數據更新
支援 Spotify Connect 整合
"""

import sys
import time
import random
import math
import argparse
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, pyqtSignal, QObject
from main import Dashboard

# Spotify 整合（可選）
try:
    from spotify_auth import SpotifyAuthManager
    from spotify_listener import SpotifyListener
    SPOTIFY_AVAILABLE = True
except ImportError:
    SPOTIFY_AVAILABLE = False
    logging.warning("Spotify 模組未安裝，將使用模擬音樂資料")


class SpotifySignals(QObject):
    """Spotify 訊號橋接器 (用於跨執行緒更新 UI)"""
    track_changed = pyqtSignal(dict)
    album_art_loaded = pyqtSignal(object)
    progress_updated = pyqtSignal(dict)


class VehicleSignals(QObject):
    """車輛資料訊號橋接器 (用於一致的 Signal/Slot 架構)"""
    update_rpm = pyqtSignal(float)
    update_speed = pyqtSignal(float)
    update_temp = pyqtSignal(float)
    update_fuel = pyqtSignal(float)
    update_gear = pyqtSignal(str)


class VehicleSimulator:
    """車輛狀態模擬器"""
    
    def __init__(self):
        self.speed = 0.0
        self.rpm = 0.8  # 千轉
        self.fuel = 65.0
        self.temp = 45.0  # 儀表百分比
        self.gear = "P"
        
        self.mode = "idle"
        self.time = 0
        self.target_speed = 0
        
        # 音樂播放模擬
        self.music_time = 0
        self.song_duration = 182  # 3:02
        self.playlist = [
            ("Drive My Car", "The Beatles", 182),
            ("Highway Star", "Deep Purple", 206),
            ("Ride", "Twenty One Pilots", 214),
            ("Born to Run", "Bruce Springsteen", 270),
            ("Life is a Highway", "Tom Cochrane", 264),
        ]
        self.current_song_index = 0
    
    def update(self, dt=0.1):
        """更新車輛狀態"""
        self.time += dt
        
        # 模式切換
        if self.mode == "idle":
            if self.time > 5:
                self.mode = "accelerating"
                self.target_speed = random.uniform(40, 100)
                self.gear = "D"
                self.time = 0
                
        elif self.mode == "accelerating":
            if self.speed >= self.target_speed * 0.95:
                self.mode = "cruising"
                self.time = 0
                
        elif self.mode == "cruising":
            if self.time > random.uniform(8, 15):
                self.mode = "decelerating"
                self.time = 0
                
        elif self.mode == "decelerating":
            if self.speed < 5:
                self.mode = "idle"
                self.gear = "P"
                self.time = 0
        
        # 更新速度
        if self.mode == "idle":
            self.speed = max(0, self.speed - 2 * dt)
            self.rpm = 0.8  # 怠速
            
        elif self.mode == "accelerating":
            self.speed = min(self.target_speed, self.speed + 3 * dt)
            self.rpm = 0.8 + (self.speed / 100.0) * 4.5
            
        elif self.mode == "cruising":
            self.speed += random.uniform(-0.5, 0.5) * dt
            self.rpm = 1.5 + (self.speed / 100.0) * 2.5
            
        elif self.mode == "decelerating":
            self.speed = max(0, self.speed - 4 * dt)
            if self.speed < 5:
                self.rpm = 0.8
            else:
                self.rpm = max(0.8, 1.0 + (self.speed / 100.0) * 3.0)
        
        # 限制範圍
        self.speed = max(0, min(180, self.speed))
        self.rpm = max(0, min(7, self.rpm))
        
        # 更新油量（緩慢減少）
        if self.speed > 0:
            self.fuel = max(5, self.fuel - 0.005 * dt)
        
        # 更新水溫
        if self.rpm > 1.5:
            target_temp = 50  # 正常工作溫度
        else:
            target_temp = 45
        
        if self.temp < target_temp:
            self.temp += 0.5 * dt
        elif self.temp > target_temp:
            self.temp -= 0.3 * dt
        
        # 添加小波動
        self.temp += random.uniform(-0.1, 0.1)
        self.temp = max(20, min(95, self.temp))
        
        # 檔位邏輯
        if self.speed > 5 and self.gear == "P":
            self.gear = "D"
        elif self.speed < 1 and self.mode == "idle":
            self.gear = "P"
        
        # 音樂播放進度
        self.music_time += dt
        if self.music_time >= self.song_duration:
            # 切換到下一首
            self.current_song_index = (self.current_song_index + 1) % len(self.playlist)
            song_title, artist, duration = self.playlist[self.current_song_index]
            self.song_duration = duration
            self.music_time = 0


def main():
    """主程式"""
    # 解析命令列參數
    parser = argparse.ArgumentParser(description='Luxgen M7 儀表板演示模式')
    parser.add_argument('--spotify', action='store_true', 
                        help='啟用 Spotify Connect 整合（需要先設定 spotify_config.json）')
    args = parser.parse_args()
    
    # 設定日誌
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 50)
    print("演示模式 - Luxgen M7 數位儀表板")
    print("無需 CAN Bus 硬體")
    print("=" * 50)
    print()
    print("功能:")
    print("  - 自動模擬車輛行駛狀態")
    print("  - 怠速 → 加速 → 巡航 → 減速 循環")
    
    # Spotify 整合狀態
    spotify_enabled = False
    spotify_listener = None
    
    if args.spotify:
        if not SPOTIFY_AVAILABLE:
            print("\n⚠️  Spotify 模組未安裝")
            print("   請執行: pip install spotipy requests Pillow")
        else:
            print("  - 🎵 Spotify Connect 整合 (即時播放資訊)")
            try:
                auth = SpotifyAuthManager()
                
                # 檢查是否已有快取的 token
                if not auth.is_authenticated():
                    print("\n需要授權 Spotify...")
                    print("選擇授權方式：")
                    print("  [1] 瀏覽器授權（自動開啟瀏覽器）")
                    print("  [2] QR Code 授權（使用手機掃描）")
                    
                    # 在觸控螢幕環境下預設使用 QR Code
                    use_qr = input("請選擇 (預設 2): ").strip() or "2"
                    
                    if use_qr == "2":
                        from spotify_qr_auth import show_qr_auth_dialog
                        print("\n開啟 QR Code 授權視窗...")
                        try:
                            if not show_qr_auth_dialog(auth):
                                print("\n❌ QR 授權失敗或已取消")
                                auth = None
                        except Exception as qr_error:
                            print(f"\n❌ QR 授權過程錯誤: {qr_error}")
                            auth = None
                    else:
                        if not auth.authenticate():
                            print("\n❌ 瀏覽器授權失敗")
                            auth = None
                
                # 確保認證完全成功才初始化 Spotify Listener
                if auth and auth.is_authenticated() and auth.get_client():
                    spotify_listener = SpotifyListener(auth, update_interval=1.0)
                    spotify_enabled = True
                    print("\n✅ Spotify 認證成功")
                else:
                    print("\n將使用模擬音樂資料")
                    auth = None
                    
            except Exception as e:
                print(f"\n⚠️  Spotify 初始化失敗: {e}")
                print("   將使用模擬音樂資料")
    else:
        print("  - 模擬音樂播放器")
        print("\n💡 提示: 使用 --spotify 參數啟用 Spotify Connect")
    
    print()
    print("控制方式:")
    print("  鍵盤:")
    print("    W/S: 加速/減速")
    print("    Q/E: 降低/升高水溫")
    print("    A/D: 減少/增加油量")
    print("    1-6: 切換檔位 (P/R/N/D/S/L)")
    print("    ←/→: 切換右側卡片")
    print()
    print("  觸控/滑鼠:")
    print("    在右側區域向左/右滑動: 切換油量表 ⇄ 音樂播放器")
    print("    滾動滑輪: 切換卡片 (桌面模式)")
    print()
    print("  圓點指示器:")
    print("    右側底部圓點顯示當前卡片位置")
    print()
    print("按 Ctrl+C 或關閉視窗退出")
    print("=" * 50)
    
    app = QApplication(sys.argv)
    dashboard = Dashboard()
    
    if spotify_enabled:
        dashboard.setWindowTitle("Luxgen M7 儀表板 - 演示模式 [Spotify Connected]")
    else:
        dashboard.setWindowTitle("Luxgen M7 儀表板 - 演示模式")
    
    # 建立車輛資料訊號橋接器
    vehicle_signals = VehicleSignals()
    
    # 連接車輛資料 Signals 到 Dashboard Slots
    vehicle_signals.update_rpm.connect(dashboard.set_rpm)
    vehicle_signals.update_speed.connect(dashboard.set_speed)
    vehicle_signals.update_temp.connect(dashboard.set_temperature)
    vehicle_signals.update_fuel.connect(dashboard.set_fuel)
    vehicle_signals.update_gear.connect(dashboard.set_gear)
    
    dashboard.show()
    
    # 建立模擬器
    simulator = VehicleSimulator()
    
    # 設定 Spotify 回調
    if spotify_enabled:
        # 建立訊號橋接器
        spotify_signals = SpotifySignals()
        
        def update_track_info(track_info):
            """在主執行緒更新歌曲資訊"""
            dashboard.music_card.set_song(track_info['name'], track_info['artists'])
            if track_info.get('album_art'):
                dashboard.music_card.set_album_art_from_pil(track_info['album_art'])
                
        def update_album_art(album_art):
            """在主執行緒更新專輯封面"""
            dashboard.music_card.set_album_art_from_pil(album_art)
            
        def update_progress(progress_data):
            """在主執行緒更新進度"""
            progress_ms = progress_data['progress_ms']
            duration_ms = progress_data['duration_ms']
            dashboard.music_card.set_progress(progress_ms / 1000, duration_ms / 1000)
            
        # 連接訊號到 UI 更新函數
        spotify_signals.track_changed.connect(update_track_info)
        spotify_signals.album_art_loaded.connect(update_album_art)
        spotify_signals.progress_updated.connect(update_progress)
        
        # 回調函數只負責發送訊號
        def on_track_change(track_info):
            logging.info(f"新歌曲: {track_info['name']} - {track_info['artists']}")
            spotify_signals.track_changed.emit(track_info)
        
        def on_album_art_loaded(album_art):
            logging.info("專輯封面已載入")
            spotify_signals.album_art_loaded.emit(album_art)
        
        def on_progress_update(progress_data):
            spotify_signals.progress_updated.emit(progress_data)
        
        spotify_listener.set_callback('on_track_change', on_track_change)
        spotify_listener.set_callback('on_album_art_loaded', on_album_art_loaded)
        spotify_listener.set_callback('on_progress_update', on_progress_update)
        spotify_listener.start()
        
        logging.info("Spotify 監聽器已啟動（非同步圖片載入）")
    
    # 建立定時器更新數據
    def update_data():
        """定時器回調 - 使用 Signal/Slot 機制確保架構一致性"""
        simulator.update(0.1)
        
        # ✅ 使用 Signal 發送資料更新（保持與 datagrab.py 一致的架構）
        vehicle_signals.update_speed.emit(simulator.speed)
        vehicle_signals.update_rpm.emit(simulator.rpm)
        vehicle_signals.update_fuel.emit(simulator.fuel)
        vehicle_signals.update_temp.emit(simulator.temp)
        vehicle_signals.update_gear.emit(simulator.gear)
        
        # 如果沒有啟用 Spotify，使用模擬音樂
        # 注意：這裡直接呼叫 music_card 方法是安全的，因為在主執行緒
        if not spotify_enabled:
            song_title, artist, _ = simulator.playlist[simulator.current_song_index]
            dashboard.music_card.set_song(song_title, artist)
            dashboard.music_card.set_progress(simulator.music_time, simulator.song_duration)
    
    timer = QTimer()
    timer.timeout.connect(update_data)
    timer.start(100)  # 每 100ms 更新一次 (10 Hz)
    
    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\n程式結束")
        timer.stop()
        if spotify_listener:
            spotify_listener.stop()


if __name__ == '__main__':
    main()
