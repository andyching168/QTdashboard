import time
import threading
import sys
import logging
import can
import serial.tools.list_ports
from rich.console import Console
from rich.table import Table

# 配置日誌
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("Scanner")
console = Console()

# 全局變數
current_obd_rpm = 0
stop_threads = False
send_lock = threading.Lock()

def select_serial_port():
    ports = list(serial.tools.list_ports.comports())
    # ... (簡化版的 port 選擇邏輯)
    if not ports:
        return None
    if len(ports) == 1:
        return ports[0].device
    
    console.print("[yellow]可用裝置：[/yellow]")
    for i, p in enumerate(ports):
        console.print(f"[{i}] {p.device}")
    idx = int(console.input("請選擇 [0]: ") or 0)
    return ports[idx].device

def obd_query_thread(bus):
    """持續查詢 OBD RPM 作為比對基準"""
    global current_obd_rpm
    while not stop_threads:
        try:
            msg = can.Message(arbitration_id=0x7DF, data=[0x02, 0x01, 0x0C, 0,0,0,0,0], is_extended_id=False)
            with send_lock:
                bus.send(msg)
            
            # 等待回應 (簡單的 blocking receive)
            # 注意：這裡可能會跟 main thread 的 recv 搶，但因為我們只是要一個大概的基準，
            # 其實可以依賴 main thread 接收到的 0x7E8 來更新 current_obd_rpm
            time.sleep(0.2)
        except:
            time.sleep(0.5)

def scanner_main():
    global current_obd_rpm, stop_threads
    
    port = select_serial_port()
    if not port:
        console.print("[red]無可用裝置[/red]")
        return

    try:
        bus = can.interface.Bus(interface='slcan', channel=port, bitrate=500000)
    except Exception as e:
        console.print(f"[red]連接失敗: {e}[/red]")
        return

    console.print(f"[green]已連接 {port}，開始掃描...[/green]")
    console.print("[yellow]請發動引擎，並切換至 R 或 D 檔 (踩住煞車！)[/yellow]")
    console.print("[yellow]輕踩油門讓轉速變化，以利比對[/yellow]")

    # 啟動 OBD 查詢 (只負責發送)
    t = threading.Thread(target=obd_query_thread, args=(bus,), daemon=True)
    t.start()

    # 候選名單計數器
    candidates = {} # Key: (id, byte_start, endian, factor), Value: score

    start_time = time.time()
    
    try:
        while True:
            msg = bus.recv(timeout=0.1)
            if not msg: continue

            # 1. 更新 OBD 基準值
            if msg.arbitration_id == 0x7E8 and msg.data[2] == 0x0C:
                rpm = (msg.data[3] * 256 + msg.data[4]) / 4
                current_obd_rpm = rpm
                # console.print(f"OBD RPM: {rpm}", end="\r")
                continue

            # 如果還沒有 OBD 數據，先不掃描
            if current_obd_rpm < 300: 
                continue

            # 2. 掃描所有可能的 2-byte 組合
            # 我們假設 RPM 是 2 bytes (16-bit)
            data = msg.data
            dlc = len(data)
            if dlc < 2: continue

            # 排除已知的 ID (例如 OBD 回應)
            if msg.arbitration_id in [0x7E8, 0x7DF]: continue
            # 排除原本的 RPM ID (832) 因為我們知道它是錯的
            if msg.arbitration_id == 0x340: continue 

            for i in range(dlc - 1):
                # Big Endian
                val_be = (data[i] << 8) | data[i+1]
                # Little Endian
                val_le = (data[i+1] << 8) | data[i]

                # 測試常見的 Factor
                factors = [1, 0.5, 0.25, 2, 4]
                
                for val, endian in [(val_be, 'BE'), (val_le, 'LE')]:
                    for factor in factors:
                        calc_rpm = val * factor
                        
                        # 比對誤差 (容許 +/- 50 RPM)
                        if abs(calc_rpm - current_obd_rpm) < 50:
                            key = (msg.arbitration_id, i, endian, factor)
                            candidates[key] = candidates.get(key, 0) + 1
                            
                            # 如果命中次數夠多，顯示出來
                            if candidates[key] == 10: # 第一次確認
                                console.print(f"[bold green]發現候選訊號！[/bold green]")
                                console.print(f"ID: {hex(msg.arbitration_id)} ({msg.arbitration_id})")
                                console.print(f"Bytes: {i}-{i+1}, Endian: {endian}, Factor: {factor}")
                                console.print(f"Value: {val} -> Calc: {calc_rpm} (OBD: {current_obd_rpm})")
                                console.print("-" * 30)
                            elif candidates[key] % 50 == 0: # 持續追蹤
                                console.print(f"持續命中: ID {hex(msg.arbitration_id)} Bytes {i}-{i+1} ({endian}) x{factor} = {calc_rpm:.1f}")

    except KeyboardInterrupt:
        stop_threads = True
        bus.shutdown()

if __name__ == "__main__":
    scanner_main()
