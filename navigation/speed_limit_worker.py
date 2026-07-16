"""
速限查詢背景 worker

把 CSV 首次載入（~4.4MB big5 解析）與週期性查詢移出 Qt 主執行緒。
查詢請求會合併（coalesce）：worker 忙碌時只保留最新一筆座標，
不會堆積過時的查詢。

結果透過 Qt signal 回到主執行緒（與 datagrab.WorkerSignals 相同模式）。
"""
import logging
import threading

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class SpeedLimitWorker(QObject):
    """常駐背景執行緒，序列化執行速限查詢"""

    # (速限值, 方向, 雙向速限dict) — 與 query_speed_limit 回傳值一致
    result_ready = pyqtSignal(object, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cond = threading.Condition()
        self._pending = None
        self._stop = False
        self._thread = threading.Thread(
            target=self._run, name="SpeedLimitWorker", daemon=True
        )

    def start(self):
        self._thread.start()

    def request(self, lat, lon, bearing=None):
        """提交查詢（執行緒安全）。連續呼叫只保留最新一筆。"""
        with self._cond:
            self._pending = (lat, lon, bearing)
            self._cond.notify()

    def stop(self, timeout=2.0):
        with self._cond:
            self._stop = True
            self._cond.notify()
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)
        return not self._thread.is_alive()

    def _run(self):
        # 延遲到 worker 執行緒才載入，避免 CSV 解析阻塞主執行緒
        from navigation.speed_limit import get_speed_limit_loader
        try:
            loader = get_speed_limit_loader()
        except Exception:
            logger.exception("[SpeedLimit] 載入速限資料失敗，worker 結束")
            return

        while True:
            with self._cond:
                while self._pending is None and not self._stop:
                    self._cond.wait()
                if self._stop:
                    return
                lat, lon, bearing = self._pending
                self._pending = None

            try:
                limit, direction, dual_limits = loader.query(lat, lon, bearing)
            except Exception:
                logger.exception("[SpeedLimit] 查詢失敗")
                continue

            self.result_ready.emit(limit, direction, dual_limits)
