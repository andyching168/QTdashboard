# Auto-extracted from main.py
import time
import glob
import os
import platform
import serial
import logging
import threading
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

logger = logging.getLogger(__name__)

# 共享鎖，防止 GPS 和 Radar 線程競爭同一個 serial port
_serial_lock = threading.Lock()

# === 雷達功能開關 ===
# 設為 False 可停用雷達掃描功能（連接埠偵測、資料讀取等全部跳過）
RADAR_ENABLED = False

class GPSMonitorThread(QThread):
    """
    GPS 狀態監控執行緒
    - 掃描 /dev/ttyUSB* 和 /dev/ttyACM*
    - 使用多組 baud 自動偵測（9600 / 38400）
    - 監控是否定位完成 (Fix)
    - 提取座標資訊
    - 支援外部 GPS 注入（MQTT 導航 payload）
    """
    gps_fixed_changed = pyqtSignal(bool)
    gps_speed_changed = pyqtSignal(float)
    gps_position_changed = pyqtSignal(float, float)  # lat, lon
    gps_source_changed = pyqtSignal(bool, bool)  # (is_internal, is_fresh)
    gps_device_status_changed = pyqtSignal(bool)  # True=device found, False=no device
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.baud_rates = [9600, 38400]
        self.baud_rate = self.baud_rates[0]
        self._last_fix_status = False
        self._current_port = None
        self._last_lat = None
        self._last_lon = None
        self._using_external_gps = False
        self._external_gps_timestamp = None
        self._has_device = None  # None=unknown, True=device found, False=no device
        self._last_mqtt_gps_time = 0  # 記錄上次收到 MQTT GPS 的本地時間（秒）
        # 與導航訊息新鮮度標準一致（15 秒）
        self._external_fresh_threshold = 15
        self._external_stale_threshold = 300
        self._search_without_device_count = 0  # 連續搜尋無結果次數
        
    def run(self):
        logger.info("[GPS] Starting monitor thread...")
        self._consecutive_failures = 0
        
        # 雷達功能關閉時，不需要等待雷達線程，直接開始掃描
        if not RADAR_ENABLED:
            logger.info("[GPS] RADAR_ENABLED=False，跳過等待雷達線程")
        else:
            # 等待雷達線程先鎖定其 port
            time.sleep(2)
        
        while self.running:
            # 1. 如果沒有鎖定 port，進行掃描
            if not self._current_port:
                ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
                ports = sorted(ports)
                
                if not ports:
                    self._update_device_status(found=False)
                    time.sleep(2)
                    continue
                
                # 發現至少一個 port，標記有裝置
                self._update_device_status(found=True)
                logger.info(f"[GPS] Found ports: {ports}")
                
                # 智能策略：自動識別 GPS vs Radar（使用鎖防止競爭）
                # 但雷達關閉時，無需偵測雷達
                if not RADAR_ENABLED:
                    # 雷達關閉：直接用 9600 baud 嘗試所有 port，不再嘗試 38400
                    target_bauds = [9600]
                    logger.info("[GPS] RADAR_ENABLED=False，直接用 9600 baud 掃描")
                else:
                    target_bauds = self.baud_rates
                
                found = False
                for port in ports:
                    for baud in target_bauds:
                        try:
                            with _serial_lock:
                                ser = serial.Serial(port, baud, timeout=0.3)
                                data_lines = []
                                for i in range(3):
                                    line = ser.readline()
                                    if line:
                                        s = line.decode('ascii', errors='ignore').strip()
                                    data_lines.append(s)
                                    # 識別 Radar，立即跳過（僅在雷達開啟時）
                                    if RADAR_ENABLED and 'LR:' in s and 'RF:' in s:
                                        ser.close()
                                        found = True
                                        break
                                    # 識別 GPS
                                    if ('$GPGGA' in s or '$GNGGA' in s or 
                                        '$GPRMC' in s or '$GNRMC' in s) and ',' in s:
                                        self._current_port = port
                                        self.baud_rate = baud
                                        self._consecutive_failures = 0
                                        ser.close()
                                        logger.info(f"[GPS] *** FOUND GPS on {port} @ {baud} ***")
                                        break
                            ser.close()
                            
                            # 如果檢測到乱码数据（不是GPS也不是Radar），可能port被佔用，快速跳過
                            if not found and not self._current_port and data_lines:
                                # 如果没有任何有效identifiers，可能是乱码
                                if not any(('$G' in d or 'LR:' in d) for d in data_lines):
                                    logger.info(f"[GPS] {port} @ {baud}: garbled data, skipping rest of port")
                                    break  # 跳過這個port的其餘baud
                                
                        except Exception as e:
                            pass
                        if self._current_port:
                            break
                    if self._current_port:
                        break
                
                if not self._current_port:
                    logger.info("[GPS] No GPS found, will retry...")
                    time.sleep(2)
                    time.sleep(2)
            else:
                # 2. 已鎖定 port，持續讀取
                success = self._read_loop()
                
                # 只有失敗時才計數（成功時重置）
                if not success:
                    self._consecutive_failures += 1
                else:
                    self._consecutive_failures = 0
                
                # 連續失敗超過 10 次視為真正的斷線
                if not success or self._consecutive_failures > 10:
                    if self._consecutive_failures > 10:
                        logger.warning(f"[GPS] Too many consecutive failures, treating as disconnection")
                    else:
                        logger.warning(f"[GPS] Connection lost on {self._current_port}")
                    self._current_port = None
                    self._update_status(False)
                    self._consecutive_failures = 0
                    time.sleep(1)
                    
    def _try_connect(self, port):
        """測試連接"""
        # 優先嘗試上一個成功的 baud rate，可加速重連
        candidate_bauds = [self.baud_rate] + [b for b in self.baud_rates if b != self.baud_rate]

        for baud in candidate_bauds:
            try:
                with serial.Serial(port, baud, timeout=0.3) as ser:
                    # 快速檢測：只讀取少量行（GGA/RMC 每秒1次，0.3秒內至少1-2行）
                    for _ in range(3):
                        line = ser.readline()
                        if not line:
                            continue
                        try:
                            line_str = line.decode('ascii', errors='ignore').strip()
                            if ((line_str.startswith('$GPGGA') or line_str.startswith('$GNGGA') or
                                 line_str.startswith('$GPRMC') or line_str.startswith('$GNRMC')) and
                                    ',' in line_str):
                                logger.info(f"[GPS] Found GPS on {port} @ {baud}")
                                return baud
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"[GPS] Error trying {port} @ {baud}: {e}")
        return None
        
    def _read_loop(self):
        """持續讀取迴圈"""
        try:
            with _serial_lock:
                ser = serial.Serial(self._current_port, self.baud_rate, timeout=1.0)
                while self.running:
                    line = ser.readline()
                    if not line:
                        # Timeout，可能沒資料，但不一定斷線
                        continue
                        
                    try:
                        line_str = line.decode('ascii', errors='ignore').strip()
                        
                        # 識別並跳過 Radar 數據
                        if 'LR:' in line_str and 'RF:' in line_str:
                            logger.warning(f"[GPS] Detected Radar data on {self._current_port}, need to rescan")
                            return False
                        
                        # 解析 GPS Fix 狀態
                        is_fixed = False
                        has_status = False
                        
                        # 優先使用 RMC 判斷 fix 狀態，因為 RMC 包含速度資訊且依賴 GGA 的有效定位
                        # 只有當 GGA quality >= 1 且 RMC status == 'A' 時才視為 fixed
                        gga_quality = None
                        rmc_status = None
                        
                        if line_str.startswith('$GNGGA') or line_str.startswith('$GPGGA'):
                            parts = line_str.split(',')
                            if len(parts) >= 7:
                                try:
                                    gga_quality = int(parts[6])
                                except (ValueError, IndexError):
                                    pass
                                
                        if line_str.startswith('$GNRMC') or line_str.startswith('$GPRMC'):
                            parts = line_str.split(',')
                            if len(parts) >= 3:
                                rmc_status = parts[2]
                                has_status = True
                                
                                # Parse Speed (Field 7, in Knots)
                                if len(parts) >= 8:
                                    try:
                                        speed_knots = float(parts[7])
                                        speed_kmh = speed_knots * 1.852
                                        self.gps_speed_changed.emit(speed_kmh)
                                    except (ValueError, IndexError):
                                        pass
                                
                                # Parse Position (Fields 3-6: lat, N/S, lon, E/W)
                                if len(parts) >= 7:
                                    try:
                                        lat_raw = parts[3]
                                        lat_dir = parts[4]
                                        lon_raw = parts[5]
                                        lon_dir = parts[6]
                                        
                                        if lat_raw and lon_raw:
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
                                            
                                            if self._last_lat != lat or self._last_lon != lon:
                                                self._last_lat = lat
                                                self._last_lon = lon
                                                self.gps_position_changed.emit(lat, lon)
                                    except (ValueError, IndexError):
                                        pass
                        
                        # 只有 GGA quality >= 1 且 RMC status == 'A' 才視為 fixed
                        if gga_quality is not None and rmc_status is not None:
                            is_fixed = (gga_quality >= 1 and rmc_status == 'A')
                        elif rmc_status is not None:
                            is_fixed = (rmc_status == 'A')
                        elif gga_quality is not None:
                            is_fixed = (gga_quality >= 1)
                        
                        if has_status:
                            self._update_status(is_fixed)
                            
                    except ValueError:
                        pass
        except serial.SerialException as e:
            # timeout 不應視為斷線，只打印一次避免刷屏
            if "timeout" not in str(e).lower():
                logger.error(f"[GPS] Serial error: {e}")
            return True  # Timeout 視為短暫無數據，不重置 port
        except Exception as e:
            logger.error(f"[GPS] Error: {e}")
            return False
            
        return True

    def stop(self):
        """停止監控並釋放資源"""
        self.running = False
        self.wait() # 等待執行緒結束
        logger.info("[GPS] Monitor thread stopped.")

    def inject_external_gps(self, lat: float, lon: float, speed: float, bearing: float, timestamp: str):
        """注入外部 GPS 資料（來自 MQTT 導航 payload）
        
        當內部 GPS 未定位時使用。
        使用本地時間判斷新鮮度，避免發送端時鐘漂移導致圖標閃爍。
        
        Args:
            lat: 緯度
            lon: 經度
            speed: 速度 (km/h)
            bearing: 方向角度
            timestamp: ISO 格式時間戳（不再用於新鮮度判斷，僅保留用於日誌）
        """
        FRESH_THRESHOLD = self._external_fresh_threshold      # 15 秒內：即時位置
        STALE_THRESHOLD = self._external_stale_threshold      # 5 分鐘內：最後位置
        # 超過 5 分鐘：忽略
        
        # 使用本地時間判斷新鮮度，避免發送端時鐘誤差
        current_time = time.time()
        time_since_last = current_time - self._last_mqtt_gps_time if self._last_mqtt_gps_time > 0 else 0
        
        # 超過 5 分鐘不使用
        if time_since_last > STALE_THRESHOLD and self._last_mqtt_gps_time > 0:
            logger.info(f"[GPS] External GPS data too old ({time_since_last:.1f}s since last msg), ignoring")
            return
        
        # 判斷是否為即時位置
        is_fresh = time_since_last <= FRESH_THRESHOLD
        freshness_label = "fresh" if is_fresh else "stale"
        logger.info(f"[GPS] Injecting external GPS: lat={lat}, lon={lon}, since_last={time_since_last:.1f}s ({freshness_label})")
        
        # 更新最後收到訊息的本地時間
        self._last_mqtt_gps_time = current_time
        
        # 標記使用外部 GPS
        if not self._using_external_gps:
            self._using_external_gps = True
            self._external_gps_timestamp = timestamp
        # 每次注入都更新來源 fresh/stale，避免圖標停在舊狀態
        self.gps_source_changed.emit(False, is_fresh)
        
        # 只有數據新鮮時才視為 fixed，過時的數據不視為有效定位
        if is_fresh:
            if not self._last_fix_status:
                self._last_fix_status = True
                self.gps_fixed_changed.emit(True)
                logger.info("[GPS] External GPS: Status changed to FIXED (fresh data)")
        else:
            # 數據過時，不應視為 fixed
            if self._last_fix_status:
                self._last_fix_status = False
                self.gps_fixed_changed.emit(False)
                logger.warning("[GPS] External GPS: Status changed to STALE (data too old)")
        
        # 不發射速度信號（使用者說速度不用）
        
        # 發射位置信號（只在變化時）
        if self._last_lat != lat or self._last_lon != lon:
            self._last_lat = lat
            self._last_lon = lon
            self.gps_position_changed.emit(lat, lon)

    def _update_status(self, is_fixed):
        # 若正在使用外部 MQTT GPS，且內部 GPS 有 fix，立即切換回內部
        if is_fixed and self._using_external_gps:
            self._using_external_gps = False
            self._external_gps_timestamp = None
            self.gps_source_changed.emit(True, True)  # True = internal, True = fresh
            logger.info("[GPS] Reverted to internal GPS")
        
        # 只在 fix 狀態改變時發射信號
        if is_fixed != self._last_fix_status:
            self._last_fix_status = is_fixed
            self.gps_fixed_changed.emit(is_fixed)
            status = "FIXED" if is_fixed else "SEARCHING"
            logger.info(f"[GPS] Status changed: {status}")

    def _update_device_status(self, found: bool):
        """更新裝置狀態"""
        if self._has_device != found:
            self._has_device = found
            self.gps_device_status_changed.emit(found)
            if found:
                logger.info("[GPS] Device found")
            else:
                logger.warning("[GPS] No device detected")
    
    def is_using_external_gps(self) -> bool:
        """回傳是否正在使用外部 GPS"""
        return self._using_external_gps


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
                ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
                # 在 macOS 上增加額外的裝置路徑模式
                if platform.system() == 'Darwin':
                    ports += glob.glob('/dev/cu.usb*') + glob.glob('/dev/cu.SLAB*')
                
                # 判斷是否要跳過掃描：開關關閉，或只有一個 port
                if not RADAR_ENABLED or len(ports) <= 1:
                    if not RADAR_ENABLED:
                        print("[Radar] RADAR_ENABLED=False，雷達功能已停用")
                    elif len(ports) <= 1:
                        print(f"[Radar] 只找到 {len(ports)} 個 port，跳過掃描")
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
            with _serial_lock:
                # 嘗試開啟 serial port
                with serial.Serial(port, self.baud_rate, timeout=0.5) as ser:
                    # 讀取幾行看看是不是雷達數據
                    for _ in range(3):  # 快速檢測
                        line = ser.readline()
                        try:
                            line_str = line.decode('ascii', errors='ignore').strip()
                            # 跳過 GPS NMEA 數據
                            if '$G' in line_str or '$GN' in line_str:
                                return False  # 這是 GPS port
                            # 檢查特徵：包含 'LR:' 和 'RR:' 和 'LF:' 和 'RF:'
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
            with _serial_lock:
                ser = serial.Serial(self._current_port, self.baud_rate, timeout=1.0)
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


