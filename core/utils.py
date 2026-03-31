import os
import time
import gc
import json
import platform
from collections import deque
from functools import wraps
from pathlib import Path


def is_raspberry_pi():
    """檢測是否在樹莓派上運行"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            return 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo
    except:
        return False


def is_production_environment():
    """
    檢測是否為生產環境（應使用全螢幕）
    
    Returns:
        bool: True = 生產環境（樹莓派或 Linux 嵌入式），False = 開發環境（Mac/Windows）
    """
    if is_raspberry_pi():
        return True
    
    if os.environ.get('QTDASHBOARD_FULLSCREEN', '').lower() in ('1', 'true', 'yes'):
        return True
    
    system = platform.system()
    if system in ('Darwin', 'Windows'):
        return False
    
    if system == 'Linux':
        if os.environ.get('DISPLAY'):
            has_desktop = os.environ.get('XDG_CURRENT_DESKTOP') or os.environ.get('DESKTOP_SESSION')
            return not has_desktop
    
    return False


class PerformanceMonitor:
    """效能監控器 - 追蹤函數執行時間"""
    
    _instance = None
    SLOW_THRESHOLD_MS = 16
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self._initialized = True
        self.enabled = os.environ.get('PERF_MONITOR', '').lower() in ('1', 'true', 'yes')
        self.slow_calls = deque(maxlen=100)
        self.stats = {}
        self._report_timer = None
        self._frame_start = None
        self._frame_times = deque(maxlen=60)
    
    def start_frame(self):
        if self.enabled:
            self._frame_start = time.perf_counter()
    
    def end_frame(self, context: str = ""):
        if not self.enabled or self._frame_start is None:
            return
        
        duration_ms = (time.perf_counter() - self._frame_start) * 1000
        self._frame_times.append(duration_ms)
        
        if duration_ms > self.SLOW_THRESHOLD_MS:
            print(f"⚠️ [PERF] 幀延遲: {duration_ms:.1f}ms {context}")
            self.slow_calls.append({
                'func': f"Frame: {context}" if context else "Frame",
                'duration_ms': duration_ms,
                'time': time.time()
            })
    
    def track(self, func_name: str, duration_ms: float):
        if not self.enabled:
            return
        
        if func_name not in self.stats:
            self.stats[func_name] = {'count': 0, 'total_ms': 0, 'max_ms': 0, 'slow_count': 0}
        
        stat = self.stats[func_name]
        stat['count'] += 1
        stat['total_ms'] += duration_ms
        stat['max_ms'] = max(stat['max_ms'], duration_ms)
        
        if duration_ms > self.SLOW_THRESHOLD_MS:
            stat['slow_count'] += 1
            self.slow_calls.append({
                'func': func_name,
                'duration_ms': duration_ms,
                'time': time.time()
            })
            print(f"⚠️ [PERF] 慢呼叫: {func_name} 耗時 {duration_ms:.1f}ms")
    
    def report(self):
        if not self.stats:
            print("[PERF] 無統計資料")
            return
        
        print("\n" + "=" * 60)
        print("📊 效能報告")
        print("=" * 60)
        
        sorted_stats = sorted(
            self.stats.items(), 
            key=lambda x: x[1]['slow_count'], 
            reverse=True
        )
        
        print(f"{'函數名稱':<40} {'呼叫次數':>8} {'慢呼叫':>6} {'平均ms':>8} {'最大ms':>8}")
        print("-" * 60)
        
        for func_name, stat in sorted_stats[:20]:
            avg_ms = stat['total_ms'] / stat['count'] if stat['count'] > 0 else 0
            print(f"{func_name:<40} {stat['count']:>8} {stat['slow_count']:>6} {avg_ms:>8.1f} {stat['max_ms']:>8.1f}")
        
        print("=" * 60)
        
        if self.slow_calls:
            print("\n🐢 最近 10 個慢呼叫:")
            for call in list(self.slow_calls)[-10:]:
                print(f"  - {call['func']}: {call['duration_ms']:.1f}ms")
        print()


class JankDetector:
    """卡頓偵測器 - 使用 QTimer 偵測主執行緒阻塞"""
    
    def __init__(self, threshold_ms=50):
        self.threshold_ms = threshold_ms
        self.last_tick = None
        self.enabled = os.environ.get('PERF_MONITOR', '').lower() in ('1', 'true', 'yes')
        self.timer = None
        self.jank_count = 0
        self.start_time = None
        self.jank_log = []
    
    def start(self):
        if not self.enabled:
            return
        
        from PyQt6.QtCore import QTimer
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)
        self.last_tick = time.perf_counter()
        self.start_time = time.perf_counter()
        print("[JankDetector] 卡頓偵測器已啟動（閾值: 50ms）")
    
    def _tick(self):
        now = time.perf_counter()
        if self.last_tick is not None:
            elapsed_ms = (now - self.last_tick) * 1000
            if elapsed_ms > self.threshold_ms:
                self.jank_count += 1
                time_since_start = now - self.start_time if self.start_time else 0
                
                gc_counts = gc.get_count()
                gc_info = f" (GC: {gc_counts})"
                
                print(f"🔴 [JANK] 主執行緒阻塞 {elapsed_ms:.0f}ms{gc_info} (累計: {self.jank_count}, 啟動後 {time_since_start:.1f}s)")
                
                self.jank_log.append({
                    'time': time_since_start,
                    'duration_ms': elapsed_ms,
                    'gc_counts': gc_counts
                })
                if len(self.jank_log) > 20:
                    self.jank_log.pop(0)
        self.last_tick = now
    
    def stop(self):
        if self.timer:
            self.timer.stop()
            if self.jank_count > 0:
                print(f"[JankDetector] 總共偵測到 {self.jank_count} 次卡頓")
                
                if len(self.jank_log) >= 2:
                    intervals = []
                    for i in range(1, len(self.jank_log)):
                        interval = self.jank_log[i]['time'] - self.jank_log[i-1]['time']
                        intervals.append(interval)
                    avg_interval = sum(intervals) / len(intervals)
                    print(f"[JankDetector] 平均卡頓間隔: {avg_interval:.1f} 秒")


def perf_track(func):
    """裝飾器 - 追蹤函數執行時間"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        monitor = PerformanceMonitor()
        if not monitor.enabled:
            return func(*args, **kwargs)
        
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            if args and hasattr(args[0], '__class__'):
                func_name = f"{args[0].__class__.__name__}.{func.__name__}"
            else:
                func_name = func.__name__
            monitor.track(func_name, duration_ms)
    return wrapper


