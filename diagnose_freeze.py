#!/usr/bin/env python3
"""
凍結問題診斷工具
在 RPi4 上執行此腳本來分析凍結的原因

使用方式：
    PERF_MONITOR=1 python main.py

或執行此診斷腳本：
    python diagnose_freeze.py
"""

import gc
import sys
import time
import threading
import psutil
import os

def get_memory_info():
    """取得記憶體使用資訊"""
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return {
        'rss_mb': mem_info.rss / 1024 / 1024,
        'vms_mb': mem_info.vms / 1024 / 1024,
    }

def get_gc_info():
    """取得 GC 資訊"""
    return {
        'counts': gc.get_count(),
        'threshold': gc.get_threshold(),
        'objects': len(gc.get_objects()),
    }

def monitor_gc_performance():
    """監控 GC 效能"""
    print("=" * 60)
    print("Python GC 效能監控")
    print("=" * 60)
    
    gc.set_debug(gc.DEBUG_STATS)  # 啟用 GC 除錯輸出
    
    # 記錄 GC 前後的時間
    gc_times = []
    
    for i in range(5):
        print(f"\n--- 第 {i+1} 次全量 GC ---")
        gc_info_before = get_gc_info()
        mem_before = get_memory_info()
        
        start = time.perf_counter()
        collected = gc.collect()  # 全量 GC
        duration = (time.perf_counter() - start) * 1000
        
        gc_info_after = get_gc_info()
        mem_after = get_memory_info()
        
        gc_times.append(duration)
        
        print(f"GC 耗時: {duration:.1f} ms")
        print(f"回收物件: {collected}")
        print(f"記憶體變化: {mem_before['rss_mb']:.1f} -> {mem_after['rss_mb']:.1f} MB")
        print(f"物件數量: {gc_info_before['objects']} -> {gc_info_after['objects']}")
        
        # 創建一些物件來模擬應用程式運行
        dummy = [list(range(1000)) for _ in range(1000)]
        del dummy
        time.sleep(1)
    
    gc.set_debug(0)  # 關閉 GC 除錯輸出
    
    print("\n" + "=" * 60)
    print("GC 效能摘要")
    print("=" * 60)
    avg_time = sum(gc_times) / len(gc_times)
    max_time = max(gc_times)
    print(f"平均 GC 時間: {avg_time:.1f} ms")
    print(f"最大 GC 時間: {max_time:.1f} ms")
    
    if max_time > 100:
        print("\n⚠️ 警告：GC 時間過長，可能導致 UI 凍結！")
        print("建議：")
        print("  1. 調整 GC 閾值：gc.set_threshold(50000, 500, 100)")
        print("  2. 使用增量式 GC：定期執行 gc.collect(0)")
    
    return avg_time, max_time

def check_thread_blocking():
    """檢查執行緒阻塞"""
    print("\n" + "=" * 60)
    print("執行緒狀態檢查")
    print("=" * 60)
    
    for thread in threading.enumerate():
        print(f"  - {thread.name}: {'daemon' if thread.daemon else 'normal'}")

def check_io_operations():
    """檢查可能的 I/O 阻塞"""
    print("\n" + "=" * 60)
    print("I/O 操作檢查")
    print("=" * 60)
    
    # 檢查 spotify_config.json 讀取時間
    import json
    config_files = ['spotify_config.json', 'mqtt_config.json', 'odometer_data.json']
    
    for config_file in config_files:
        config_path = os.path.join(os.path.dirname(__file__), config_file)
        if os.path.exists(config_path):
            start = time.perf_counter()
            with open(config_path, 'r') as f:
                data = f.read()
            duration = (time.perf_counter() - start) * 1000
            print(f"  {config_file}: {duration:.2f} ms ({len(data)} bytes)")
        else:
            print(f"  {config_file}: 不存在")
    
    # 檢查圖片載入時間
    print("\n圖片載入檢查:")
    sprite_path = os.path.join(os.path.dirname(__file__), 'carSprite')
    if os.path.exists(sprite_path):
        for img_file in ['closed_base.png', 'FL.png', 'FR.png']:
            img_path = os.path.join(sprite_path, img_file)
            if os.path.exists(img_path):
                start = time.perf_counter()
                with open(img_path, 'rb') as f:
                    data = f.read()
                duration = (time.perf_counter() - start) * 1000
                print(f"  {img_file}: {duration:.2f} ms ({len(data)/1024:.1f} KB)")

def check_network_latency():
    """檢查網路延遲"""
    print("\n" + "=" * 60)
    print("網路延遲檢查")
    print("=" * 60)
    
    import socket
    
    targets = [
        ("8.8.8.8", 53, "Google DNS"),
        ("1.1.1.1", 53, "Cloudflare DNS"),
        ("api.spotify.com", 443, "Spotify API"),
    ]
    
    for host, port, name in targets:
        try:
            start = time.perf_counter()
            sock = socket.create_connection((host, port), timeout=5)
            duration = (time.perf_counter() - start) * 1000
            sock.close()
            print(f"  {name}: {duration:.1f} ms ✓")
        except Exception as e:
            print(f"  {name}: 連線失敗 - {e}")

def main():
    print("=" * 60)
    print("QTDashboard 凍結問題診斷工具")
    print("=" * 60)
    print()
    
    print("系統資訊:")
    print(f"  Python: {sys.version}")
    print(f"  CPU: {psutil.cpu_count()} 核心")
    print(f"  記憶體: {psutil.virtual_memory().total / 1024 / 1024 / 1024:.1f} GB")
    print(f"  可用記憶體: {psutil.virtual_memory().available / 1024 / 1024 / 1024:.1f} GB")
    
    # 檢查 I/O 操作
    check_io_operations()
    
    # 檢查網路延遲
    check_network_latency()
    
    # 檢查執行緒
    check_thread_blocking()
    
    # 監控 GC 效能
    avg_gc, max_gc = monitor_gc_performance()
    
    print("\n" + "=" * 60)
    print("診斷結論")
    print("=" * 60)
    
    issues = []
    
    if max_gc > 100:
        issues.append("GC 時間過長")
    
    if psutil.virtual_memory().available < 500 * 1024 * 1024:  # < 500MB
        issues.append("可用記憶體不足")
    
    if issues:
        print("發現潛在問題:")
        for issue in issues:
            print(f"  ⚠️ {issue}")
        
        print("\n建議解決方案:")
        print("  1. 在 main.py 開頭加入：")
        print("     import gc")
        print("     gc.set_threshold(50000, 500, 100)")
        print()
        print("  2. 執行時啟用效能監控：")
        print("     PERF_MONITOR=1 python main.py")
    else:
        print("  ✓ 未發現明顯問題")
        print()
        print("如果問題持續，請執行：")
        print("  PERF_MONITOR=1 python main.py")
        print("並觀察卡頓時的輸出訊息")

if __name__ == '__main__':
    main()
