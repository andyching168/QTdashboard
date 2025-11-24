import time
import threading
import sys
import logging
import can
import cantools
import serial.tools.list_ports
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.console import Console
from rich.align import Align
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
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

# --- 全局變數 ---
current_mode = "HYBRID" # HYBRID (同時跑), CAN_ONLY, OBD_ONLY
data_store = {
    "CAN": {"rpm": 0, "speed": 0, "fuel": 0, "update_count": 0, "last_update": 0, "hz": 0},
    "OBD": {"rpm": 0, "speed": 0, "temp": 0, "update_count": 0, "last_update": 0, "hz": 0}
}
stop_threads = False
console = Console()
dashboard = None  # PyQt6 儀表板實例

# 新增一個鎖，只用來保護「發送」操作，避免寫入衝突
send_lock = threading.Lock()

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
# --- 合併後的單一接收邏輯 ---
def unified_receiver(bus, db):
    """統一處理所有接收到的 CAN 訊息 (包含 DBC 解碼和 OBD 解析)"""
    global data_store, dashboard
    last_can_hz_calc = time.time()
    can_count = 0
    error_count = 0
    max_consecutive_errors = 100
    
    logger.info("CAN 訊息接收執行緒已啟動")
    
    while not stop_threads:
        try:
            # 使用 recv() 加上 timeout，而不是 iterator，這樣可以安全退出
            msg = bus.recv(timeout=0.1) 
            
            if msg is None: 
                continue # 超時沒數據，繼續下一圈
            
            # 重置錯誤計數（收到有效訊息）
            error_count = 0

            # 1. 處理 OBD 回應 (ID 0x7E8)
            if msg.arbitration_id == 0x7E8:
                try:
                    if len(msg.data) < 3:
                        logger.warning(f"OBD 訊息長度不足: {len(msg.data)} bytes")
                        continue
                    
                    # PID 0C (RPM)
                    if msg.data[2] == 0x0C:
                        if len(msg.data) < 5:
                            logger.warning("RPM 資料長度不足")
                            continue
                        rpm = (msg.data[3] * 256 + msg.data[4]) / 4
                        data_store["OBD"]["rpm"] = rpm
                        data_store["OBD"]["last_update"] = time.time()
                        logger.debug(f"OBD RPM: {rpm}")
                    
                    # PID 05 (Temp) - 水箱溫度
                    elif msg.data[2] == 0x05:
                        if len(msg.data) < 4:
                            logger.warning("水溫資料長度不足")
                            continue
                        temp = msg.data[3] - 40
                        data_store["OBD"]["temp"] = temp
                        logger.debug(f"水箱溫度: {temp}°C")
                        
                        # 更新前端水溫顯示
                        # 40°C -> 0%, 80°C -> 50%, 120°C -> 100%
                        if dashboard:
                            try:
                                temp_normalized = ((temp - 40) / 80.0) * 100
                                temp_normalized = max(0, min(100, temp_normalized))
                                dashboard.set_temperature(temp_normalized)
                            except Exception as e:
                                logger.error(f"更新前端水溫失敗: {e}")
                                
                except (IndexError, KeyError) as e:
                    logger.error(f"解析 OBD 訊息錯誤 (ID 0x7E8): {e}, data: {msg.data.hex()}")
                except Exception as e:
                    logger.error(f"處理 OBD 訊息未預期錯誤: {e}")

            # 2. 處理 ENGINE_RPM1 (ID 0x340 / 832)
            elif msg.arbitration_id == 0x340:
                try:
                    decoded = db.decode_message(msg.arbitration_id, msg.data)
                    rpm_raw = decoded.get('ENGINE_RPM1', 0)
                    data_store["CAN"]["rpm"] = rpm_raw
                    data_store["CAN"]["last_update"] = time.time()
                    
                    # 更新前端轉速顯示 (轉換為千轉)
                    if dashboard:
                        try:
                            dashboard.set_rpm(rpm_raw / 1000.0)
                        except Exception as e:
                            logger.error(f"更新前端轉速失敗: {e}")
                    
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
                    fuel = decoded.get('FUEL', 0)
                    data_store["CAN"]["fuel"] = fuel
                    logger.debug(f"油量: {fuel}%")
                    
                    # 更新前端油量顯示 (0-100%)
                    if dashboard:
                        try:
                            dashboard.set_fuel(fuel)
                        except Exception as e:
                            logger.error(f"更新前端油量失敗: {e}")
                            
                except cantools.database.errors.DecodeError as e:
                    logger.error(f"DBC 解碼錯誤 (FUEL): {e}")
                except Exception as e:
                    logger.error(f"處理油量訊息錯誤: {e}")
            
            # 4. 處理 SPEED_FL 速度 (ID 0x38A / 906)
            elif msg.arbitration_id == 0x38A:
                try:
                    decoded = db.decode_message(msg.arbitration_id, msg.data)
                    speed = decoded.get('SPEED_FL', 0)
                    data_store["CAN"]["speed"] = speed
                    logger.debug(f"速度: {speed} km/h")
                    
                    # 更新前端速度顯示
                    if dashboard:
                        try:
                            dashboard.set_speed(speed)
                        except Exception as e:
                            logger.error(f"更新前端速度失敗: {e}")
                            
                except cantools.database.errors.DecodeError as e:
                    logger.error(f"DBC 解碼錯誤 (SPEED_FL): {e}")
                except Exception as e:
                    logger.error(f"處理速度訊息錯誤: {e}")
                
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