class OdometerStorage:
    """ODO 和 Trip 資料的持久化存儲（非同步節流寫入）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self._initialized = True
        
        if platform.system() == 'Windows':
            config_dir = Path(os.environ.get('APPDATA', '.')) / 'QTDashboard'
        else:
            config_dir = Path.home() / '.config' / 'qtdashboard'
        
        config_dir.mkdir(parents=True, exist_ok=True)
        self.data_file = config_dir / 'odometer_data.json'
        
        self.data = {
            'odo_total': 0.0,
            'trip1_distance': 0.0,
            'trip2_distance': 0.0,
            'trip1_reset_time': None,
            'trip2_reset_time': None,
            'last_update': None
        }
        
        self._dirty = False
        self._last_save_time = 0
        self._save_interval = 10.0
        self._save_timer = None
        self._lock = None
        
        self.load()
    
    def _get_lock(self):
        if self._lock is None:
            import threading
            self._lock = threading.Lock()
        return self._lock
    
    def load(self):
        try:
            if self.data_file.exists():
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    saved_data = json.load(f)
                    self.data.update(saved_data)
                    print(f"[Storage] 已載入里程資料: ODO={self.data['odo_total']:.1f}km, "
                          f"Trip1={self.data['trip1_distance']:.1f}km, "
                          f"Trip2={self.data['trip2_distance']:.1f}km")
        except Exception as e:
            print(f"[Storage] 載入里程資料失敗: {e}")
    
    def _do_save(self):
        try:
            with self._get_lock():
                if not self._dirty:
                    return
                data_copy = self.data.copy()
                data_copy['last_update'] = time.time()
                self._dirty = False
                self._last_save_time = time.time()
            
            import uuid
            temp_file = self.data_file.with_suffix(f'.{uuid.uuid4().hex}.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data_copy, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.data_file)
        except Exception as e:
            print(f"[Storage] 儲存里程資料失敗: {e}")
    
    def _schedule_save(self):
        import threading
        
        now = time.time()
        time_since_last_save = now - self._last_save_time
        
        if time_since_last_save >= self._save_interval:
            threading.Thread(target=self._do_save, daemon=True).start()
        else:
            if self._save_timer is None or not self._save_timer.is_alive():
                delay = self._save_interval - time_since_last_save
                self._save_timer = threading.Timer(delay, self._do_save)
                self._save_timer.daemon = True
                self._save_timer.start()
    
    def _mark_dirty(self):
        self._dirty = True
        self._schedule_save()
    
    def save_now(self):
        if self._save_timer:
            self._save_timer.cancel()
        self._dirty = True
        self._do_save()
        print("[Storage] 里程資料已儲存")
    
    def update_odo(self, value: float):
        self.data['odo_total'] = value
        self._mark_dirty()
    
    def update_trip1(self, distance: float, reset_time: float = None):
        self.data['trip1_distance'] = distance
        if reset_time is not None:
            self.data['trip1_reset_time'] = reset_time
        self._mark_dirty()
    
    def update_trip2(self, distance: float, reset_time: float = None):
        self.data['trip2_distance'] = distance
        if reset_time is not None:
            self.data['trip2_reset_time'] = reset_time
        self._mark_dirty()
    
    def get_odo(self) -> float:
        return self.data.get('odo_total', 0.0)
    
    def get_trip1(self) -> tuple:
        return (self.data.get('trip1_distance', 0.0), 
                self.data.get('trip1_reset_time'))
    
    def get_trip2(self) -> tuple:
        return (self.data.get('trip2_distance', 0.0), 
                self.data.get('trip2_reset_time'))
