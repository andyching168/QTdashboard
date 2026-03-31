#!/usr/bin/env python3
"""
CAN Bus 模擬器
模擬 Luxgen M7 車輛數據，用於測試儀表板系統
"""

import time
import random
import math
import can
import cantools
import logging
from threading import Thread, Event

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VehicleSimulator:
    """車輛狀態模擬器"""
    
    def __init__(self):
        # 車輛狀態
        self.speed = 0.0  # km/h
        self.rpm = 800.0  # rpm (怠速)
        self.fuel = 65.0  # % (約 2/3 滿)
        self.coolant_temp = 88.0  # °C (正常工作溫度)
        self.throttle = 0.0  # %
        self.gear = 0  # P=0, R=7, N=0, D=1-6
        
        # 模擬模式
        self.mode = "idle"  # idle, accelerating, cruising, decelerating
        self.time_in_mode = 0
        
        # 運動特性
        self.acceleration = 0.0
        self.target_speed = 0.0
        
    def update(self, dt=0.1):
        """更新車輛狀態"""
        self.time_in_mode += dt
        
        # 模式切換邏輯
        if self.mode == "idle":
            if self.time_in_mode > random.uniform(5, 15):
                self.mode = "accelerating"
                self.target_speed = random.uniform(30, 100)  # 家用車常用速度範圍
                self.time_in_mode = 0
                logger.info(f"切換到加速模式，目標速度: {self.target_speed:.1f} km/h")
                
        elif self.mode == "accelerating":
            if self.speed >= self.target_speed * 0.95:
                self.mode = "cruising"
                self.time_in_mode = 0
                logger.info(f"切換到巡航模式，當前速度: {self.speed:.1f} km/h")
                
        elif self.mode == "cruising":
            if self.time_in_mode > random.uniform(10, 30):
                self.mode = "decelerating"
                self.time_in_mode = 0
                logger.info("切換到減速模式")
                
        elif self.mode == "decelerating":
            if self.speed < 5:
                self.mode = "idle"
                self.time_in_mode = 0
                logger.info("切換到怠速模式")
        
        # 根據模式更新參數
        if self.mode == "idle":
            self.throttle = 0
            self.acceleration = -2.0  # 緩慢減速
            self.rpm = 800 + random.uniform(-50, 50)
            
        elif self.mode == "accelerating":
            self.throttle = random.uniform(30, 70)
            self.acceleration = 2.5 + random.uniform(-0.5, 0.5)
            # RPM 與速度相關（家用車一般不超過 6000）
            self.rpm = 1500 + (self.speed / 100.0) * 4000 + random.uniform(-100, 100)
            self.rpm = min(6200, self.rpm)
            
        elif self.mode == "cruising":
            self.throttle = random.uniform(10, 30)
            self.acceleration = random.uniform(-0.5, 0.5)
            self.rpm = 2000 + (self.speed / 120.0) * 2000 + random.uniform(-50, 50)
            
        elif self.mode == "decelerating":
            self.throttle = 0
            self.acceleration = -4.0 + random.uniform(-1, 1)
            self.rpm = max(800, 1000 + (self.speed / 120.0) * 2000)
        
        # 更新速度
        self.speed += self.acceleration * dt
        self.speed = max(0, min(200, self.speed))
        
        # 更新油量 (緩慢減少)
        if self.speed > 0:
            fuel_consumption = (self.throttle / 100.0) * 0.001 * dt
            self.fuel = max(0, self.fuel - fuel_consumption)
        
        # 更新水溫（正常工作溫度 85-95°C）
        target_temp = 90 if self.rpm > 1500 else 85
        if self.coolant_temp < target_temp:
            self.coolant_temp += 0.02 * dt
        elif self.coolant_temp > target_temp:
            self.coolant_temp -= 0.01 * dt
        # 正常範圍 75-98°C，超過 100°C 算過熱
        self.coolant_temp = max(75, min(98, self.coolant_temp))
        
        # 添加一些隨機波動
        self.speed += random.uniform(-0.2, 0.2)
        self.rpm += random.uniform(-20, 20)