def obd_query(bus):
    """主動查詢 OBD-II (保持獨立執行緒，但加鎖)"""
    global data_store
    last_hz_calc = time.time()
    count = 0
    error_count = 0
    max_errors = 50
    
    logger.info("OBD-II 查詢執行緒已啟動")
    
    while not stop_threads:
        if current_mode == "CAN_ONLY":
            time.sleep(0.5)
            continue

        try:
            # 1. 查 RPM
            msg_rpm = can.Message(
                arbitration_id=0x7DF, 
                data=[0x02, 0x01, 0x0C, 0, 0, 0, 0, 0], 
                is_extended_id=False
            )
            
            # 2. 查 水溫
            msg_temp = can.Message(
                arbitration_id=0x7DF, 
                data=[0x02, 0x01, 0x05, 0, 0, 0, 0, 0], 
                is_extended_id=False
            )

            try:
                with send_lock:  # 加鎖保護寫入
                    bus.send(msg_rpm)
                    logger.debug("已發送 OBD RPM 查詢")
                time.sleep(0.05)  # 間隔一下
                
                with send_lock:  # 加鎖保護寫入
                    bus.send(msg_temp)
                    logger.debug("已發送 OBD 水溫查詢")
                
                # 重置錯誤計數（成功發送）
                error_count = 0
                
            except can.CanError as e:
                error_count += 1
                logger.error(f"OBD 查詢發送失敗: {e}")
                if error_count >= max_errors:
                    logger.critical(f"OBD 查詢連續失敗 {max_errors} 次，執行緒即將停止")
                    break
                time.sleep(1.0)  # 錯誤後延長等待時間
                continue
                
            except Exception as e:
                error_count += 1
                logger.error(f"OBD 查詢未預期錯誤: {e}", exc_info=True)
                if error_count >= max_errors:
                    logger.critical(f"OBD 查詢連續失敗 {max_errors} 次，執行緒即將停止")
                    break
                time.sleep(1.0)
                continue

            time.sleep(0.2)  # 稍微放慢查詢速度，避免塞爆 slcan 緩衝區
            
            count += 1
            now = time.time()
            if now - last_hz_calc >= 1.0:
                data_store["OBD"]["hz"] = count
                logger.debug(f"OBD 查詢率: {count} Hz")
                count = 0
                last_hz_calc = now
                
        except Exception as e:
            logger.error(f"OBD 查詢迴圈錯誤: {e}", exc_info=True)
            time.sleep(1.0)
    
    logger.info("OBD-II 查詢執行緒已停止")

