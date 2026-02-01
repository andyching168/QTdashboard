"""
硬體初始化模組 - RPi 啟動時的硬體檢測與重試機制

在樹莓派上啟動時，會持續檢測以下硬體：
- CAN Bus (SocketCAN 或 SLCAN)
- GPS 模組 (Serial)
- GPIO 按鈕 (gpiozero)

如果有任何硬體未就緒，會持續重試直到：
1. 所有硬體都成功初始化
2. 達到超時時間（預設 60 秒）

在非 RPi 環境（開發環境）下，會跳過硬體檢測。
"""

import time
import platform
import threading
import logging
from typing import Tuple, Optional, Callable, Dict
from dataclasses import dataclass, field
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console()
logger = logging.getLogger(__name__)


def is_raspberry_pi() -> bool:
    """檢測是否在樹莓派上運行"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            return 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo
    except:
        return False


@dataclass
class HardwareStatus:
    """硬體狀態"""
    can_ready: bool = False
    gps_ready: bool = False
    gpio_ready: bool = False
    can_error: str = ""
    gps_error: str = ""
    gpio_error: str = ""
    can_interface: str = ""
    gps_port: str = ""
    
    @property
    def all_ready(self) -> bool:
        """所有硬體是否都已就緒"""
        return self.can_ready and self.gps_ready and self.gpio_ready
    
    @property
    def ready_count(self) -> int:
        """已就緒的硬體數量"""
        count = 0
        if self.can_ready:
            count += 1
        if self.gps_ready:
            count += 1
        if self.gpio_ready:
            count += 1
        return count
    
    def summary(self) -> str:
        """返回狀態摘要"""
        lines = []
        lines.append(f"CAN: {'✓ ' + self.can_interface if self.can_ready else '✗ ' + self.can_error}")
        lines.append(f"GPS: {'✓ ' + self.gps_port if self.gps_ready else '✗ ' + self.gps_error}")
        lines.append(f"GPIO: {'✓ 已初始化' if self.gpio_ready else '✗ ' + self.gpio_error}")
        return "\n".join(lines)
    
    def to_gui_dict(self, attempt: int = 0, elapsed: float = 0, timeout: float = 60) -> dict:
        """轉換為 GUI 可用的字典格式"""
        return {
            'can_ready': self.can_ready,
            'gps_ready': self.gps_ready,
            'gpio_ready': self.gpio_ready,
            'can_error': self.can_error,
            'gps_error': self.gps_error,
            'gpio_error': self.gpio_error,
            'can_interface': self.can_interface,
            'gps_port': self.gps_port,
            'attempt': attempt,
            'elapsed': elapsed,
            'timeout': timeout
        }


class HardwareInitializer:
    """
    硬體初始化器
    
    在 RPi 上會持續重試檢測硬體，直到所有硬體就緒或超時。
    在開發環境（非 RPi）會跳過實體硬體檢測。
    """
    
    # 配置參數
    DEFAULT_TIMEOUT = 60.0       # 預設超時（秒）
    RETRY_INTERVAL = 0.5         # 重試間隔（秒）- 縮短以提供更快的反應
    CAN_BITRATE = 500000         # CAN Bus 速率
    GPS_BAUD_RATES = [9600, 115200, 38400]  # GPS 嘗試的波特率
    
    def __init__(self, 
                 timeout: float = DEFAULT_TIMEOUT,
                 retry_interval: float = RETRY_INTERVAL,
                 require_gps: bool = True,
                 require_gpio: bool = True,
                 on_progress: Optional[Callable[[HardwareStatus, int, float], None]] = None):
        """
        初始化硬體初始化器
        
        Args:
            timeout: 超時時間（秒），0 表示無限等待
            retry_interval: 重試間隔（秒）
            require_gps: 是否需要 GPS（如果為 False，GPS 初始化失敗不會阻止啟動）
            require_gpio: 是否需要 GPIO（如果為 False，GPIO 初始化失敗不會阻止啟動）
            on_progress: 進度回調函數 (status, attempt, elapsed_time)
        """
        self.timeout = timeout
        self.retry_interval = retry_interval
        self.require_gps = require_gps
        self.require_gpio = require_gpio
        self.on_progress = on_progress
        
        self._status = HardwareStatus()
        self._stop_requested = False
        self._can_bus = None
        
    @property
    def status(self) -> HardwareStatus:
        """取得當前硬體狀態"""
        return self._status
    
    @property
    def can_bus(self):
        """取得已初始化的 CAN Bus 實例"""
        return self._can_bus
    
    def stop(self):
        """請求停止初始化（用於外部中斷）"""
        self._stop_requested = True
    
    def _check_can(self) -> bool:
        """
        檢測 CAN Bus（簡化版）
        
        優先順序：
        1. 嘗試 SocketCAN can0（最常見的設定）
        2. 嘗試 SLCAN（掃描 USB 串口）
        
        Returns:
            bool: True 如果 CAN Bus 可用
        """
        try:
            import can
            
            # === 1. 直接嘗試 SocketCAN can0 ===
            if platform.system() == 'Linux':
                try:
                    bus = can.interface.Bus(
                        interface='socketcan',
                        channel='can0',
                        bitrate=self.CAN_BITRATE,
                        receive_own_messages=False
                    )
                    self._can_bus = bus
                    self._status.can_interface = "SocketCAN (can0)"
                    self._status.can_ready = True
                    self._status.can_error = ""
                    logger.info("CAN Bus 連接成功: SocketCAN can0")
                    return True
                except Exception as e:
                    logger.debug(f"SocketCAN can0 失敗: {e}")
                    self._status.can_error = f"can0: {str(e)[:30]}"
            
            # === 2. 嘗試 SLCAN（掃描所有 USB 串口）===
            try:
                import serial.tools.list_ports
                ports = list(serial.tools.list_ports.comports())
                
                for port in ports:
                    # 跳過藍牙等非 USB 裝置
                    if 'bluetooth' in port.device.lower():
                        continue
                    
                    try:
                        bus = can.interface.Bus(
                            interface='slcan',
                            channel=port.device,
                            bitrate=self.CAN_BITRATE,
                            timeout=0.1,
                            receive_own_messages=False
                        )
                        self._can_bus = bus
                        self._status.can_interface = f"SLCAN ({port.device})"
                        self._status.can_ready = True
                        self._status.can_error = ""
                        logger.info(f"CAN Bus 連接成功: SLCAN {port.device}")
                        return True
                    except Exception as e:
                        logger.debug(f"SLCAN {port.device} 失敗: {e}")
                        continue
                
                if not self._status.can_error:
                    self._status.can_error = "未找到 CAN 裝置"
            except ImportError:
                self._status.can_error = "缺少 pyserial"
            
            return False
            
        except ImportError as e:
            self._status.can_error = f"缺少 python-can"
            return False
        except Exception as e:
            self._status.can_error = str(e)[:50]
            return False
    
    def _check_gps(self) -> bool:
        """
        檢測 GPS 模組（簡化版 - 快速檢測）
        
        GPS 不是必需的，所以只做簡單檢測
        
        Returns:
            bool: True 如果 GPS 可用
        """
        # GPS 是可選的，如果不需要就直接標記為「已跳過」
        if not self.require_gps:
            self._status.gps_ready = True
            self._status.gps_error = ""
            self._status.gps_port = "跳過（非必需）"
            return True
        
        try:
            import serial
            import serial.tools.list_ports
            
            # 快速掃描常見的 GPS 串口
            gps_ports = ['/dev/ttyUSB0', '/dev/ttyACM0', '/dev/ttyAMA0']
            
            for port_path in gps_ports:
                try:
                    ser = serial.Serial(port_path, 9600, timeout=0.5)
                    # 快速讀取，看是否有 NMEA 數據
                    for _ in range(3):
                        line = ser.readline().decode('ascii', errors='ignore')
                        if line.startswith('$GP') or line.startswith('$GN'):
                            ser.close()
                            self._status.gps_port = port_path
                            self._status.gps_ready = True
                            self._status.gps_error = ""
                            return True
                    ser.close()
                except:
                    continue
            
            self._status.gps_error = "未找到 GPS"
            return False
            
        except ImportError:
            self._status.gps_error = "缺少 pyserial"
            return False
        except Exception as e:
            self._status.gps_error = str(e)[:30]
            return False
    
    def _check_gpio(self) -> bool:
        """
        檢測 GPIO（簡化版 - 快速檢測）
        
        GPIO 不是必需的，只做基本檢測
        
        Returns:
            bool: True 如果 GPIO 可用
        """
        # GPIO 是可選的，如果不需要就直接標記為「已跳過」
        if not self.require_gpio:
            self._status.gpio_ready = True
            self._status.gpio_error = ""
            return True
        
        try:
            from gpiozero import Device
            from gpiozero.pins.rpigpio import RPiGPIOFactory
            
            # 嘗試設定 GPIO factory
            try:
                Device.pin_factory = RPiGPIOFactory()
                self._status.gpio_ready = True
                self._status.gpio_error = ""
                return True
            except Exception as e:
                self._status.gpio_error = f"GPIO 不可用: {str(e)[:20]}"
                return False
                
        except ImportError:
            self._status.gpio_error = "gpiozero 未安裝"
            return False
        except Exception as e:
            self._status.gpio_error = str(e)[:30]
            return False
    
    def initialize(self, show_progress: bool = True) -> Tuple[bool, HardwareStatus]:
        """
        執行硬體初始化
        
        Args:
            show_progress: 是否顯示進度（在終端機顯示）
        
        Returns:
            (success, status): 
                - success: 所有必要硬體是否都已初始化
                - status: 硬體狀態詳情
        """
        self._stop_requested = False
        
        # 非 RPi 環境：跳過硬體檢測
        if not is_raspberry_pi():
            console.print("[yellow]⚠️  非 Raspberry Pi 環境，跳過硬體檢測[/yellow]")
            logger.info("非 Raspberry Pi 環境，跳過硬體檢測")
            # 在開發環境標記為「就緒」以允許程式繼續
            self._status.can_ready = False
            self._status.gps_ready = True  # 開發時不需要 GPS
            self._status.gpio_ready = True  # 開發時不需要 GPIO
            self._status.can_error = "開發環境"
            self._status.gps_error = "開發環境 (模擬)"
            self._status.gpio_error = "開發環境 (鍵盤模擬)"
            return False, self._status
        
        console.print(Panel.fit(
            "[bold cyan]Raspberry Pi 硬體初始化[/bold cyan]\n"
            "正在檢測 CAN Bus、GPS、GPIO...",
            title="🔧 硬體檢測"
        ))
        
        start_time = time.time()
        attempt = 0
        
        while not self._stop_requested:
            attempt += 1
            elapsed = time.time() - start_time
            
            # 檢查超時
            if self.timeout > 0 and elapsed >= self.timeout:
                console.print(f"[red]⏱️  硬體初始化超時 ({self.timeout:.0f}秒)[/red]")
                logger.error(f"硬體初始化超時: {self._status.summary()}")
                break
            
            # 檢測各項硬體
            if not self._status.can_ready:
                self._check_can()
            
            if not self._status.gps_ready:
                self._check_gps()
            
            if not self._status.gpio_ready:
                self._check_gpio()
            
            # 顯示當前狀態
            if show_progress:
                remaining = self.timeout - elapsed if self.timeout > 0 else float('inf')
                console.print(
                    f"[cyan]嘗試 #{attempt}[/cyan] "
                    f"(已用時: {elapsed:.1f}s, "
                    f"剩餘: {remaining:.1f}s)\n"
                    f"  CAN: {'[green]✓[/green]' if self._status.can_ready else '[red]✗[/red] ' + self._status.can_error}\n"
                    f"  GPS: {'[green]✓[/green]' if self._status.gps_ready else '[red]✗[/red] ' + self._status.gps_error}\n"
                    f"  GPIO: {'[green]✓[/green]' if self._status.gpio_ready else '[red]✗[/red] ' + self._status.gpio_error}"
                )
            
            # 進度回調
            if self.on_progress:
                self.on_progress(self._status, attempt, elapsed)
            
            # 檢查是否全部就緒
            required_ready = self._status.can_ready
            if self.require_gps:
                required_ready = required_ready and self._status.gps_ready
            if self.require_gpio:
                required_ready = required_ready and self._status.gpio_ready
            
            if required_ready:
                console.print("[bold green]✓ 所有必要硬體已就緒！[/bold green]")
                logger.info(f"硬體初始化成功: {self._status.summary()}")
                return True, self._status
            
            # 等待後重試
            time.sleep(self.retry_interval)
        
        # 超時或被中斷
        # 檢查最低需求（至少 CAN 必須成功）
        if self._status.can_ready:
            console.print("[yellow]⚠️  部分硬體未就緒，但 CAN Bus 可用，繼續啟動[/yellow]")
            return True, self._status
        
        return False, self._status
    
    def cleanup(self):
        """清理資源"""
        if self._can_bus:
            try:
                self._can_bus.shutdown()
            except:
                pass
            self._can_bus = None


def initialize_hardware(
    timeout: float = 60.0,
    require_gps: bool = False,  # GPS 通常不是必要的
    require_gpio: bool = False,  # GPIO 按鈕不是必要的（可以用鍵盤）
    show_progress: bool = True
) -> Tuple[bool, HardwareStatus, Optional[object]]:
    """
    便捷函數：初始化所有硬體
    
    Args:
        timeout: 超時時間（秒）
        require_gps: 是否需要 GPS
        require_gpio: 是否需要 GPIO
        show_progress: 是否顯示進度
    
    Returns:
        (success, status, can_bus):
            - success: 是否成功初始化（至少 CAN 需要成功）
            - status: 硬體狀態
            - can_bus: CAN Bus 實例（如果初始化成功）
    """
    initializer = HardwareInitializer(
        timeout=timeout,
        require_gps=require_gps,
        require_gpio=require_gpio
    )
    
    success, status = initializer.initialize(show_progress=show_progress)
    
    return success, status, initializer.can_bus


# === 測試程式 ===
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.DEBUG)
    
    print("=" * 50)
    print("硬體初始化測試")
    print(f"是否為 Raspberry Pi: {is_raspberry_pi()}")
    print("=" * 50)
    
    success, status, can_bus = initialize_hardware(
        timeout=30.0,
        require_gps=False,
        require_gpio=False,
        show_progress=True
    )
    
    print("\n" + "=" * 50)
    print("結果:")
    print(f"成功: {success}")
    print(f"狀態:\n{status.summary()}")
    print(f"CAN Bus: {can_bus}")
    print("=" * 50)
    
    # 清理
    if can_bus:
        can_bus.shutdown()
