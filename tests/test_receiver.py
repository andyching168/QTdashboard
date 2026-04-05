#!/usr/bin/env python3
"""
直接 Serial 接收器 - 不使用 SLCAN，直接解析 ASCII CAN 訊框
專門用於測試 simple_simulator.py
"""

import sys
import time
import serial
import logging
from PyQt6.QtWidgets import QApplication
from main import Dashboard

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全域變數
dashboard = None
stop_flag = False


def parse_slcan_frame(frame_str):
    """
    解析 SLCAN 格式的訊框
    格式: tIIILDDDDDDDDDDDDDDDD
    - t: 標準訊框
    - III: CAN ID (3位16進制)
    - L: 資料長度
    - DD: 資料位元組
    
    Returns: (can_id, data_bytes) 或 None
    """
    try:
        if not frame_str.startswith('t') or len(frame_str) < 5:
            return None
        
        # 解析 CAN ID
        can_id = int(frame_str[1:4], 16)
        
        # 解析資料長度
        data_len = int(frame_str[4])
        
        # 解析資料
        data = []
        for i in range(data_len):
            byte_pos = 5 + i * 2
            if byte_pos + 2 <= len(frame_str):
                data.append(int(frame_str[byte_pos:byte_pos+2], 16))
        
        return (can_id, data)
    
    except Exception as e:
        logger.debug(f"解析訊框失敗: {frame_str.strip()} - {e}")
        return None


def process_can_message(can_id, data):
    """處理 CAN 訊息並更新儀表板"""
    global dashboard
    
    if not dashboard:
        return
    
    try:
        # 1. ENGINE_RPM1 (ID 0x340 / 832)
        if can_id == 0x340 and len(data) >= 8:
            # ENGINE_RPM1 在 byte 6-7 (big endian)
            rpm_raw = (data[6] << 8) | data[7]
            rpm = rpm_raw / 1000.0  # 轉換為千轉
            dashboard.set_rpm(rpm)
            logger.debug(f"RPM: {rpm:.1f} x1000")
        
        # 2. FUEL (ID 0x335 / 821)
        elif can_id == 0x335 and len(data) >= 8:
            # FUEL 在 byte 7，需要乘以 scale (0.3984)
            fuel_raw = data[7]
            fuel = fuel_raw * 0.3984
            dashboard.set_fuel(min(100, fuel))
            logger.debug(f"Fuel: {fuel:.1f}%")
        
        # 3. SPEED_FL (ID 0x38A / 906)
        elif can_id == 0x38A and len(data) >= 1:
            # SPEED_FL 在 byte 0
            speed = data[0]
            dashboard.set_speed(speed)
            logger.debug(f"Speed: {speed} km/h")
        
        # 4. OBD 回應 (ID 0x7E8)
        elif can_id == 0x7E8 and len(data) >= 4:
            if data[1] == 0x41:  # Mode 01 回應
                pid = data[2]
                
                # PID 05 - 水溫
                if pid == 0x05 and len(data) >= 4:
                    temp = data[3] - 40
                    # 轉換到儀表範圍 0-100
                    # 40°C -> 0, 80°C -> 50 (正常), 120°C -> 100
                    temp_normalized = ((temp - 40) / 80.0) * 100
                    temp_normalized = max(0, min(100, temp_normalized))
                    dashboard.set_temperature(temp_normalized)
                    logger.debug(f"Temp: {temp}°C -> {temp_normalized:.1f}%")
                
                # PID 0C - RPM (OBD)
                elif pid == 0x0C and len(data) >= 5:
                    rpm_value = ((data[3] << 8) | data[4]) / 4
                    logger.debug(f"OBD RPM: {rpm_value:.0f}")
    
    except Exception as e:
        logger.error(f"處理 CAN 訊息錯誤 (ID 0x{can_id:03X}): {e}")


def serial_receiver(port, baudrate=115200):
    """從 Serial Port 接收並解析數據"""
    global stop_flag
    
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        logger.info(f"已連接到: {port}")
        
        buffer = ""
        frame_count = 0
        last_log_time = time.time()
        
        while not stop_flag:
            try:
                # 讀取數據
                if ser.in_waiting > 0:
                    data = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                    buffer += data
                    
                    # 處理完整的訊框 (以 \r 或 \n 結尾)
                    while '\r' in buffer or '\n' in buffer:
                        # 找到第一個分隔符
                        split_char = '\r' if '\r' in buffer else '\n'
                        frame, buffer = buffer.split(split_char, 1)
                        
                        if frame:
                            result = parse_slcan_frame(frame)
                            if result:
                                can_id, data_bytes = result
                                process_can_message(can_id, data_bytes)
                                frame_count += 1
                
                # 每秒記錄統計
                now = time.time()
                if now - last_log_time >= 5.0:
                    logger.info(f"接收速率: {frame_count / 5.0:.1f} frames/sec")
                    frame_count = 0
                    last_log_time = now
                
                time.sleep(0.01)
                
            except serial.SerialException as e:
                logger.error(f"Serial 讀取錯誤: {e}")
                break
            except Exception as e:
                logger.error(f"處理錯誤: {e}", exc_info=True)
        
        ser.close()
        logger.info("Serial port 已關閉")
        
    except serial.SerialException as e:
        logger.error(f"無法開啟 serial port: {e}")
    except Exception as e:
        logger.error(f"接收器錯誤: {e}", exc_info=True)


def main():
    """主程式"""
    global dashboard, stop_flag
    
    import argparse
    from threading import Thread
    
    parser = argparse.ArgumentParser(description='直接 Serial 接收器 (測試用)')
    parser.add_argument('port', help='Serial port 路徑 (例如 /dev/ttys014)')
    parser.add_argument('--baudrate', type=int, default=115200, help='鮑率 (預設: 115200)')
    
    args = parser.parse_args()
    
    logger.info("=" * 50)
    logger.info("直接 Serial 接收器 (測試模式)")
    logger.info(f"連接到: {args.port}")
    logger.info("=" * 50)
    
    # 啟動接收執行緒
    receiver_thread = Thread(
        target=serial_receiver, 
        args=(args.port, args.baudrate), 
        daemon=True
    )
    receiver_thread.start()
    
    # 啟動 Qt 前端
    logger.info("正在啟動儀表板...")
    app = QApplication(sys.argv)
    dashboard = Dashboard()
    dashboard.show()
    
    try:
        exit_code = app.exec()
        stop_flag = True
        receiver_thread.join(timeout=2.0)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\n程式中斷")
        stop_flag = True
        receiver_thread.join(timeout=2.0)


if __name__ == '__main__':
    main()