class CANSimulator:
    """CAN Bus 模擬器"""
    
    def __init__(self, channel='vcan0', bustype='socketcan', use_virtual_bus=False):
        """
        初始化 CAN 模擬器
        
        Args:
            channel: CAN 通道名稱 (例如 'vcan0' 或 '/dev/pts/X')
            bustype: 'socketcan' (Linux) 或 'virtual' (跨平台測試)
            use_virtual_bus: 是否使用虛擬 bus (不需要實際硬體)
        """
        self.channel = channel
        self.bustype = bustype
        self.use_virtual_bus = use_virtual_bus
        self.running = Event()
        
        # 載入 DBC
        try:
            self.db = cantools.database.load_file('luxgen_m7_2009.dbc')
            logger.info(f"DBC 檔案已載入，共 {len(self.db.messages)} 個訊息定義")
        except Exception as e:
            logger.error(f"載入 DBC 失敗: {e}")
            raise
        
        # 初始化 CAN Bus
        try:
            if use_virtual_bus:
                # 使用虛擬 bus (用於測試，不需要實際硬體)
                self.bus = can.interface.Bus(bustype='virtual', channel=channel)
                logger.info(f"已建立虛擬 CAN Bus: {channel}")
            else:
                # 使用實際硬體或虛擬介面
                self.bus = can.interface.Bus(bustype=bustype, channel=channel)
                logger.info(f"已連接到 CAN Bus: {bustype}:{channel}")
        except Exception as e:
            logger.error(f"無法建立 CAN Bus: {e}")
            logger.info("提示: Linux 用戶可使用 'sudo ip link add dev vcan0 type vcan && sudo ip link set up vcan0'")
            raise
        
        # 車輛模擬器
        self.vehicle = VehicleSimulator()
        
        # OBD-II 請求處理
        self.obd_thread = None
    
    def send_can_message(self, msg_name, data_dict):
        """編碼並發送 CAN 訊息"""
        try:
            # 從 DBC 取得訊息定義
            message = self.db.get_message_by_name(msg_name)
            
            # 編碼數據
            data = message.encode(data_dict)
            
            # 建立並發送 CAN 訊息
            msg = can.Message(
                arbitration_id=message.frame_id,
                data=data,
                is_extended_id=False
            )
            self.bus.send(msg)
            
        except KeyError as e:
            logger.warning(f"DBC 中找不到訊息: {msg_name}")
        except Exception as e:
            logger.error(f"發送 CAN 訊息失敗 ({msg_name}): {e}")
    
    def send_vehicle_data(self):
        """發送車輛數據"""
        # 1. 轉速 (ID 0x340 / 832)
        # 根據檔位決定發送的信號
        rpm_data = {}
        
        # 映射檔位到 TRANS_MODE
        # P=0, R=7, N=0, D=1
        trans_mode = 0
        if self.vehicle.gear == 7: # R
            trans_mode = 7
        elif self.vehicle.gear == 1: # D
            trans_mode = 1
        else: # P or N
            trans_mode = 0
            
        rpm_data['TRANS_MODE'] = trans_mode
        
        if trans_mode == 0: # P/N
            rpm_data['ENGINE_RPM_PN'] = int(self.vehicle.rpm)
        elif trans_mode == 1: # D
            # 模擬: 全部放在 Base，Delta 為 0
            rpm_data['ENGINE_RPM_BASE'] = int(self.vehicle.rpm)
            rpm_data['ENGINE_RPM_DELTA'] = 0
        elif trans_mode == 7: # R
            rpm_data['ENGINE_RPM_BASE_R'] = int(self.vehicle.rpm)
            rpm_data['ENGINE_RPM_DELTA_R'] = 0
            
        self.send_can_message('GEAR_RPM_SPEED_STATUS', rpm_data)
        
        # 2. 油量和節氣門 (ID 0x335 / 821)
        self.send_can_message('THROTTLE_STATUS', {
            'FUEL': self.vehicle.fuel,
            'THROTTLE_POS': int(self.vehicle.throttle * 2.55),
            'THROTTLE_PEDAL_POS': int(self.vehicle.throttle * 2.55),
            'CRUSE_ONOFF': 0,
            'CRUSE_ENABLED': 0
        })
        
        # 3. 速度 (ID 0x38A / 906)
        self.send_can_message('WHEEL_SPEEDS', {
            'SPEED_FL': int(self.vehicle.speed),
            'SPEED_FR': int(self.vehicle.speed),
            'ABS_UNDEF1': 0
        })
    
    def handle_obd_requests(self):
        """處理 OBD-II 請求"""
        logger.info("OBD-II 請求處理執行緒已啟動")
        
        while self.running.is_set():
            try:
                # 接收 OBD 請求 (ID 0x7DF)
                msg = self.bus.recv(timeout=0.5)
                
                if msg is None:
                    continue
                
                # 檢查是否為 OBD 請求
                if msg.arbitration_id == 0x7DF and len(msg.data) >= 3:
                    mode = msg.data[1]
                    pid = msg.data[2]
                    
                    # Mode 01 - 當前數據
                    if mode == 0x01:
                        response_data = None
                        
                        # PID 0C - RPM
                        if pid == 0x0C:
                            rpm_value = int(self.vehicle.rpm * 4)
                            response_data = [
                                0x04,  # 長度
                                0x41,  # Mode 01 回應
                                0x0C,  # PID
                                (rpm_value >> 8) & 0xFF,
                                rpm_value & 0xFF,
                                0, 0, 0
                            ]
                            logger.debug(f"回應 OBD RPM: {self.vehicle.rpm:.0f}")
                        
                        # PID 05 - 水溫
                        elif pid == 0x05:
                            temp_value = int(self.vehicle.coolant_temp + 40)
                            response_data = [
                                0x03,  # 長度
                                0x41,  # Mode 01 回應
                                0x05,  # PID
                                temp_value,
                                0, 0, 0, 0
                            ]
                            logger.debug(f"回應 OBD 水溫: {self.vehicle.coolant_temp:.1f}°C")
                        
                        # 發送回應 (ID 0x7E8)
                        if response_data:
                            response_msg = can.Message(
                                arbitration_id=0x7E8,
                                data=response_data,
                                is_extended_id=False
                            )
                            self.bus.send(response_msg)
                            
            except can.CanError as e:
                logger.error(f"CAN 錯誤: {e}")
            except Exception as e:
                logger.error(f"OBD 處理錯誤: {e}", exc_info=True)
        
        logger.info("OBD-II 請求處理執行緒已停止")
    
    def run(self, update_rate=10):
        """
        運行模擬器
        
        Args:
            update_rate: 每秒更新次數 (Hz)
        """
        self.running.set()
        dt = 1.0 / update_rate
        
        # 啟動 OBD 處理執行緒
        self.obd_thread = Thread(target=self.handle_obd_requests, daemon=True)
        self.obd_thread.start()
        
        logger.info("=" * 50)
        logger.info("CAN 模擬器已啟動")
        logger.info(f"更新頻率: {update_rate} Hz")
        logger.info("按 Ctrl+C 停止")
        logger.info("=" * 50)
        
        try:
            while self.running.is_set():
                # 更新車輛狀態
                self.vehicle.update(dt)
                
                # 發送 CAN 數據
                self.send_vehicle_data()
                
                # 每秒記錄一次狀態
                if int(time.time() * update_rate) % update_rate == 0:
                    logger.info(
                        f"[{self.vehicle.mode:12s}] "
                        f"速度: {self.vehicle.speed:5.1f} km/h | "
                        f"轉速: {self.vehicle.rpm:5.0f} rpm | "
                        f"油量: {self.vehicle.fuel:5.1f}% | "
                        f"水溫: {self.vehicle.coolant_temp:5.1f}°C"
                    )
                
                time.sleep(dt)
                
        except KeyboardInterrupt:
            logger.info("\n收到中斷信號")
        finally:
            self.stop()
    
    def stop(self):
        """停止模擬器"""
        logger.info("正在停止模擬器...")
        self.running.clear()
        
        if self.obd_thread:
            self.obd_thread.join(timeout=2.0)
        
        if self.bus:
            self.bus.shutdown()
            logger.info("CAN Bus 已關閉")
        
        logger.info("模擬器已停止")


def main():
    """主程式"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Luxgen M7 CAN Bus 模擬器')
    parser.add_argument(
        '--channel',
        default='vcan0',
        help='CAN 通道名稱 (預設: vcan0)'
    )
    parser.add_argument(
        '--bustype',
        default='socketcan',
        choices=['socketcan', 'virtual'],
        help='Bus 類型 (預設: socketcan)'
    )
    parser.add_argument(
        '--virtual',
        action='store_true',
        help='使用虛擬 bus (不需要實際硬體)'
    )
    parser.add_argument(
        '--rate',
        type=int,
        default=10,
        help='更新頻率 (Hz, 預設: 10)'
    )
    
    args = parser.parse_args()
    
    try:
        simulator = CANSimulator(
            channel=args.channel,
            bustype=args.bustype,
            use_virtual_bus=args.virtual
        )
        simulator.run(update_rate=args.rate)
    except Exception as e:
        logger.error(f"模擬器啟動失敗: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
