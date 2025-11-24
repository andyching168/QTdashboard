#!/usr/bin/env python3
"""
簡易 CAN 模擬器 (使用虛擬 Serial Port)
使用 socat 建立虛擬 serial port 對進行測試
"""

import time
import random
import math
import struct
import serial
import logging
from threading import Thread, Event

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SimpleVehicleSimulator:
    """簡易車輛模擬器"""
    
    def __init__(self):
        self.speed = 0
        self.rpm = 800
        self.fuel = 65  # 約 2/3 滿
        self.temp = 88  # 正常工作溫度 88-92°C
        self.mode = "idle"
        self.time = 0
    
    def update(self, dt=0.1):
        """更新狀態"""
        self.time += dt
        
        # 簡單的正弦波模擬
        t = self.time / 10.0
        # 速度範圍：0-120 km/h (家用車正常範圍)
        self.speed = max(0, 40 + 40 * (0.5 + 0.5 * random.random()) * abs(math.sin(t)))
        # 轉速：怠速 800 + 速度相關（最高約 5000 rpm）
        self.rpm = 800 + (self.speed / 120.0) * 4200 + random.uniform(-100, 100)
        self.rpm = max(800, min(6500, self.rpm))  # 限制在合理範圍
        # 油量逐漸減少
        self.fuel = max(5, 65 - (self.time / 600.0) * 10)  # 每10分鐘減少約10%
        # 水溫：正常範圍 85-95°C，偶爾波動
        self.temp = 88 + 3 * math.sin(t * 0.3) + random.uniform(-1, 1)
        self.temp = max(80, min(98, self.temp))  # 限制在正常範圍


def create_virtual_ports():
    """
    建立虛擬 serial port 對
    
    需要先安裝: brew install socat (macOS) 或 apt install socat (Linux)
    """
    import subprocess
    import os
    
    logger.info("正在建立虛擬 serial port 對...")
    logger.info("請在另一個終端機執行以下命令：")
    logger.info("")
    logger.info("  socat -d -d pty,raw,echo=0 pty,raw,echo=0")
    logger.info("")
    logger.info("然後使用顯示的兩個 /dev/pts/X 或 /dev/ttys00X 路徑")
    logger.info("一個用於本模擬器，另一個給 datagrab.py")
    logger.info("")


def send_slcan_frame(ser, can_id, data):
    """
    發送 SLCAN 格式的 CAN 訊框
    
    格式: tIIILDDDDDDDDDDDDDDDD\r
    - t: 標準訊框
    - III: CAN ID (3位16進制)
    - L: 資料長度 (1位10進制)
    - DD...: 資料 (每個位元組2位16進制)
    """
    try:
        # 轉換為 SLCAN 格式
        frame = f"t{can_id:03X}{len(data)}"
        for byte in data:
            frame += f"{byte:02X}"
        frame += "\r"
        
        # 發送
        ser.write(frame.encode('ascii'))
        logger.debug(f"發送: {frame.strip()}")
        
    except Exception as e:
        logger.error(f"發送失敗: {e}")


