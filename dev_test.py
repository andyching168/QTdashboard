#!/usr/bin/env python3
"""
開發測試腳本：同進程執行 GPS/OBD 模擬 + Dashboard
用於在沒有硬體的 Linux 開發機上測試速度校正存檔等功能

此腳本直接注入數據到 Dashboard，不需要真實 GPS 硬體。
"""
import os
import sys
import time
import math
import threading

# 確保可以 import 專案模組
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 全域變數，用於執行緒間共享 Dashboard 參考
_dashboard = None
_stop_flag = False


def simulator_thread(speed_kmh=50.0, obd_offset=3.0, mode="fixed"):
    """
    模擬器執行緒 - 直接注入數據到 Dashboard
    """
    global _dashboard, _stop_flag
    import datagrab
    
    start = time.time()
    
    print(f"[Simulator] 等待 Dashboard 啟動...")
    
    # 等待 Dashboard 初始化完成
    while _dashboard is None and not _stop_flag:
        time.sleep(0.1)
    
    if _stop_flag:
        return
        
    print(f"[Simulator] 開始模擬 - GPS速度={speed_kmh} km/h, OBD偏移=+{obd_offset} km/h, 模式={mode}")
    
    while not _stop_flag:
        try:
            t = time.time() - start
            
            # 速度模式
            if mode == "sine":
                # 30 秒一個週期，速度在 0 ~ speed_kmh 之間變化
                gps_speed = max(0.0, speed_kmh * (0.5 + 0.5 * math.sin(2 * math.pi * t / 30.0)))
            else:
                gps_speed = speed_kmh
            
            # OBD 速度 = GPS 速度 + 偏移（模擬車速錶偏快）
            obd_speed = gps_speed + obd_offset
            
            # 更新 datagrab 數據
            datagrab.data_store["OBD"]["speed"] = obd_speed
            datagrab.data_store["OBD"]["speed_smoothed"] = obd_speed
            datagrab.data_store["OBD"]["last_update"] = time.time()
            
            # RPM 跟速度連動
            fake_rpm = 800 + (gps_speed / 120.0) * 4000
            datagrab.data_store["OBD"]["rpm"] = fake_rpm
            
            # ===== 設定 Dashboard 狀態 =====
            # 1. 設定 GPS 已定位（直接設定變數，UI 由 gps_monitor_thread 的 signal 更新）
            _dashboard.is_gps_fixed = True
            _dashboard.current_gps_speed = gps_speed
            
            # 2. 透過 GPSMonitorThread 的 signal 更新 GPS 圖示（如果有的話）
            if hasattr(_dashboard, 'gps_monitor_thread') and _dashboard.gps_monitor_thread:
                _dashboard.gps_monitor_thread.gps_fixed_changed.emit(True)
                _dashboard.gps_monitor_thread.gps_speed_changed.emit(gps_speed)
            
            # 3. 透過 Dashboard 的 signal 更新 UI（速度和轉速）
            #    Dashboard 有自己的 signal: signal_update_speed, signal_update_rpm
            speed_correction = datagrab.get_speed_correction()
            corrected_speed = obd_speed * speed_correction
            _dashboard.signal_update_speed.emit(corrected_speed)
            _dashboard.signal_update_rpm.emit(fake_rpm / 1000.0)
            
            # 每秒輸出一次狀態
            print(f"\r[Sim] GPS={gps_speed:5.1f} OBD={obd_speed:5.1f} 顯示={corrected_speed:5.1f} 校正={speed_correction:.4f}", end="", flush=True)
            
            time.sleep(1.0)
            
        except Exception as e:
            print(f"\n[Simulator] 錯誤: {e}")
            import traceback
            traceback.print_exc()
            break
    
    print("\n[Simulator] 已停止")


def main():
    global _dashboard, _stop_flag
    
    import argparse
    parser = argparse.ArgumentParser(description="開發測試：GPS/OBD 模擬 + Dashboard")
    parser.add_argument("--speed", type=float, default=50.0, help="GPS 速度 (km/h)")
    parser.add_argument("--obd-offset", type=float, default=3.0, help="OBD 速度偏移量 (km/h)")
    parser.add_argument("--mode", choices=["fixed", "sine"], default="fixed", help="速度模式")
    args = parser.parse_args()
    
    # ===== 先建立 QApplication =====
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    
    print("=" * 60)
    print("開發測試模式（直接注入模擬數據）")
    print(f"GPS 速度: {args.speed} km/h")
    print(f"OBD 速度: {args.speed + args.obd_offset} km/h (偏移 +{args.obd_offset})")
    print(f"模式: {args.mode}")
    print("=" * 60)
    print("校正邏輯：ratio = GPS / OBD")
    print(f"預期校正係數會趨向: {args.speed / (args.speed + args.obd_offset):.4f}")
    print("=" * 60)
    
    # 啟動模擬器執行緒
    sim_thread = threading.Thread(
        target=simulator_thread,
        args=(args.speed, args.obd_offset, args.mode),
        daemon=True
    )
    sim_thread.start()
    
    # 啟動 Dashboard
    print("\n啟動 Dashboard...\n")
    
    from main import Dashboard, SplashScreen
    
    # 顯示啟動畫面
    splash = SplashScreen()
    splash.show()
    
    # 建立 Dashboard
    dashboard = Dashboard()
    
    # 啟動畫面完成後顯示 Dashboard
    def on_splash_finished():
        global _dashboard
        splash.close()
        dashboard.show()
        dashboard.start_dashboard()
        # 設定全域參考，讓模擬器執行緒可以存取
        _dashboard = dashboard
        print("[Dashboard] 已啟動，模擬器開始注入數據")
    
    splash.finished.connect(on_splash_finished)
    
    # 執行 Qt 事件迴圈
    ret = app.exec()
    
    # 清理
    _stop_flag = True
    sim_thread.join(timeout=2.0)
    
    sys.exit(ret)


if __name__ == "__main__":
    main()
