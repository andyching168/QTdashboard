"""
QTdashboard 主題系統

提供中央化的顏色定義和主題管理機制。
"""

from typing import Optional
from dataclasses import dataclass
from PyQt6.QtGui import QColor
from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class ThemeColors:
    """所有 UI 顏色定義"""
    # 主要顏色
    PRIMARY = "#6af"           # 藍色（主要強調色）
    SUCCESS = "#4ade80"        # 綠色（安全/正常/巡航）
    DANGER = "#ef4444"        # 紅色（危險/錯誤/超速）
    WARNING = "#facc15"       # 黃色（警告/外部GPS）
    ORANGE = "#fa0"           # 橙色（警告）
    
    # 狀態指示燈
    LAMP_ON = "#4ade80"       # 指示燈亮
    LAMP_OFF = "#333333"      # 指示燈滅
    
    # 按鈕顏色
    BTN_WIFI = "#1DB954"
    BTN_TIME = "#4285F4"
    BTN_BRIGHTNESS = "#FF9800"
    BTN_UPDATE = "#00BCD4"
    BTN_POWER = "#E91E63"
    BTN_SETTINGS = "#9C27B0"
    
    # 速度同步模式
    SPEED_CALIBRATED = "#4CAF50"
    SPEED_FIXED = "#FF9800"
    SPEED_GPS = "#2196F3"
    
    # 文字顏色
    TEXT_PRIMARY = "#ffffff"   # 主要文字（白色）
    TEXT_SECONDARY = "#888888" # 次要文字（灰色）
    TEXT_DISABLED = "#444444"  # 禁用文字
    
    # 背景顏色
    BG_DARK = "#0a0a0f"       # 主背景（深黑）
    BG_CARD = "#1a1a25"       # 卡片背景（深灰紫）
    BG_CARD_ALT = "#2a2a35"   # 卡片背景交替色
    BG_INPUT = "#15151a"      # 輸入框背景
    BG_STATUS_BAR = "#1a1a1f" # 狀態列背景
    
    # 邊框
    BORDER_DEFAULT = "#2a2a35"
    BORDER_HOVER = "#3a3a45"
    BORDER_ACTIVE = "#4a4a55"
    
    # 特殊元件
    GAUGE_BG = "#101015"      # 儀表背景
    NEEDLE = "#ff6b6b"        # 指針顏色
    TICK = "#4a5568"          # 刻度線
    TICK_MAJOR = "#6a7588"    # 主刻度
    
    # 手煞車/引擎
    PARKING_BRAKE = "#f66"
    ENGINE_RUNNING = "#4ade80"
    ENGINE_OFF = "#666666"
    
    # GPS 狀態
    GPS_INTERNAL = "#4ade80"  # 內部GPS（綠色）
    GPS_EXTERNAL_FRESH = "#facc15"  # 外部GPS即時（黃色）
    GPS_EXTERNAL_STALE = "#888888"  # 外部GPS過時（灰色）
    GPS_NOT_FOUND = "#ef4444" # GPS未找到（紅色）
    
    # 方向燈
    TURN_SIGNAL_BRIGHT = "#b1ff00"  # 方向燈亮（黃綠）
    TURN_SIGNAL_DIM = "#0a0a0a"     # 方向燈暗
    
    # 速限
    SPEED_LIMIT_BORDER = "#ef4444"  # 速限邊框
    SPEED_LIMIT_BG = "#ffffff"      # 速限背景
    SPEED_LIMIT_TEXT = "#000000"    # 速限文字


class ThemeManager(QObject):
    """主題管理器"""
    
    theme_changed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._current_theme = "dark"
        self._colors = ThemeColors()
        
    @property
    def colors(self) -> ThemeColors:
        return self._colors
    
    @property
    def current_theme(self) -> str:
        return self._current_theme
    
    def set_theme(self, theme_name: str):
        """設定主題（目前只支援 dark）"""
        if theme_name != "dark":
            print(f"[Theme] 主題 '{theme_name}' 尚未實作，目前只支援 dark")
            return
        self._current_theme = theme_name
        self.theme_changed.emit(theme_name)
        print(f"[Theme] 主題切換為: {theme_name}")
    
    def adjust_color(self, hex_color: str, factor: float) -> str:
        """調整顏色亮度
        
        Args:
            hex_color: 6位 hex 顏色字串（如 "#6af"）
            factor: 亮度因子（>1 變亮，<1 變暗）
        
        Returns:
            調整後的 hex 顏色字串
        """
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            return hex_color
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        r = min(255, max(0, int(r * factor)))
        g = min(255, max(0, int(g * factor)))
        b = min(255, max(0, int(b * factor)))
        return f'#{r:02x}{g:02x}{b:02x}'
    
    def get_gradient(self, color1: str, color2: str, stop: float = 0.5) -> str:
        """產生兩色漸層字串"""
        return f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {color1}, stop:{stop} {color2})"
    
    def darken(self, hex_color: str, amount: float = 0.8) -> str:
        """變暗"""
        return self.adjust_color(hex_color, amount)
    
    def lighten(self, hex_color: str, amount: float = 1.2) -> str:
        """變亮"""
        return self.adjust_color(hex_color, amount)


# 全域主題管理器實例
_theme_manager: Optional[ThemeManager] = None

def get_theme_manager() -> ThemeManager:
    """取得全域主題管理器"""
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager

def T(key: str) -> str:
    """快速取得主題顏色
    
    Args:
        key: ThemeColors 屬性名
    
    Returns:
        顏色 hex 字串
    """
    return getattr(ThemeColors, key, "#ff00ff")