# --- 3. UI 顯示 ---
def generate_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=3)
    )
    layout["body"].split_row(
        Layout(name="can_panel"),
        Layout(name="obd_panel")
    )
    return layout

def update_display(layout):
    # Header
    mode_text = f"[bold white on blue] 目前模式: {current_mode} (按 'm' 切換, 'q' 退出) [/]"
    layout["header"].update(Panel(Align.center(mode_text), title="Luxgen 7 MPV Dashboard Demo"))

    # CAN Panel
    can_table = Table(expand=True)
    can_table.add_column("Metric", style="cyan")
    can_table.add_column("Value", style="bold green")
    can_table.add_row("RPM", f"{float(data_store['CAN']['rpm']):.0f}")
    can_table.add_row("更新率 (Hz)", f"{data_store['CAN']['hz']}")
    can_table.add_row("資料來源", "被動監聽 (DBC)")
    can_table.add_row("特點", "極低延遲，無需請求")
    
    can_style = "green" if current_mode in ["HYBRID", "CAN_ONLY"] else "dim"
    layout["can_panel"].update(Panel(can_table, title="CAN Bus (儀表級數據)", border_style=can_style))

    # OBD Panel
    obd_table = Table(expand=True)
    obd_table.add_column("Metric", style="magenta")
    obd_table.add_column("Value", style="bold yellow")
    obd_table.add_row("RPM", f"{float(data_store['OBD']['rpm']):.0f}")
    obd_table.add_row("水溫", f"{data_store['OBD']['temp']} °C")
    obd_table.add_row("請求率 (Hz)", f"{data_store['OBD']['hz']}")
    obd_table.add_row("資料來源", "主動詢答 (OBD-II)")
    obd_table.add_row("特點", "通用但有延遲")

    obd_style = "yellow" if current_mode in ["HYBRID", "OBD_ONLY"] else "dim"
    layout["obd_panel"].update(Panel(obd_table, title="OBD-II (診斷級數據)", border_style=obd_style))

    # Footer comparison
    diff = abs(float(data_store['CAN']['rpm']) - float(data_store['OBD']['rpm']))
    footer_text = f"RPM 差異: {diff:.0f} | CAN 更新速度是 OBD 的 {data_store['CAN']['hz'] / max(1, data_store['OBD']['hz']):.1f} 倍"
    layout["footer"].update(Panel(Align.center(footer_text), title="即時對比"))

