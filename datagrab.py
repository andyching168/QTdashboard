import time
import threading
import sys
import logging
import can
import cantools
import serial.tools.list_ports
from rich.console import Console
from rich.panel import Panel
from rich.align import Align

# PyQt6 Imports
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal

# 引入你的儀表板類別
from main import Dashboard 

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
    # update_nav_icon = pyqtSignal(str) # 預留給導航圖片

# --- 全局變數 ---
current_mode = "HYBRID" 
data_store = {
    "CAN": {"rpm": 0, "speed": 0, "fuel": 0, "hz": 0, "last_update": 0},
    "OBD": {"rpm": 0, "speed": 0, "temp": 0, "hz": 0, "last_update": 0}
}
stop_threads = False
console = Console()
send_lock = threading.Lock() # 保護寫入操作

# --- 1. 硬體連接 ---
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
    for p in ports:
        all_ports.append((p.device, p.description))
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
        console.print(f"[{i}] {device} - {desc}")
    
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
    """
    global data_store
    last_can_hz_calc = time.time()
    can_count = 0
    error_count = 0
    max_consecutive_errors = 100
    
    # RPM 平滑參數
    current_rpm_smoothed = 0.0
    rpm_alpha = 0.25  # 平滑係數 (0.0~1.0)，越小越平滑但反應越慢
    
    # 檔位切換狀態追蹤
    last_gear_str = None
    last_gear_change_time = 0
    
    logger.info("CAN 訊息接收執行緒已啟動")
    
    while not stop_threads:
        try:
            # 使用 recv() 加上 timeout，而不是 iterator，這樣可以安全退出
            msg = bus.recv(timeout=0.1) 
            
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
                    
                    # PID 05 (Temp) - 水箱溫度 (通常只在 ECU 0x7E8)
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
                        
                    elif trans_mode in [0x01, 0x07]: # D 檔 (0x01) 或 R 檔 (0x07)
                        gear_str = "D" if trans_mode == 0x01 else "R"
                            
                    else:
                        # 其他檔位 (S/L 等)
                        gear_str = str(trans_mode)
                    
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
            
            # 3. 處理 FUEL 油量 (ID 0x335 / 821)
            elif msg.arbitration_id == 0x335:
                try:
                    decoded = db.decode_message(msg.arbitration_id, msg.data)
                    # FUEL 縮放 (0.3984, 0)，範圍 0-100%
                    fuel_value = decoded['FUEL']
                    if hasattr(fuel_value, 'value'):
                        fuel = float(fuel_value.value)
                    else:
                        fuel = float(fuel_value)

                    data_store["CAN"]["fuel"] = fuel
                    logger.debug(f"油量: {fuel}%")
                    
                    # 更新前端油量顯示 (0-100%)
                    signals.update_fuel.emit(fuel)  # ✅ 安全發送
                            
                except cantools.database.errors.DecodeError as e:
                    logger.error(f"DBC 解碼錯誤 (FUEL): {e}")
                except Exception as e:
                    logger.error(f"處理油量訊息錯誤: {e}")
            
            # 4. 處理 SPEED_FL 速度 (ID 0x38A / 906)
            elif msg.arbitration_id == 0x38A:
                try:
                    decoded = db.decode_message(msg.arbitration_id, msg.data)
                    # SPEED_FL 縮放 (1, 0)，範圍 0-255 km/h
                    speed_value = decoded['SPEED_FL']
                    if hasattr(speed_value, 'value'):
                        speed = float(speed_value.value)
                    else:
                        speed = float(speed_value)

                    data_store["CAN"]["speed"] = speed
                    logger.debug(f"速度: {speed} km/h")
                    
                    # 更新前端速度顯示
                    signals.update_speed.emit(speed)  # ✅ 安全發送

                    # --- 隱藏版 RPM 解析 (針對 R/D 檔) ---
                    # [已移除] ID 0x38A 證實為輪速訊號，轉彎時會失準，故移除此邏輯。
                    # 改為優化 OBD 查詢頻率與多來源接收。
                    # --------------------------------------
                            
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
                    
                    # 判斷方向燈狀態並發送
                    # 根據 DBC 註解：R,L shows at same time means hazard (雙閃)
                    if left_signal == 1 and right_signal == 1:
                        signals.update_turn_signal.emit("both_on")
                    elif left_signal == 1 and right_signal == 0:
                        signals.update_turn_signal.emit("left_on")
                    elif left_signal == 0 and right_signal == 1:
                        signals.update_turn_signal.emit("right_on")
                    else:
                        signals.update_turn_signal.emit("off")
                    
                    logger.debug(f"方向燈: L={left_signal} R={right_signal}")
                    
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
                    
                    # 發送門狀態到前端 (0=關閉, 1=打開，需要轉換為 is_closed)
                    signals.update_door_status.emit("FL", door_fl == 0)
                    signals.update_door_status.emit("FR", door_fr == 0)
                    signals.update_door_status.emit("RL", door_rl == 0)
                    signals.update_door_status.emit("RR", door_rr == 0)
                    signals.update_door_status.emit("BK", door_bk == 0)
                    
                    logger.debug(f"門狀態: FL={door_fl} FR={door_fr} RL={door_rl} RR={door_rr} BK={door_bk}")
                    
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
            time.sleep(0.1)

            # 查詢 水溫 (PID 0x05)
            msg_temp = can.Message(
                arbitration_id=0x7DF, 
                data=[0x02, 0x01, 0x05, 0, 0, 0, 0, 0], 
                is_extended_id=False
            )
            
            with send_lock:
                bus.send(msg_temp)
            
            time.sleep(0.05)  # 加速查詢頻率 (20Hz) 以獲得更流暢的指針
            
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
    t_receiver = None
    t_query = None
    
    try:
        logger.info("=" * 50)
        logger.info("Luxgen M7 儀表板系統啟動 (Safe Mode)")
        logger.info("=" * 50)
        
        # 1. 優先建立 Qt Application (這是使用 QObject/Signals 的前提)
        app = QApplication(sys.argv)
        
        # 2. 建立信號物件
        signals = WorkerSignals()
        
        # 3. 選擇並連接硬體
        port = select_serial_port()
        if not port:
            logger.error("未選擇 Serial 裝置，程式退出")
            return
        
        logger.info(f"已選擇裝置: {port}")

        try:
            logger.info("正在初始化 CAN Bus...")
            # 設定 SLCAN 介面
            # 注意: 這裡使用 slcan interface，需要 python-can 的 serial 支持
            bus = can.interface.Bus(
                interface='slcan', 
                channel=port, 
                bitrate=500000,
                timeout=0.1
            )
            logger.info(f"CAN Bus 已連接: {bus}")
            
        except Exception as e:
            console.print(f"[red]CAN Bus 初始化失敗: {e}[/red]")
            logger.error(f"CAN Bus 初始化失敗: {e}", exc_info=True)
            return
        
        try:
            # 載入 DBC
            logger.info("正在載入 DBC 檔案...")
            db = cantools.database.load_file('luxgen_m7_2009.dbc')
            logger.info(f"DBC 檔案已載入，共 {len(db.messages)} 個訊息定義")
        except FileNotFoundError:
            console.print("[red]DBC 檔案遺失！將無法解碼 CAN 訊號[/red]")
            return

        # 4. 初始化介面並連接信號
        console.print("[green]啟動儀表板前端...[/green]")
        dashboard = Dashboard()
        
        # ★★★ 關鍵連接步驟 ★★★
        signals.update_rpm.connect(dashboard.set_rpm)
        signals.update_speed.connect(dashboard.set_speed)
        signals.update_temp.connect(dashboard.set_temperature)
        signals.update_fuel.connect(dashboard.set_fuel)
        signals.update_gear.connect(dashboard.set_gear)
        signals.update_turn_signal.connect(dashboard.set_turn_signal)
        signals.update_door_status.connect(dashboard.set_door_status)
        
        dashboard.show()

        # 5. 啟動背景執行緒 (傳入 signals)
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

        # 6. 進入 Qt 事件循環 (這行會卡住主執行緒直到視窗關閉)
        logger.info("儀表板運行中...")
        exit_code = app.exec()
        
        sys.exit(exit_code)

    except KeyboardInterrupt:
        console.print("\n[yellow]收到中斷信號[/yellow]")
        
    except Exception as e:
        console.print(f"[red]嚴重錯誤: {e}[/red]")
        logger.critical(f"主程式崩潰: {e}", exc_info=True)
        
    finally:
        # 清理資源
        logger.info("正在關閉系統...")
        stop_threads = True
        
        if bus:
            try:
                bus.shutdown()
            except:
                pass
        
        console.print("[green]程式已安全結束[/green]")

if __name__ == "__main__":
    main()
