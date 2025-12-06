#!/usr/bin/env python3
"""
最大值記錄器 - 記錄每次執行時的最大 RPM 和水溫

功能：
- 追蹤執行期間的最大 RPM 和水溫
- 程式結束時儲存到 log/ 資料夾
- 最多保留 5 筆記錄（自動刪除最舊的）
"""

import os
import json
from datetime import datetime
from pathlib import Path


class MaxValueLogger:
    """最大值記錄器"""
    
    _instance = None
    
    def __new__(cls):
        """單例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # 最大值追蹤
        self.max_rpm = 0.0
        self.max_coolant = 0.0
        
        # 記錄開始時間
        self.start_time = datetime.now()
        
        # Log 資料夾路徑
        self.log_dir = Path(__file__).parent / "log"
        self.max_files = 5  # 最多保留 5 筆
        
        # 確保 log 資料夾存在
        self.log_dir.mkdir(exist_ok=True)
        
        print(f"[MaxValueLogger] 初始化完成，log 目錄: {self.log_dir}")
    
    def update_rpm(self, rpm: float):
        """更新 RPM 最大值
        
        Args:
            rpm: 當前 RPM 值（注意：Dashboard 內部使用 x1000，這裡直接接收原始值）
        """
        if rpm > self.max_rpm:
            self.max_rpm = rpm
    
    def update_coolant(self, temp: float):
        """更新水溫最大值
        
        Args:
            temp: 當前水溫（°C）
        """
        if temp > self.max_coolant:
            self.max_coolant = temp
    
    def save(self):
        """儲存最大值到檔案
        
        檔案格式：log/max_YYYYMMDD_HHMMSS.txt
        """
        # 如果沒有有效資料，不儲存
        if self.max_rpm <= 0 and self.max_coolant <= 0:
            print("[MaxValueLogger] 無有效資料，跳過儲存")
            return
        
        # 產生檔名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"max_{timestamp}.txt"
        filepath = self.log_dir / filename
        
        # 計算執行時間
        duration = datetime.now() - self.start_time
        duration_str = str(duration).split('.')[0]  # 移除微秒
        
        # 儲存資料
        content = f"""========================================
  儀表板最大值記錄
========================================
記錄時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
執行時長: {duration_str}
----------------------------------------
最大 RPM:    {self.max_rpm:.0f} RPM
最大水溫:   {self.max_coolant:.1f} °C
========================================
"""
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[MaxValueLogger] 已儲存最大值記錄: {filepath}")
            print(f"[MaxValueLogger] 最大 RPM: {self.max_rpm:.0f}, 最大水溫: {self.max_coolant:.1f}°C")
            
            # 清理舊檔案
            self._cleanup_old_files()
            
        except Exception as e:
            print(f"[MaxValueLogger] 儲存失敗: {e}")
    
    def _cleanup_old_files(self):
        """清理舊檔案，只保留最新的 N 筆"""
        try:
            # 取得所有 max_*.txt 檔案
            files = sorted(self.log_dir.glob("max_*.txt"), reverse=True)
            
            # 刪除超過數量限制的舊檔案
            for old_file in files[self.max_files:]:
                old_file.unlink()
                print(f"[MaxValueLogger] 已刪除舊記錄: {old_file.name}")
                
        except Exception as e:
            print(f"[MaxValueLogger] 清理舊檔案失敗: {e}")
    
    def get_stats(self) -> dict:
        """取得當前統計資料
        
        Returns:
            dict: 包含 max_rpm 和 max_coolant 的字典
        """
        return {
            "max_rpm": self.max_rpm,
            "max_coolant": self.max_coolant,
            "start_time": self.start_time.isoformat(),
        }


def get_max_value_logger() -> MaxValueLogger:
    """取得 MaxValueLogger 單例"""
    return MaxValueLogger()


# 測試用
if __name__ == "__main__":
    logger = get_max_value_logger()
    
    # 模擬資料更新
    logger.update_rpm(3500)
    logger.update_rpm(5200)
    logger.update_rpm(4800)
    logger.update_coolant(85)
    logger.update_coolant(92)
    logger.update_coolant(88)
    
    print(f"統計: {logger.get_stats()}")
    
    # 儲存
    logger.save()