# --- 主程式 ---
def main():
    global current_mode, stop_threads, dashboard
    
    bus = None
    db = None
    t_receiver = None
    t_query = None
    
    try:
        logger.info("=" * 50)
        logger.info("Luxgen M7 儀表板系統啟動")
        logger.info("=" * 50)
        
        # 1. 連接
        port = select_serial_port()
        if not port:
            logger.error("未選擇 Serial 裝置，程式退出")
            return
        
        logger.info(f"已選擇裝置: {port}")

        try:
            # 初始化 CAN Bus
            logger.info("正在初始化 CAN Bus...")
            logger.info("注意: SLCAN 初始化可能需要 5-10 秒...")
            
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("CAN Bus 初始化超時")
            
            # 設定 15 秒超時
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(15)
            
            try:
                bus = can.interface.Bus(
                    interface='slcan',  # 使用 interface 取代 bustype
                    channel=port, 
                    bitrate=500000,
                    timeout=5  # 設定通訊超時
                )
                signal.alarm(0)  # 取消超時
                logger.info(f"CAN Bus 已連接: {bus}")
            except TimeoutError:
                signal.alarm(0)
                raise TimeoutError("SLCAN 初始化超時 (15秒)，請檢查設備連接")
            
        except TimeoutError as e:
            console.print(f"[red]CAN Bus 初始化超時: {e}[/red]")
            console.print("[yellow]提示: 使用 simple_simulator.py 時無法直接連接 SLCAN[/yellow]")
            console.print("[yellow]請改用前端測試模式: python main.py[/yellow]")
            logger.error(f"CAN Bus 初始化超時: {e}")
            return
        except OSError as e:
            console.print(f"[red]無法開啟 CAN Bus 裝置: {e}[/red]")
            console.print("[yellow]提示: 虛擬 serial port 可能不支援 SLCAN 協定[/yellow]")
            logger.error(f"CAN Bus 連接失敗: {e}")
            return
        except Exception as e:
            console.print(f"[red]CAN Bus 初始化錯誤: {e}[/red]")
            console.print("[yellow]如要測試前端介面，請直接執行: python main.py[/yellow]")
            logger.error(f"CAN Bus 初始化失敗: {e}", exc_info=True)
            return
        
        try:
            # 載入 DBC
            logger.info("正在載入 DBC 檔案...")
            db = cantools.database.load_file('luxgen_m7_2009.dbc')
            logger.info(f"DBC 檔案已載入，共 {len(db.messages)} 個訊息定義")
            
        except FileNotFoundError:
            console.print("[red]找不到 luxgen_m7_2009.dbc 檔案！[/red]")
            logger.error("DBC 檔案不存在")
            return
        except Exception as e:
            console.print(f"[red]載入 DBC 檔案失敗: {e}[/red]")
            logger.error(f"DBC 載入錯誤: {e}", exc_info=True)
            return

        # 2. 啟動執行緒
        logger.info("正在啟動背景執行緒...")
        t_receiver = threading.Thread(target=unified_receiver, args=(bus, db), daemon=True, name="CAN-Receiver")
        t_query = threading.Thread(target=obd_query, args=(bus,), daemon=True, name="OBD-Query")
        
        t_receiver.start()
        t_query.start()
        logger.info("背景執行緒已啟動")

        # 3. 啟動 PyQt6 前端顯示
        console.print("[green]啟動儀表板前端...[/green]")
        logger.info("正在初始化 Qt 應用程式...")
        
        try:
            app = QApplication(sys.argv)
            dashboard = Dashboard()
            dashboard.show()
            logger.info("儀表板視窗已開啟")
            
            # 啟動 Qt 事件循環
            exit_code = app.exec()
            logger.info(f"Qt 應用程式已關閉，退出碼: {exit_code}")
            sys.exit(exit_code)
            
        except Exception as e:
            console.print(f"[red]前端啟動失敗: {e}[/red]")
            logger.error(f"Qt 應用程式錯誤: {e}", exc_info=True)
            raise
            
    except KeyboardInterrupt:
        console.print("\n[yellow]收到中斷信號 (Ctrl+C)[/yellow]")
        logger.info("使用者中斷程式")
        
    except Exception as e:
        console.print(f"[red]程式發生嚴重錯誤: {e}[/red]")
        logger.critical(f"主程式嚴重錯誤: {e}", exc_info=True)
        
    finally:
        # 清理資源
        logger.info("正在清理資源...")
        stop_threads = True
        
        # 等待執行緒結束
        if t_receiver and t_receiver.is_alive():
            logger.info("等待接收執行緒結束...")
            t_receiver.join(timeout=2.0)
            
        if t_query and t_query.is_alive():
            logger.info("等待查詢執行緒結束...")
            t_query.join(timeout=2.0)
        
        # 關閉 CAN Bus
        if bus:
            try:
                logger.info("正在關閉 CAN Bus...")
                bus.shutdown()
                logger.info("CAN Bus 已關閉")
            except Exception as e:
                logger.error(f"關閉 CAN Bus 時發生錯誤: {e}")
        
        console.print("[green]程式已安全結束[/green]")
        logger.info("程式結束")
        logger.info("=" * 50)

if __name__ == "__main__":
    main()
