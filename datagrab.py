import time
import threading
import sys
import logging
import platform
import subprocess
import os
import json
import can
import cantools
import serial.tools.list_ports
from rich.console import Console
from rich.panel import Panel
from rich.align import Align

# 設定入口點環境變數 (供程式重啟時判斷)
os.environ['DASHBOARD_ENTRY'] = 'datagrab'

# PyQt6 Imports (只需要 Signal 相關)
from PyQt6.QtCore import QObject, pyqtSignal

# 引入儀表板的統一啟動流程
from main import run_dashboard

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('qtdashboard.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 降低第三方套件的日誌級別，避免網路錯誤訊息刷屏
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('requests').setLevel(logging.ERROR)
logging.getLogger('spotify_listener').setLevel(logging.INFO)

# --- 0. 信號類別 (關鍵修正：用於跨執行緒通訊) ---
class WorkerSignals(QObject):
    """
    定義所有從背景執行緒發送到 GUI 的信號。
    必須繼承自 QObject 才能使用 pyqtSignal。
    """
    update_rpm = pyqtSignal(float)   # 發送轉速 (float)
    update_speed = pyqtSignal(float) # 發送車速 (float)
    update_temp = pyqtSignal(float)  # 發送水溫百分比 (float)
    update_fuel = pyqtSignal(float)  # 發送油量百分比 (float)
    update_gear = pyqtSignal(str)    # 發送檔位 (str)
    update_turn_signal = pyqtSignal(str)  # 發送方向燈狀態 (str: "left_on", "left_off", "right_on", "right_off", "both_on", "both_off", "off")
    update_door_status = pyqtSignal(str, bool)  # 發送門狀態 (door: str, is_closed: bool)
    update_cruise = pyqtSignal(bool, bool)  # 發送巡航狀態 (cruise_switch: bool, cruise_engaged: bool)
    update_turbo = pyqtSignal(float)  # 發送渦輪增壓 (bar)
    update_battery = pyqtSignal(float)  # 發送電瓶電壓 (V)
    # update_nav_icon = pyqtSignal(str) # 預留給導航圖片

# --- 全局變數 ---
current_mode = "HYBRID" 
data_store = {
    "CAN": {"rpm": 0, "speed": 0, "fuel": 0, "hz": 0, "last_update": 0},
    "OBD": {"rpm": 0, "speed": 0, "speed_smoothed": 0, "temp": 0, "turbo": 0, "battery": 0, "hz": 0, "last_update": 0}
}
stop_threads = False
console = Console()
send_lock = threading.Lock() # 保護寫入操作
gps_speed_mode=False  # True: GPS 顯示優先 (OBD+GPS 混合)，False: OBD 顯示
speed_sync_mode = "calibrated"  # calibrated | fixed | gps

# 校正會話控制
CALIBRATION_MARKER = "/tmp/.dashboard_speed_calibrate"
calibration_enabled = False  # 僅手動啟用時才允許自動校正
# 速度校正設定
SPEED_CALIBRATION_DIR = os.path.join(os.path.expanduser("~"), ".config", "qtdashboard")
SPEED_CALIBRATION_FILE = os.path.join(SPEED_CALIBRATION_DIR, "speed_calibration.json")
SPEED_CORRECTION_DEFAULT = 1.01
SPEED_CORRECTION_MIN = 0.7
SPEED_CORRECTION_MAX = 1.3
_speed_correction_lock = threading.Lock()
_speed_correction_value = SPEED_CORRECTION_DEFAULT

def _load_speed_correction(default=SPEED_CORRECTION_DEFAULT):
    """讀取速度校正係數"""
    global _speed_correction_value
    value = default
    try:
        with open(SPEED_CALIBRATION_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
            candidate = float(payload.get("speed_correction", value))
            candidate = max(SPEED_CORRECTION_MIN, min(SPEED_CORRECTION_MAX, candidate))
            value = candidate
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"讀取速度校正檔失敗，使用預設值: {e}")
    _speed_correction_value = value
    return value

def get_speed_correction():
    """取得目前速度校正係數"""
    with _speed_correction_lock:
        return _speed_correction_value

def set_speed_correction(new_value, persist=False):
    """更新速度校正係數，必要時寫回檔案"""
    global _speed_correction_value
    clamped = max(SPEED_CORRECTION_MIN, min(SPEED_CORRECTION_MAX, float(new_value)))
    with _speed_correction_lock:
        _speed_correction_value = clamped
    if persist:
        persist_speed_correction()
    return clamped

def persist_speed_correction():
    """將目前速度校正係數寫入磁碟"""
    value = get_speed_correction()
    try:
        os.makedirs(SPEED_CALIBRATION_DIR, exist_ok=True)
        with open(SPEED_CALIBRATION_FILE, "w", encoding="utf-8") as f:
            json.dump({"speed_correction": value, "updated_at": time.time()}, f)
    except Exception as e:
        logger.warning(f"寫入速度校正檔失敗: {e}")

# 初始化校正係數
_load_speed_correction()

# 讀取校正啟用標記（單次會話）
if os.environ.get("SPEED_CALIBRATE_ONCE") == "1" or os.path.exists(CALIBRATION_MARKER):
    calibration_enabled = True
    try:
        if os.path.exists(CALIBRATION_MARKER):
            os.remove(CALIBRATION_MARKER)  # 單次使用
    except Exception:
        pass
else:
    calibration_enabled = False

def is_speed_calibration_enabled():
    return calibration_enabled

def set_speed_calibration_enabled(enabled: bool):
    global calibration_enabled
    calibration_enabled = bool(enabled)
    logger.info(f"速度校正模式 {'啟用' if calibration_enabled else '停用'}")

def set_speed_sync_mode(mode: str):
    """設定速度同步模式，並同步 gps_speed_mode 旗標"""
    global speed_sync_mode, gps_speed_mode
    allowed = {"calibrated", "fixed", "gps"}
    if mode not in allowed:
        logger.warning(f"無效速度模式: {mode}")
        return speed_sync_mode
    speed_sync_mode = mode
    gps_speed_mode = (mode == "gps")
    logger.info(f"速度模式切換為 {mode}，gps_speed_mode={gps_speed_mode}")
    return speed_sync_mode
# --- 1. 硬體連接 ---

def detect_socketcan_interfaces():
    """
    偵測可用的 SocketCAN 介面 (僅 Linux)
    返回: list of (interface_name, status) 或空列表
    """
    if platform.system() != 'Linux':
        return []
    
    interfaces = []
    try:
        # 使用 ip link 列出所有 CAN 介面
        result = subprocess.run(
            ['ip', '-details', 'link', 'show', 'type', 'can'],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            current_iface = None
            
            for line in lines:
                # 解析介面名稱 (例如: "3: can0: <NOARP,UP,LOWER_UP>...")
                if ': ' in line and not line.startswith(' '):
                    parts = line.split(': ')
                    if len(parts) >= 2:
                        current_iface = parts[1].split('@')[0]  # 處理 can0@... 格式
                        # 檢查狀態
                        is_up = 'UP' in line and 'LOWER_UP' in line
                        status = "UP" if is_up else "DOWN"
                        interfaces.append((current_iface, status))
            
            logger.info(f"偵測到 SocketCAN 介面: {interfaces}")
        
    except FileNotFoundError:
        logger.debug("ip 命令不存在，跳過 SocketCAN 偵測")
    except subprocess.TimeoutExpired:
        logger.warning("SocketCAN 偵測超時")
    except Exception as e:
        logger.debug(f"SocketCAN 偵測錯誤: {e}")
    
    return interfaces


def setup_socketcan_interface(interface='can0', bitrate=500000):
    """
    設定 SocketCAN 介面 (需要 root 權限)
    返回: True 如果成功，False 如果失敗
    """
    try:
        # 先嘗試關閉介面（如果已經開啟）
        subprocess.run(['sudo', 'ip', 'link', 'set', interface, 'down'],
                      capture_output=True, timeout=5)
        
        # 設定 bitrate
        result = subprocess.run(
            ['sudo', 'ip', 'link', 'set', interface, 'type', 'can', 'bitrate', str(bitrate)],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode != 0:
            logger.error(f"設定 {interface} bitrate 失敗: {result.stderr}")
            return False
        
        # 啟動介面
        result = subprocess.run(
            ['sudo', 'ip', 'link', 'set', interface, 'up'],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode != 0:
            logger.error(f"啟動 {interface} 失敗: {result.stderr}")
            return False
        
        logger.info(f"SocketCAN 介面 {interface} 已設定 (bitrate={bitrate})")
        return True
        
    except FileNotFoundError:
        logger.error("需要 sudo 和 ip 命令來設定 SocketCAN")
        return False
    except subprocess.TimeoutExpired:
        logger.error("設定 SocketCAN 超時")
        return False
    except Exception as e:
        logger.error(f"設定 SocketCAN 錯誤: {e}")
        return False


def init_can_bus(bitrate=500000):
    """
    初始化 CAN Bus 連線
    優先順序：
    1. Linux: SocketCAN (如果有可用介面)
    2. 所有平台: SLCAN (USB CAN adapter)
    
    返回: (bus, interface_type) 或 (None, None)
    """
    bus = None
    interface_type = None
    
    # === CAN 過濾器：只接收我們需要的 ID ===
    # 這可以大幅減少 CPU 負擔，特別是在高流量 CAN Bus 上
    can_filters = [
        {"can_id": 0x7E8, "can_mask": 0x7FF},  # OBD ECU 回應
        {"can_id": 0x7E9, "can_mask": 0x7FF},  # OBD TCM 回應
        {"can_id": 0x340, "can_mask": 0x7FF},  # ENGINE_RPM1 (檔位)
        {"can_id": 0x335, "can_mask": 0x7FF},  # THROTTLE_STATUS (油量、巡航)
        {"can_id": 0x38A, "can_mask": 0x7FF},  # SPEED_FL (車速)
        {"can_id": 0x410, "can_mask": 0x7FF},  # CONSOLE_STATUS (方向燈撥桿)
        {"can_id": 0x420, "can_mask": 0x7FF},  # BODY_ECU_STATUS (方向燈、門狀態)
    ]
    
    # === 1. 嘗試 SocketCAN (僅 Linux) ===
    if platform.system() == 'Linux':
        console.print("[cyan]偵測 SocketCAN 介面...[/cyan]")
        socketcan_interfaces = detect_socketcan_interfaces()
        
        if socketcan_interfaces:
            for iface, status in socketcan_interfaces:
                console.print(f"  發現: [green]{iface}[/green] ({status})")
                
                # 如果介面是 DOWN，嘗試設定並啟動
                if status == "DOWN":
                    console.print(f"  [yellow]介面 {iface} 未啟動，嘗試設定...[/yellow]")
                    if not setup_socketcan_interface(iface, bitrate):
                        continue
                
                # 嘗試連接
                try:
                    bus = can.interface.Bus(
                        interface='socketcan',
                        channel=iface,
                        bitrate=bitrate,
                        receive_own_messages=False,
                        can_filters=can_filters
                    )
                    interface_type = f"SocketCAN ({iface})"
                    console.print(f"[bold green]✓ SocketCAN 連線成功: {iface}[/bold green]")
                    logger.info(f"CAN Bus 已連接 (SocketCAN): {iface}, 過濾器: {len(can_filters)} 個 ID")
                    return bus, interface_type
                    
                except Exception as e:
                    logger.warning(f"SocketCAN {iface} 連線失敗: {e}")
                    continue
        else:
            console.print("  [yellow]未發現 SocketCAN 介面[/yellow]")
    
    # === 2. Fallback 到 SLCAN ===
    console.print("[cyan]嘗試 SLCAN 模式...[/cyan]")
    
    port = select_serial_port()
    if not port:
        console.print("[red]未找到可用的 CAN 裝置[/red]")
        return None, None
    
    try:
        # 注意：SLCAN 不支援硬體過濾器，過濾會在軟體層進行
        # 但設定 can_filters 仍有助於 python-can 內部優化
        bus = can.interface.Bus(
            interface='slcan',
            channel=port,
            bitrate=bitrate,
            timeout=0.01,
            receive_own_messages=False,
            can_filters=can_filters
        )
        interface_type = f"SLCAN ({port})"
        console.print(f"[bold green]✓ SLCAN 連線成功: {port}[/bold green]")
        logger.info(f"CAN Bus 已連接 (SLCAN): {port}, 過濾器: {len(can_filters)} 個 ID")
        return bus, interface_type
        
    except Exception as e:
        console.print(f"[red]SLCAN 連線失敗: {e}[/red]")
        logger.error(f"SLCAN 初始化失敗: {e}", exc_info=True)
        return None, None


def select_serial_port():
    import glob
    
    # 自動偵測的 serial ports
    ports = list(serial.tools.list_ports.comports())
    
    # 手動搜尋虛擬 serial ports (macOS/Linux)
    virtual_ports = []
    for pattern in ['/dev/ttys*', '/dev/pts/*', '/dev/ttyUSB*', '/dev/ttyACM*']:
        virtual_ports.extend(glob.glob(pattern))
    
    # 合併所有可用的 ports
    all_ports = []
    canable_port = None  # 記錄 CANable 裝置
    
    for p in ports:
        all_ports.append((p.device, p.description))
        # 檢查是否為 CANable 裝置 (不分大小寫)
        if 'canable' in p.description.lower():
            canable_port = p.device
            logger.info(f"偵測到 CANable 裝置: {p.device} - {p.description}")
    
    for vp in virtual_ports:
        if not any(vp == p[0] for p in all_ports):  # 避免重複
            all_ports.append((vp, "Virtual Serial Port"))
    
    if not all_ports:
        console.print("[red]未找到任何 Serial 裝置！[/red]")
        console.print("[yellow]提示: 如要測試，請先建立虛擬 port 對：[/yellow]")
        console.print("  socat -d -d pty,raw,echo=0 pty,raw,echo=0")
        return None
    
    console.print("[yellow]可用的 Serial 裝置：[/yellow]")
    for i, (device, desc) in enumerate(all_ports):
        # 標注 CANable 裝置
        if 'canable' in desc.lower():
            console.print(f"[{i}] {device} - {desc} [bold green](CANable)[/bold green]")
        else:
            console.print(f"[{i}] {device} - {desc}")
    
    # 優先自動選擇 CANable 裝置
    if canable_port:
        console.print(f"[green]自動選擇 CANable 裝置: {canable_port}[/green]")
        return canable_port
    
    # 提供手動輸入選項
    console.print("[cyan]或直接輸入 port 路徑 (例如: /dev/ttys014)[/cyan]")
    
    if len(all_ports) == 1:
        console.print(f"[green]自動選擇唯一裝置: {all_ports[0][0]}[/green]")
        return all_ports[0][0]
    
    choice = console.input("請輸入裝置編號或路徑 [0]: ").strip()
    
    # 檢查是否為直接輸入路徑
    if choice.startswith('/dev/'):
        logger.info(f"使用手動輸入的路徑: {choice}")
        return choice
    
    # 否則當作索引處理
    try:
        idx = int(choice) if choice else 0
        return all_ports[idx][0]
    except (ValueError, IndexError):
        logger.warning(f"無效的選擇: {choice}，使用預設裝置")
        return all_ports[0][0]

# --- 2. 核心邏輯 (監聽與查詢) ---
def unified_receiver(bus, db, signals):
    """
    統一處理所有接收到的 CAN 訊息 (包含 DBC 解碼和 OBD 解析)
    關鍵修改：使用 signals.emit() 取代 dashboard.set_xxx()
    
    RPI4 優化：
    - 減少 recv timeout 以降低延遲
    - 狀態變化偵測：只在狀態真正改變時才 emit signal
    - 減少不必要的 logger 呼叫
    """
    global data_store
    last_can_hz_calc = time.time()
    can_count = 0
    error_count = 0
    max_consecutive_errors = 100
    
    # RPM 平滑參數
    current_rpm_smoothed = 0.0
    rpm_alpha = 0.25  # 平滑係數 (0.0~1.0)，越小越平滑但反應越慢
    
    # 速度平滑參數 (OBD)
    current_speed_smoothed = 0.0
    speed_alpha = 0.3  # 速度平滑係數
    last_obd_speed_int = None  # OBD 速度緩存
    
    # 油量平滑演算法參數
    # 使用移動平均 + 變化率限制，避免浮動
    fuel_samples = []  # 油量樣本緩衝區
    fuel_sample_size = 10  # 保留最近 10 個樣本
    fuel_smoothed = None  # 平滑後的油量值
    fuel_last_update_time = 0  # 上次更新時間
    fuel_min_update_interval = 180.0  # 正常情況下每 3 分鐘更新一次 UI
    fuel_change_threshold = 0.5  # 油量變化閾值 (0.5%)
    fuel_rapid_rise_threshold = 3.0  # 快速上升閾值 (3%)，檢測加油情況
    
    # 檔位切換狀態追蹤
    last_gear_str = None
    last_gear_change_time = 0
    
    # === RPI4 優化：狀態緩存，只在變化時 emit ===
    last_turn_signal_state = None  # 方向燈狀態緩存
    last_door_states = {  # 門狀態緩存
        "FL": None, "FR": None, "RL": None, "RR": None, "BK": None
    }
    last_cruise_state = (None, None)  # 巡航狀態緩存
    last_fuel_int = None  # 油量緩存（整數化，避免浮點微小變化觸發更新）
    last_speed_int = None  # CAN 速度緩存（僅供記錄，不更新 UI）
    
    logger.info("CAN 訊息接收執行緒已啟動")
    
    while not stop_threads:
        try:
            # RPI4 優化：減少 timeout 從 0.1 到 0.01，降低延遲
            # 在 SLCAN 上，較短的 timeout 能更快響應新訊息
            msg = bus.recv(timeout=0.01) 
            
            if msg is None: 
                continue # 超時沒數據，繼續下一圈
            
            # 重置錯誤計數（收到有效訊息）
            error_count = 0

            # 1. 處理 OBD 回應 (ID 0x7E8 ECU / 0x7E9 TCM)
            if msg.arbitration_id in [0x7E8, 0x7E9]:
                try:
                    if len(msg.data) < 3:
                        continue
                    
                    # PID 0C (RPM)
                    if msg.data[2] == 0x0C:
                        if len(msg.data) < 5:
                            continue
                        raw_rpm = (msg.data[3] * 256 + msg.data[4]) / 4
                        
                        # 平滑處理 (EMA - Exponential Moving Average)
                        if current_rpm_smoothed == 0:
                            current_rpm_smoothed = raw_rpm
                        else:
                            current_rpm_smoothed = (current_rpm_smoothed * (1 - rpm_alpha)) + (raw_rpm * rpm_alpha)
                        
                        # 記錄來源
                        source = "ECU" if msg.arbitration_id == 0x7E8 else "TCM"
                        data_store["OBD"]["rpm"] = raw_rpm
                        data_store["OBD"]["last_update"] = time.time()
                        
                        # [修改] 放棄 CAN RPM，直接使用 OBD 數據更新介面
                        # 雖然頻率較低，但數值是標準且準確的
                        signals.update_rpm.emit(current_rpm_smoothed / 1000.0)
                    
                    # PID 0D (Vehicle Speed) - 車速
                    elif msg.data[2] == 0x0D:
                        if len(msg.data) < 4:
                            continue
                        raw_speed = msg.data[3]  # 單位: km/h
                        
                        # 平滑處理
                        if current_speed_smoothed == 0:
                            current_speed_smoothed = raw_speed
                        else:
                            current_speed_smoothed = (current_speed_smoothed * (1 - speed_alpha)) + (raw_speed * speed_alpha)
                        
                        data_store["OBD"]["speed"] = raw_speed
                        data_store["OBD"]["speed_smoothed"] = current_speed_smoothed
                        data_store["OBD"]["last_update"] = time.time()
                        
                        
                        # 套用校正係數後更新 UI（依據速度模式）
                        mode = speed_sync_mode
                        if mode == "fixed":
                            speed_correction = 1.05
                            corrected_speed = current_speed_smoothed * speed_correction + 0.8
                        else:
                            speed_correction = get_speed_correction()
                            corrected_speed = current_speed_smoothed * speed_correction
                        speed_int = int(corrected_speed)
                        if last_obd_speed_int is None or abs(speed_int - last_obd_speed_int) >= 1:
                            signals.update_speed.emit(corrected_speed)
                            last_obd_speed_int = speed_int
                    
                    # PID 05 (Temp) - 水箱溫度 (通常只在 ECU 0x7E8)
                    elif msg.data[2] == 0x05 and msg.arbitration_id == 0x7E8:
                        if len(msg.data) < 4:
                            logger.warning("水溫資料長度不足")
                            continue
                        temp = msg.data[3] - 40
                        data_store["OBD"]["temp"] = temp
                        logger.debug(f"水箱溫度: {temp}°C")
                        
                        # 更新前端水溫顯示
                        # 40°C -> 0%, 80°C -> 50%, 120°C -> 100%
                        temp_normalized = ((temp - 40) / 80.0) * 100
                        temp_normalized = max(0, min(100, temp_normalized))
                        signals.update_temp.emit(temp_normalized)  # ✅ 安全發送
                    
                    # PID 0B (Intake Manifold Pressure) - 進氣歧管壓力 (渦輪增壓)
                    elif msg.data[2] == 0x0B and msg.arbitration_id == 0x7E8:
                        if len(msg.data) < 4:
                            logger.warning("進氣歧管壓力資料長度不足")
                            continue
                        # OBD 返回的是絕對壓力 (kPa)，0-255 kPa
                        # 需要轉換為相對壓力 (相對於大氣壓 ~101 kPa)
                        abs_pressure_kpa = msg.data[3]
                        # 轉換為相對壓力 (bar): (絕對壓力 - 大氣壓) / 100
                        # 負值 = 真空/負壓，正值 = 增壓
                        turbo_bar = (abs_pressure_kpa - 101) / 100.0
                        data_store["OBD"]["turbo"] = turbo_bar
                        logger.debug(f"渦輪增壓: {turbo_bar:.2f} bar (絕對: {abs_pressure_kpa} kPa)")
                        
                        # 更新前端渦輪增壓顯示
                        signals.update_turbo.emit(turbo_bar)
                    
                    # PID 42 (Control Module Voltage) - 控制模組電壓 (電瓶電壓)
                    elif msg.data[2] == 0x42 and msg.arbitration_id == 0x7E8:
                        if len(msg.data) < 5:
                            logger.warning("電瓶電壓資料長度不足")
                            continue
                        # 公式: (A*256 + B) / 1000 = 電壓 (V)
                        voltage = (msg.data[3] * 256 + msg.data[4]) / 1000.0
                        data_store["OBD"]["battery"] = voltage
                        logger.debug(f"電瓶電壓: {voltage:.1f} V")
                        
                        # 更新前端電瓶電壓顯示
                        signals.update_battery.emit(voltage)
                        
                except (IndexError, KeyError) as e:
                    logger.error(f"解析 OBD 訊息錯誤: {e}, data: {msg.data.hex()}")
                except Exception as e:
                    logger.error(f"處理 OBD 訊息未預期錯誤: {e}")

            # 2. 處理 ENGINE_RPM1 (ID 0x340 / 832)
            elif msg.arbitration_id == 0x340:
                try:
                    # decoded = db.decode_message(msg.arbitration_id, msg.data)
                    # 改為純手動解析，因為 DBC Multiplexing 對未定義的 ID (如 8) 會報錯導致中斷
                    
                    # 取得檔位模式 (Byte 0)
                    # DBC: TRANS_MODE : 7|5@1+ (Byte 0 bits 0-4)
                    trans_mode = msg.data[0] & 0x1F
                    
                    # --- 僅保留檔位解析 (RPM 改用 OBD) ---
                    gear_str = "P" # 預設
                    
                    if trans_mode == 0x00: # P/N 檔
                        # 區分 P 和 N (根據 Byte 1)
                        # P: 00 80 ... (Byte 1 & 0x0F = 0)
                        # N: 00 84 ... (Byte 1 & 0x0F = 4)
                        if (msg.data[1] & 0x0F) == 4:
                            gear_str = "N"
                        else:
                            gear_str = "P"
                        
                    elif trans_mode == 0x07: # R 檔
                        gear_str = "R"
                    
                    elif trans_mode >= 0x01 and trans_mode <= 0x05: # D 檔 1-5 檔
                        # trans_mode 0x01 = 1檔, 0x02 = 2檔, ..., 0x05 = 5檔
                        gear_str = str(trans_mode)
                    
                    elif trans_mode >= 0x06:
                        # 6 或以上的值，保持上一次的檔位顯示（不更新）
                        gear_str = last_gear_str if last_gear_str else "5"
                            
                    else:
                        # 其他檔位 (S/L 等)
                        gear_str = str(trans_mode)
                    
                    # 記錄當前檔位供下次使用
                    last_gear_str = gear_str
                    
                    # 更新前端檔位顯示
                    signals.update_gear.emit(gear_str)
                    
                    # [已移除] 複雜的 CAN RPM 解析邏輯
                    # 由於 Luxgen M7 的 RPM 訊號在 D/R 檔位使用了特殊的 Base+Delta 編碼，
                    # 且實測發現極不穩定，故決定回退到使用標準 OBD-II PID 0x0C 讀取轉速。
                    
                    # 計算 CAN Hz
                    can_count += 1
                    now = time.time()
                    if now - last_can_hz_calc >= 1.0:
                        data_store["CAN"]["hz"] = can_count
                        logger.debug(f"CAN 更新率: {can_count} Hz")
                        can_count = 0
                        last_can_hz_calc = now
                        
                except cantools.database.errors.DecodeError as e:
                    logger.error(f"DBC 解碼錯誤 (ENGINE_RPM1): {e}")
                except Exception as e:
                    logger.error(f"處理轉速訊息錯誤: {e}")
            
            # 3. 處理 THROTTLE_STATUS (ID 0x335 / 821) - 油量 + 巡航
            elif msg.arbitration_id == 0x335:
                try:
                    decoded = db.decode_message(msg.arbitration_id, msg.data)
                    
                    # === 油量 ===
                    # FUEL 縮放 (0.3984, 0)，範圍 0-100%
                    fuel_value = decoded['FUEL']
                    if hasattr(fuel_value, 'value'):
                        fuel_raw = float(fuel_value.value)
                    else:
                        fuel_raw = float(fuel_value)

                    data_store["CAN"]["fuel"] = fuel_raw
                    
                    # === 油量平滑演算法 ===
                    # 1. 加入樣本緩衝區
                    fuel_samples.append(fuel_raw)
                    if len(fuel_samples) > fuel_sample_size:
                        fuel_samples.pop(0)
                    
                    # 2. 計算移動平均（去除最高和最低值後的平均）
                    if len(fuel_samples) >= 3:
                        sorted_samples = sorted(fuel_samples)
                        # 去除最高和最低的異常值
                        trimmed = sorted_samples[1:-1] if len(sorted_samples) > 4 else sorted_samples
                        fuel_avg = sum(trimmed) / len(trimmed)
                    else:
                        fuel_avg = fuel_raw
                    
                    # 3. 初始化或更新平滑值
                    current_time = time.time()
                    if fuel_smoothed is None:
                        fuel_smoothed = fuel_avg
                        last_fuel_int = int(fuel_smoothed)
                        signals.update_fuel.emit(fuel_smoothed)
                        fuel_last_update_time = current_time
                    else:
                        # 4. 檢測快速上升（加油情況）
                        fuel_diff = fuel_avg - fuel_smoothed
                        is_rapid_rise = fuel_diff >= fuel_rapid_rise_threshold
                        
                        # 5. 變化率限制：每次最多變化 0.5%（除非是快速上升）
                        if is_rapid_rise:
                            # 快速上升時直接更新到新值
                            fuel_smoothed = fuel_avg
                        elif abs(fuel_diff) > fuel_change_threshold:
                            # 限制變化幅度
                            fuel_smoothed += fuel_change_threshold if fuel_diff > 0 else -fuel_change_threshold
                        else:
                            fuel_smoothed = fuel_avg
                        
                        # 6. 更新 UI 的條件：
                        #    - 快速上升（加油）：立即更新
                        #    - 正常情況：每 3 分鐘更新一次
                        fuel_int = int(fuel_smoothed)
                        time_since_update = current_time - fuel_last_update_time
                        
                        should_update = False
                        if is_rapid_rise:
                            # 快速上升（加油）時立即更新
                            should_update = True
                            logger.info(f"偵測到油量快速上升 (加油): {last_fuel_int}% -> {fuel_int}%")
                        elif time_since_update >= fuel_min_update_interval:
                            # 正常情況下每 3 分鐘更新一次
                            should_update = True
                        
                        if should_update:
                            signals.update_fuel.emit(fuel_smoothed)
                            last_fuel_int = fuel_int
                            fuel_last_update_time = current_time
                    
                    # === 巡航狀態 ===
                    # CRUSE_ONOFF: bit 2 (開關)
                    # CRUSE_ENABLED: bit 4 (作動中)
                    cruise_switch_value = decoded.get('CRUSE_ONOFF', 0)
                    cruise_enabled_value = decoded.get('CRUSE_ENABLED', 0)
                    
                    # 轉換為 bool
                    if hasattr(cruise_switch_value, 'value'):
                        cruise_switch = bool(int(cruise_switch_value.value))
                    else:
                        cruise_switch = bool(int(cruise_switch_value))
                    
                    if hasattr(cruise_enabled_value, 'value'):
                        cruise_enabled = bool(int(cruise_enabled_value.value))
                    else:
                        cruise_enabled = bool(int(cruise_enabled_value))
                    
                    # RPI4 優化：只在巡航狀態真正改變時才 emit signal
                    cruise_state = (cruise_switch, cruise_enabled)
                    if cruise_state != last_cruise_state:
                        signals.update_cruise.emit(cruise_switch, cruise_enabled)
                        last_cruise_state = cruise_state
                            
                except cantools.database.errors.DecodeError as e:
                    logger.error(f"DBC 解碼錯誤 (THROTTLE_STATUS): {e}")
                except Exception as e:
                    logger.error(f"處理油量/巡航訊息錯誤: {e}")
            
            # 4. 處理 SPEED_FL 速度 (ID 0x38A / 906)
            # 注意：速度改用 OBD PID 0x0D 更新 UI，CAN 速度僅供記錄參考
            elif msg.arbitration_id == 0x38A:
                try:
                    decoded = db.decode_message(msg.arbitration_id, msg.data)
                    # SPEED_FL 縮放 (1, 0)，範圍 0-255 km/h
                    speed_value = decoded['SPEED_FL']
                    if hasattr(speed_value, 'value'):
                        speed = float(speed_value.value)
                    else:
                        speed = float(speed_value)

                    # 只記錄到 data_store，不更新 UI（改由 OBD PID 0x0D 更新）
                    data_store["CAN"]["speed"] = speed
                    last_speed_int = int(speed)  # 更新緩存供參考
                            
                except cantools.database.errors.DecodeError as e:
                    logger.error(f"DBC 解碼錯誤 (SPEED_FL): {e}")
                except Exception as e:
                    logger.error(f"處理速度訊息錯誤: {e}")

            # 5. 處理方向燈和門狀態 BODY_ECU_STATUS (ID 0x420 / 1056)
            elif msg.arbitration_id == 0x420:
                try:
                    decoded = db.decode_message(msg.arbitration_id, msg.data)
                    
                    # === 方向燈狀態 ===
                    left_signal = decoded.get('LEFT_SIGNAL_STATUS', 0)
                    right_signal = decoded.get('RIGHT_SIGNAL_STATUS', 0)
                    
                    # 轉換為 int (如果是 NamedSignalValue)
                    if hasattr(left_signal, 'value'):
                        left_signal = int(left_signal.value)
                    else:
                        left_signal = int(left_signal)
                    
                    if hasattr(right_signal, 'value'):
                        right_signal = int(right_signal.value)
                    else:
                        right_signal = int(right_signal)
                    
                    # 判斷方向燈狀態
                    if left_signal == 1 and right_signal == 1:
                        turn_state = "both_on"
                    elif left_signal == 1 and right_signal == 0:
                        turn_state = "left_on"
                    elif left_signal == 0 and right_signal == 1:
                        turn_state = "right_on"
                    else:
                        turn_state = "off"
                    
                    # RPI4 優化：只在狀態真正改變時才 emit signal
                    if turn_state != last_turn_signal_state:
                        signals.update_turn_signal.emit(turn_state)
                        last_turn_signal_state = turn_state
                    
                    # === 門狀態 ===
                    # 根據 DBC: 0=關閉, 1=打開
                    door_fl = decoded.get('DOOR_FL_STATUS', 0)
                    door_fr = decoded.get('DOOR_FR_STATUS', 0)
                    door_rl = decoded.get('DOOR_RL_STATUS', 0)
                    door_rr = decoded.get('DOOR_RR_STATUS', 0)
                    door_bk = decoded.get('DOOR_BACK_DOOR_STATUS', 0)
                    
                    # 轉換為 int
                    if hasattr(door_fl, 'value'):
                        door_fl = int(door_fl.value)
                    else:
                        door_fl = int(door_fl)
                    
                    if hasattr(door_fr, 'value'):
                        door_fr = int(door_fr.value)
                    else:
                        door_fr = int(door_fr)
                    
                    if hasattr(door_rl, 'value'):
                        door_rl = int(door_rl.value)
                    else:
                        door_rl = int(door_rl)
                    
                    if hasattr(door_rr, 'value'):
                        door_rr = int(door_rr.value)
                    else:
                        door_rr = int(door_rr)
                    
                    if hasattr(door_bk, 'value'):
                        door_bk = int(door_bk.value)
                    else:
                        door_bk = int(door_bk)
                    
                    # RPI4 優化：只在門狀態真正改變時才 emit signal
                    door_fl_closed = (door_fl == 0)
                    door_fr_closed = (door_fr == 0)
                    door_rl_closed = (door_rl == 0)
                    door_rr_closed = (door_rr == 0)
                    door_bk_closed = (door_bk == 0)
                    
                    if last_door_states["FL"] != door_fl_closed:
                        signals.update_door_status.emit("FL", door_fl_closed)
                        last_door_states["FL"] = door_fl_closed
                    if last_door_states["FR"] != door_fr_closed:
                        signals.update_door_status.emit("FR", door_fr_closed)
                        last_door_states["FR"] = door_fr_closed
                    if last_door_states["RL"] != door_rl_closed:
                        signals.update_door_status.emit("RL", door_rl_closed)
                        last_door_states["RL"] = door_rl_closed
                    if last_door_states["RR"] != door_rr_closed:
                        signals.update_door_status.emit("RR", door_rr_closed)
                        last_door_states["RR"] = door_rr_closed
                    if last_door_states["BK"] != door_bk_closed:
                        signals.update_door_status.emit("BK", door_bk_closed)
                        last_door_states["BK"] = door_bk_closed
                    
                except cantools.database.errors.DecodeError as e:
                    logger.error(f"DBC 解碼錯誤 (BODY_ECU_STATUS): {e}")
                except Exception as e:
                    logger.error(f"處理車身狀態訊息錯誤: {e}")
            
            # 6. 偵測潛在的 RPM 訊號 (ID 0x316 / 790 ENGINE_DATA)
            # elif msg.arbitration_id == 0x316:
            #     # 當主要 RPM (ID 832) 失效時，記錄此 ID 的數據以供分析
            #     if time.time() - data_store["CAN"].get("last_update", 0) > 1.0:
            #         if error_count % 20 == 0: # 降低頻率
            #             logger.info(f"尋找 RPM 候選 - ID 790 Raw: {msg.data.hex()}")
                
        except ValueError as e:
            # 捕捉 fromhex error，忽略這條損壞的訊息
            error_count += 1
            if error_count % 10 == 0:  # 每 10 個錯誤記錄一次
                logger.warning(f"訊框格式錯誤，已跳過 {error_count} 個錯誤訊框")
                
        except can.CanError as e:
            error_count += 1
            logger.error(f"CAN Bus 錯誤: {e}")
            if error_count >= max_consecutive_errors:
                logger.critical(f"連續錯誤達 {max_consecutive_errors} 次，接收執行緒即將停止")
                break
            time.sleep(0.1)  # 錯誤後稍微延遲
            
        except Exception as e:
            error_count += 1
            logger.error(f"接收執行緒未預期錯誤: {type(e).__name__}: {e}", exc_info=True)
            if error_count >= max_consecutive_errors:
                logger.critical(f"連續錯誤達 {max_consecutive_errors} 次，接收執行緒即將停止")
                break
    
    logger.info("CAN 訊息接收執行緒已停止")

def obd_query(bus, signals):
    """主動查詢 OBD-II"""
    global data_store
    logger.info("OBD-II 查詢執行緒已啟動")
    
    while not stop_threads:
        if current_mode == "CAN_ONLY":
            time.sleep(1)
            continue

        try:
            # 查詢 RPM (PID 0x0C)
            msg_rpm = can.Message(
                arbitration_id=0x7DF, 
                data=[0x02, 0x01, 0x0C, 0, 0, 0, 0, 0], 
                is_extended_id=False
            )
            with send_lock:
                bus.send(msg_rpm)
            time.sleep(0.08)
            
            # 查詢 車速 (PID 0x0D)
            msg_speed = can.Message(
                arbitration_id=0x7DF, 
                data=[0x02, 0x01, 0x0D, 0, 0, 0, 0, 0], 
                is_extended_id=False
            )
            with send_lock:
                bus.send(msg_speed)
            time.sleep(0.08)

            # 查詢 水溫 (PID 0x05)
            msg_temp = can.Message(
                arbitration_id=0x7DF, 
                data=[0x02, 0x01, 0x05, 0, 0, 0, 0, 0], 
                is_extended_id=False
            )
            with send_lock:
                bus.send(msg_temp)
            time.sleep(0.05)
            
            # 查詢 進氣歧管壓力/渦輪增壓 (PID 0x0B)
            msg_turbo = can.Message(
                arbitration_id=0x7DF, 
                data=[0x02, 0x01, 0x0B, 0, 0, 0, 0, 0], 
                is_extended_id=False
            )
            with send_lock:
                bus.send(msg_turbo)
            time.sleep(0.05)
            
            # 查詢 電瓶電壓 (PID 0x42)
            msg_battery = can.Message(
                arbitration_id=0x7DF, 
                data=[0x02, 0x01, 0x42, 0, 0, 0, 0, 0], 
                is_extended_id=False
            )
            with send_lock:
                bus.send(msg_battery)
            
            time.sleep(0.05)  # 查詢間隔
            
        except can.CanError:
            time.sleep(1)
        except Exception as e:
            logger.error(f"OBD 查詢錯誤: {e}")
            time.sleep(1)
    
    logger.info("OBD-II 查詢執行緒已停止")

# --- 3. 主程式 ---
def main():
    global current_mode, stop_threads
    
    bus = None
    db = None
    interface_type = None
    
    try:
        logger.info("=" * 50)
        logger.info("Luxgen M7 儀表板系統啟動")
        logger.info(f"平台: {platform.system()}")
        logger.info("=" * 50)
        
        # 1. 初始化 CAN Bus（自動選擇 SocketCAN 或 SLCAN）
        console.print(Panel.fit(
            "[bold cyan]Luxgen M7 儀表板系統[/bold cyan]\n"
            f"平台: {platform.system()}",
            title="啟動中"
        ))
        
        bus, interface_type = init_can_bus(bitrate=500000)
        
        if bus is None:
            logger.error("無法初始化 CAN Bus，程式退出")
            console.print("[red]無法連接 CAN Bus！請檢查硬體連線。[/red]")
            return
        
        logger.info(f"CAN Bus 連線模式: {interface_type}")
        
        # 2. 載入 DBC 檔案
        try:
            logger.info("正在載入 DBC 檔案...")
            db = cantools.database.load_file('luxgen_m7_2009.dbc')
            logger.info(f"DBC 檔案已載入，共 {len(db.messages)} 個訊息定義")
        except FileNotFoundError:
            console.print("[red]DBC 檔案遺失！將無法解碼 CAN 訊號[/red]")
            return

        # 3. 建立信號物件
        signals = WorkerSignals()
        
        def setup_can_data_source(dashboard):
            """設定 CAN Bus 資料來源 - 在 dashboard 準備好後呼叫"""
            
            # 連接信號到 Dashboard
            signals.update_rpm.connect(dashboard.set_rpm)
            signals.update_speed.connect(dashboard.set_speed)
            signals.update_temp.connect(dashboard.set_temperature)
            signals.update_fuel.connect(dashboard.set_fuel)
            signals.update_gear.connect(dashboard.set_gear)
            signals.update_turn_signal.connect(dashboard.set_turn_signal)
            signals.update_door_status.connect(dashboard.set_door_status)
            signals.update_cruise.connect(dashboard.set_cruise)
            signals.update_turbo.connect(dashboard.set_turbo)
            signals.update_battery.connect(dashboard.set_battery)
            
            # 啟動背景執行緒
            logger.info("正在啟動背景執行緒...")
            t_receiver = threading.Thread(
                target=unified_receiver, 
                args=(bus, db, signals), 
                daemon=True, 
                name="CAN-Receiver"
            )
            t_query = threading.Thread(
                target=obd_query, 
                args=(bus, signals), 
                daemon=True, 
                name="OBD-Query"
            )
            
            t_receiver.start()
            t_query.start()
            
            logger.info("儀表板運行中...")
            
            # 返回清理函數
            def cleanup():
                global stop_threads
                logger.info("正在關閉系統...")
                stop_threads = True
                if bus:
                    try:
                        bus.shutdown()
                    except:
                        pass
                console.print("[green]程式已安全結束[/green]")
            
            return cleanup
        
        # 4. 使用統一啟動流程
        console.print("[green]啟動儀表板前端...[/green]")
        
        # 根據連線模式設定視窗標題
        window_title = f"Luxgen M7 儀表板 - {interface_type}"
        
        run_dashboard(
            window_title=window_title,
            setup_data_source=setup_can_data_source
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]收到中斷信號[/yellow]")
        
    except Exception as e:
        console.print(f"[red]嚴重錯誤: {e}[/red]")
        logger.critical(f"主程式崩潰: {e}", exc_info=True)


if __name__ == "__main__":
    main()
