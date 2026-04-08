"""
QTdashboard 主題系統

提供中央化的顏色定義和主題管理機制。
"""

import os
import json
from typing import Optional, Dict
from dataclasses import dataclass
from PyQt6.QtGui import QColor
from PyQt6.QtCore import QObject, pyqtSignal


ACCENT_COLOR_PRESETS: Dict[str, str] = {
    "藍色（預設）": "#6af",
    "紫色": "#9b6aff",
    "粉色": "#f6a",
    "紅色": "#f55",
    "橙色": "#fa5",
    "金色": "#fa0",
    "綠色": "#5f8",
    "青色": "#0fc",
    "天藍色": "#0af",
}


@dataclass
class ThemeColors:
    """所有 UI 顏色定義"""
    PRIMARY: str = "#6af"
    SUCCESS: str = "#4ade80"
    DANGER: str = "#ef4444"
    WARNING: str = "#facc15"
    ORANGE: str = "#fa0"
    
    LAMP_ON: str = "#4ade80"
    LAMP_OFF: str = "#333333"
    
    BTN_WIFI: str = "#1DB954"
    BTN_TIME: str = "#4285F4"
    BTN_BRIGHTNESS: str = "#FF9800"
    BTN_UPDATE: str = "#00BCD4"
    BTN_POWER: str = "#E91E63"
    BTN_SETTINGS: str = "#9C27B0"
    
    SPEED_CALIBRATED: str = "#4CAF50"
    SPEED_FIXED: str = "#FF9800"
    SPEED_GPS: str = "#2196F3"
    
    TEXT_PRIMARY: str = "#ffffff"
    TEXT_SECONDARY: str = "#888888"
    TEXT_DISABLED: str = "#444444"
    
    BG_DARK: str = "#0a0a0f"
    BG_CARD: str = "#1a1a25"
    BG_CARD_ALT: str = "#2a2a35"
    BG_INPUT: str = "#15151a"
    BG_STATUS_BAR: str = "#1a1a1f"
    
    BORDER_DEFAULT: str = "#2a2a35"
    BORDER_HOVER: str = "#3a3a45"
    BORDER_ACTIVE: str = "#4a4a55"
    
    GAUGE_BG: str = "#101015"
    NEEDLE: str = "#ff6b6b"
    TICK: str = "#4a5568"
    TICK_MAJOR: str = "#6a7588"
    
    PARKING_BRAKE: str = "#f66"
    ENGINE_RUNNING: str = "#4ade80"
    ENGINE_OFF: str = "#666666"
    
    GPS_INTERNAL: str = "#4ade80"
    GPS_EXTERNAL_FRESH: str = "#facc15"
    GPS_EXTERNAL_STALE: str = "#888888"
    GPS_NOT_FOUND: str = "#ef4444"
    
    TURN_SIGNAL_BRIGHT: str = "#b1ff00"
    TURN_SIGNAL_DIM: str = "#0a0a0a"
    
    SPEED_LIMIT_BORDER: str = "#ef4444"
    SPEED_LIMIT_BG: str = "#ffffff"
    SPEED_LIMIT_TEXT: str = "#000000"


def _get_config_dir() -> str:
    """取得設定檔目錄"""
    config_dir = os.path.join(os.path.expanduser("~"), ".config", "qtdashboard")
    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)
    return config_dir


def _get_accent_color_config_path() -> str:
    """取得強調色設定檔路徑"""
    return os.path.join(_get_config_dir(), "accent_color.json")


class ThemeManager(QObject):
    """主題管理器"""
    
    theme_changed = pyqtSignal(str)
    accent_color_changed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._current_theme = "dark"
        self._colors = ThemeColors()
        self._accent_color_overrides: Dict[str, str] = {}
        self._load_accent_color()
        
    def _load_accent_color(self):
        """從設定檔載入強調色"""
        config_path = _get_accent_color_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    accent = data.get('primary', '#6af')
                    self._accent_color_overrides['PRIMARY'] = accent
                    print(f"[Theme] 已載入強調色: {accent}")
            except Exception as e:
                print(f"[Theme] 載入強調色失敗: {e}")
                self._accent_color_overrides['PRIMARY'] = '#6af'
        else:
            self._accent_color_overrides['PRIMARY'] = '#6af'
    
    def _save_accent_color(self, color_hex: str):
        """儲存強調色到設定檔"""
        config_path = _get_accent_color_config_path()
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump({'primary': color_hex}, f, indent=2)
            print(f"[Theme] 已儲存強調色: {color_hex}")
        except Exception as e:
            print(f"[Theme] 儲存強調色失敗: {e}")
    
    @property
    def colors(self) -> ThemeColors:
        return self._colors
    
    @property
    def current_theme(self) -> str:
        return self._current_theme
    
    @property
    def accent_color(self) -> str:
        """取得目前強調色"""
        return self._accent_color_overrides.get('PRIMARY', '#6af')
    
    def set_accent_color(self, color_hex: str):
        """設定強調色"""
        self._accent_color_overrides['PRIMARY'] = color_hex
        self._save_accent_color(color_hex)
        self.accent_color_changed.emit(color_hex)
        print(f"[Theme] 強調色已更改為: {color_hex}")
    
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
    manager = get_theme_manager()
    if key in manager._accent_color_overrides:
        return manager._accent_color_overrides[key]
    return getattr(ThemeColors, key, "#ff00ff")


def reapply_t_function(stylesheet: str) -> str:
    """重新評估 stylesheet 字串中的 T() 調用
    
    將 {T('COLOR_NAME')} 模式替換為實際的 T() 返回值
    """
    import re
    
    pattern = r"\{T\('([^']+)'\)\}"
    
    def replace_t(match):
        color_key = match.group(1)
        return T(color_key)
    
    return re.sub(pattern, replace_t, stylesheet)
