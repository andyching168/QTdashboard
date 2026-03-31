# Auto-extracted from main.py
import time
import glob
import os
import platform
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

class GPSMonitorThread(QThread):
    """
    GPS 狀態監控執行緒
    - 掃描 /dev/ttyUSB* 和 /dev/ttyACM*
    - 使用 38400 baud detection
    - 監控是否定位完成 (Fix)
    - 提取座標資訊
    """
    gps_fixed_changed = pyqtSignal(bool)
    gps_speed_changed = pyqtSignal(float)
    gps_position_changed = pyqtSignal(float, float)  # lat, lon
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.baud_rate = 38400
        self._last_fix_status = False
        self._current_port = None
        self._last_lat = None
        self._last_lon = None
        
    def run(self):
        print("[GPS] Starting monitor thread...")
        while self.running:
            # 1. 如果沒有鎖定 port，進行掃描
            if not self._current_port:
                ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*') + glob.glob('/dev/pts/*')
                if not ports:
                    self._update_status(False)
                    time.sleep(2)
                    continue
                
                # 簡單策略：嘗試每一個 port
                found = False
                for port in ports:
                    if self._try_connect(port):
                        self._current_port = port
                        found = True
                        break
                
                if not found:
                    time.sleep(2)
            else:
                # 2. 已鎖定 port，持續讀取
                if not self._read_loop():
                    # 讀取失敗（斷線），重置 port
                    print(f"[GPS] Connection lost on {self._current_port}")
                    self._current_port = None
                    self._update_status(False)
                    time.sleep(1)
                    
    def _try_connect(self, port):
        """測試連接"""
        try:
            with serial.Serial(port, self.baud_rate, timeout=1.0) as ser:
                # 讀取幾行看看是不是 NMEA
                for _ in range(5):
                    line = ser.readline()
                    try:
                        line_str = line.decode('ascii', errors='ignore').strip()
                        if line_str.startswith('$'):
                            print(f"[GPS] Found GPS on {port} @ {self.baud_rate}")
                            return True
                    except:
                        pass
        except:
            pass
        return False
        
    def _read_loop(self):
        """持續讀取迴圈"""
        try:
            with serial.Serial(self._current_port, self.baud_rate, timeout=1.0) as ser:
                while self.running:
                    line = ser.readline()
                    if not line:
                        # Timeout，可能沒資料，但不一定斷線
                        continue
                        
                    try:
                        line_str = line.decode('ascii', errors='ignore').strip()
                        
                        # 簡單解析 Fix 狀態
                        is_fixed = False
                        has_status = False
                        
                        if line_str.startswith('$GNGGA') or line_str.startswith('$GPGGA'):
                            parts = line_str.split(',')
                            if len(parts) >= 7:
                                # Quality: 0=Invalid, 1=GPS, 2=DGPS...
                                has_status = True
                                is_fixed = (parts[6] != '0')
                                
                        if line_str.startswith('$GNRMC') or line_str.startswith('$GPRMC'):
                            parts = line_str.split(',')
                            if len(parts) >= 3:
                                # Status: A=Active, V=Void
                                has_status = True
                                is_fixed = (parts[2] == 'A')
                                
                                # Parse Speed (Field 7, in Knots)
                                if is_fixed and len(parts) >= 8:
                                    try:
                                        speed_knots = float(parts[7])
                                        speed_kmh = speed_knots * 1.852
                                        self.gps_speed_changed.emit(speed_kmh)
                                    except (ValueError, IndexError):
                                        pass
                                
                                # Parse Position (Fields 3-6: lat, N/S, lon, E/W)
                                if is_fixed and len(parts) >= 7:
                                    try:
                                        lat_raw = parts[3]  # DDMM.MMMM
                                        lat_dir = parts[4]  # N or S
                                        lon_raw = parts[5]  # DDDMM.MMMM
                                        lon_dir = parts[6]  # E or W
                                        
                                        if lat_raw and lon_raw:
                                            # Convert NMEA format to decimal degrees
                                            lat_deg = float(lat_raw[:2])
                                            lat_min = float(lat_raw[2:])
                                            lat = lat_deg + lat_min / 60.0
                                            if lat_dir == 'S':
                                                lat = -lat
                                            
                                            lon_deg = float(lon_raw[:3])
                                            lon_min = float(lon_raw[3:])
                                            lon = lon_deg + lon_min / 60.0
                                            if lon_dir == 'W':
                                                lon = -lon
                                            
                                            # 只在座標變化時發送（避免頻繁更新）
                                            if self._last_lat != lat or self._last_lon != lon:
                                                self._last_lat = lat
                                                self._last_lon = lon
                                                self.gps_position_changed.emit(lat, lon)
                                    except (ValueError, IndexError):
                                        pass
                        
                        if has_status:
                            self._update_status(is_fixed)
                            
                    except ValueError:
                        pass
        except serial.SerialException as e:
            print(f"[GPS] Serial error: {e}")
            return False # 斷線
        except Exception as e:
            print(f"[GPS] Error: {e}")
            return False
            
        return True

    def stop(self):
        """停止監控並釋放資源"""
        self.running = False
        self.wait() # 等待執行緒結束
        print("[GPS] Monitor thread stopped.")

    def _update_status(self, is_fixed):
        if is_fixed != self._last_fix_status:
            self._last_fix_status = is_fixed
            self.gps_fixed_changed.emit(is_fixed)
            status = "FIXED" if is_fixed else "SEARCHING"
            print(f"[GPS] Status changed: {status}")


class RadarMonitorThread(QThread):
    """
    ESP32 雷達訊號監控執行緒
    - 掃描 serial ports
    - 使用 115200 baud detection
    - 識別 (LR:x,RR:x,LF:x,RF:x) 格式
    """
    radar_message_received = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.baud_rate = 115200
        self._current_port = None
        
    def run(self):
        print("[Radar] Starting monitor thread...")
        while self.running:
            # 1. 如果沒有鎖定 port，進行掃描
            if not self._current_port:
                ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*') + glob.glob('/dev/pts/*')
                # 在 macOS 上增加額外的裝置路徑模式
                if platform.system() == 'Darwin':
                    ports += glob.glob('/dev/cu.usb*') + glob.glob('/dev/cu.SLAB*')
                    
                if not ports:
                    time.sleep(2)
                    continue
                
                # 嘗試每一個 port
                found = False
                for port in ports:
                    if self._try_connect(port):
                        self._current_port = port
                        found = True
                        break
                
                if not found:
                    time.sleep(2)
            else:
                # 2. 已鎖定 port，持續讀取
                if not self._read_loop():
                    # 讀取失敗（斷線），重置 port
                    print(f"[Radar] Connection lost on {self._current_port}")
                    self._current_port = None
                    time.sleep(1)
                    
    def _try_connect(self, port):
        """測試連接"""
        try:
            # 嘗試開啟 serial port
            with serial.Serial(port, self.baud_rate, timeout=1.0) as ser:
                # 讀取幾行看看是不是雷達數據
                for _ in range(10): # 嘗試多讀幾行，確保有足夠機會抓到
                    line = ser.readline()
                    try:
                        line_str = line.decode('ascii', errors='ignore').strip()
                        # 檢查特徵：包含 'LR:' 和 'RR:' 和 'LF:' 和 'RF:' (支援有括號或無括號格式)
                        if 'LR:' in line_str and 'RR:' in line_str and 'LF:' in line_str and 'RF:' in line_str:
                            print(f"[Radar] Found Radar on {port} @ {self.baud_rate}")
                            print(f"[Radar] Sample data: {line_str}")
                            return True
                    except:
                        pass
        except:
            pass
        return False
        
    def _read_loop(self):
        """持續讀取迴圈"""
        try:
            with serial.Serial(self._current_port, self.baud_rate, timeout=1.0) as ser:
                while self.running:
                    line = ser.readline()
                    if not line:
                        continue
                        
                    try:
                        line_str = line.decode('ascii', errors='ignore').strip()
                        # 檢查是否包含雷達數據（支援有括號或無括號格式）
                        if 'LR:' in line_str and 'RR:' in line_str and 'LF:' in line_str and 'RF:' in line_str:
                            print(f"[Radar] Data: {line_str}")  # Debug 用
                            self.radar_message_received.emit(line_str)
                    except ValueError:
                        pass
        except serial.SerialException as e:
            print(f"[Radar] Serial error: {e}")
            return False # 斷線
        except Exception as e:
            print(f"[Radar] Error: {e}")
            return False
            
        return True

    def stop(self):
        self.running = False
        self.wait()