def simulate_can_data(port, baudrate=115200):
    """
    模擬 CAN 數據發送
    
    Args:
        port: Serial port 路徑 (例如 /dev/pts/2 或 /dev/ttys002)
        baudrate: 鮑率
    """
    try:
        # 開啟 serial port
        ser = serial.Serial(port, baudrate, timeout=1)
        logger.info(f"已開啟 serial port: {port}")
        
        # 初始化 SLCAN
        ser.write(b"C\r")  # 關閉通道
        time.sleep(0.1)
        ser.write(b"S6\r")  # 設定為 500kbps
        time.sleep(0.1)
        ser.write(b"O\r")  # 開啟通道
        time.sleep(0.1)
        logger.info("SLCAN 已初始化")
        
        # 車輛模擬器
        vehicle = SimpleVehicleSimulator()
        
        logger.info("=" * 50)
        logger.info("開始發送模擬數據")
        logger.info("按 Ctrl+C 停止")
        logger.info("=" * 50)
        
        try:
            while True:
                # 更新車輛狀態
                vehicle.update(0.1)
                
                # 1. 發送轉速 (ID 0x340 / 832)
                # ENGINE_RPM1 在位元 55:16 (7 bytes, big endian)
                rpm_value = int(vehicle.rpm)
                data_340 = [0] * 8
                data_340[6] = (rpm_value >> 8) & 0xFF
                data_340[7] = rpm_value & 0xFF
                send_slcan_frame(ser, 0x340, data_340)
                
                time.sleep(0.02)
                
                # 2. 發送油量 (ID 0x335 / 821)
                # FUEL 在位元 55:8 (byte 7)
                fuel_raw = int(vehicle.fuel / 0.3984)  # 根據 DBC scale
                data_335 = [0] * 8
                data_335[7] = fuel_raw & 0xFF
                send_slcan_frame(ser, 0x335, data_335)
                
                time.sleep(0.02)
                
                # 3. 發送速度 (ID 0x38A / 906)
                # SPEED_FL 在位元 0:8 (byte 0)
                speed_value = int(vehicle.speed)
                data_38a = [0] * 8
                data_38a[0] = speed_value & 0xFF
                send_slcan_frame(ser, 0x38A, data_38a)
                
                time.sleep(0.02)
                
                # 4. 模擬 OBD 回應 (如果收到請求)
                if ser.in_waiting > 0:
                    request = ser.read(ser.in_waiting)
                    logger.debug(f"收到: {request}")
                    
                    # 簡單的 OBD 回應處理
                    if b"t7DF" in request:
                        # 回應水溫 (PID 05)
                        temp_value = int(vehicle.temp + 40)
                        obd_response = [0x03, 0x41, 0x05, temp_value, 0, 0, 0, 0]
                        send_slcan_frame(ser, 0x7E8, obd_response)
                        
                        time.sleep(0.01)
                        
                        # 回應 RPM (PID 0C)
                        rpm_value = int(vehicle.rpm * 4)
                        obd_response = [0x04, 0x41, 0x0C, (rpm_value >> 8) & 0xFF, rpm_value & 0xFF, 0, 0, 0]
                        send_slcan_frame(ser, 0x7E8, obd_response)
                
                # 每秒記錄一次
                if int(time.time() * 10) % 10 == 0:
                    logger.info(
                        f"速度: {vehicle.speed:5.1f} km/h | "
                        f"轉速: {vehicle.rpm:5.0f} rpm | "
                        f"油量: {vehicle.fuel:5.1f}% | "
                        f"水溫: {vehicle.temp:5.1f}°C"
                    )
                
                time.sleep(0.04)  # ~10Hz 更新率
                
        except KeyboardInterrupt:
            logger.info("\n收到中斷信號")
        finally:
            # 關閉 SLCAN
            ser.write(b"C\r")
            ser.close()
            logger.info("Serial port 已關閉")
            
    except serial.SerialException as e:
        logger.error(f"Serial port 錯誤: {e}")
        logger.info("\n提示：請先建立虛擬 serial port 對")
        logger.info("macOS: socat -d -d pty,raw,echo=0 pty,raw,echo=0")
        logger.info("Linux: socat -d -d pty,raw,echo=0,link=/tmp/vcan0 pty,raw,echo=0,link=/tmp/vcan1")
    except Exception as e:
        logger.error(f"錯誤: {e}", exc_info=True)


def main():
    """主程式"""
    import argparse
    import math
    
    parser = argparse.ArgumentParser(description='簡易 CAN 模擬器 (Serial Port)')
    parser.add_argument(
        'port',
        nargs='?',
        help='Serial port 路徑 (例如 /dev/pts/2 或 /dev/ttys002)'
    )
    parser.add_argument(
        '--baudrate',
        type=int,
        default=115200,
        help='鮑率 (預設: 115200)'
    )
    parser.add_argument(
        '--setup',
        action='store_true',
        help='顯示如何建立虛擬 serial port'
    )
    
    args = parser.parse_args()
    
    if args.setup or not args.port:
        create_virtual_ports()
        if not args.port:
            return 0
    
    simulate_can_data(args.port, args.baudrate)
    return 0


if __name__ == '__main__':
    exit(main())
