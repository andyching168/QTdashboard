"""熄火 MQTT 協調器

從 main.py 的 Dashboard 拆出的關機/電源相關非 UI 職責：
- 關機監控器 (ShutdownMonitor) 的 signal 接線與啟動
- 熄火 / 效能 MQTT event 的組裝與 retained 發布（失敗留在本地待補送）

UI 動作（行程總結卡片、關機對話框、toast）仍由 Dashboard 的 slot 處理；
本協調器只負責事件建立、pending 儲存與背景執行緒發布。
"""

import os
import json
import time
import threading

from PyQt6.QtCore import QObject

from core.shutdown_monitor import get_shutdown_monitor
from core.shutdown_mqtt import (
    build_shutdown_event,
    build_performance_event,
    publish_pending_then_current,
    upsert_pending_event,
)
from core.utils import PerformanceMonitor, system_resource_snapshot


class ShutdownMqttCoordinator(QObject):
    """協調關機監控器接線與熄火 MQTT event 發布"""

    def __init__(self, dashboard, mqtt_controller, config_path, parent=None):
        super().__init__(parent)
        self._dashboard = dashboard
        self._mqtt_controller = mqtt_controller
        self._config_path = config_path
        self._publish_in_progress = False

    def attach_monitor(self):
        """初始化關機監控器並接線到 Dashboard 的 UI slots

        Returns:
            ShutdownMonitor: 已接線並啟動無訊號監控的監控器實例
        """
        dashboard = self._dashboard
        monitor = get_shutdown_monitor()

        # 連接信號
        monitor.power_lost.connect(dashboard._on_power_lost)
        monitor.power_restored.connect(dashboard._on_power_restored)

        # 連接無電壓訊號超時信號（3 分鐘沒收到 OBD 電壓數據）
        monitor.no_signal_timeout.connect(dashboard._on_no_voltage_signal_timeout)
        monitor.telegram_notification_finished.connect(dashboard._on_telegram_notification_finished)
        monitor.shutdown_cancelled.connect(dashboard._hide_shutdown_summary_card)

        # 連接轉速信號到關機監控器（用於判斷是否低於 300 RPM）
        dashboard.signal_update_rpm.connect(lambda rpm: monitor.update_rpm(rpm * 1000))

        # 啟動無訊號監控
        monitor.start_no_signal_monitoring()

        print("[ShutdownMonitor] 關機監控器已初始化（含無訊號超時監控）")
        return monitor

    # === 熄火 MQTT event ===

    def build_shutdown_mqtt_event(self):
        """建立熄火 MQTT event。"""
        dashboard = self._dashboard
        trip_info = {}
        if hasattr(dashboard, "trip_info_card") and hasattr(dashboard.trip_info_card, "get_trip_info"):
            try:
                trip_info = dashboard.trip_info_card.get_trip_info()
            except Exception as e:
                print(f"[ShutdownMQTT] 讀取行程資訊失敗: {e}")

        return build_shutdown_event(
            lat=dashboard.gps_lat,
            lon=dashboard.gps_lon,
            location_fixed=getattr(dashboard, "is_gps_fixed", False),
            elapsed_time=trip_info.get("elapsed_time"),
            trip_distance=trip_info.get("trip_distance"),
            avg_fuel=trip_info.get("avg_fuel"),
        )

    def build_performance_mqtt_event(self, shutdown_event):
        """建立熄火當下的效能 MQTT event，並保留對應 shutdown event_id。"""
        dashboard = self._dashboard
        system_snapshot = system_resource_snapshot()
        system_snapshot["uptime_sec"] = round(time.time() - dashboard._dashboard_started_at, 1)

        perf_snapshot = PerformanceMonitor().snapshot()
        jank_detector = getattr(dashboard, "jank_detector", None)
        if jank_detector is not None:
            jank_snapshot = jank_detector.snapshot()
        else:
            jank_snapshot = {"enabled": False, "count": 0, "recent": []}

        return build_performance_event(
            shutdown_event,
            system_snapshot=system_snapshot,
            performance_snapshot=perf_snapshot,
            jank_snapshot=jank_snapshot,
        )

    def publish(self):
        """熄火時送出 retained MQTT event；失敗會留在本地待下次補送。"""
        dashboard = self._dashboard

        if self._publish_in_progress:
            print("[ShutdownMQTT] 發送中，略過重複請求")
            return

        event = self.build_shutdown_mqtt_event()
        performance_event = self.build_performance_mqtt_event(event)
        upsert_pending_event(event)
        upsert_pending_event(performance_event)

        if not os.path.exists(self._config_path):
            print("[ShutdownMQTT] 未設定 MQTT，已先儲存熄火紀錄")
            dashboard.show_toast("MQTT 尚未設定，熄火紀錄已先儲存", "warning", 4500)
            return

        if self._mqtt_controller.client is None or not self._mqtt_controller.connected:
            print("[ShutdownMQTT] MQTT 尚未連線，已先儲存熄火紀錄")
            dashboard.show_toast("MQTT 尚未連線，熄火紀錄已先儲存", "warning", 4500)
            return

        self._publish_in_progress = True

        def _worker():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                result = publish_pending_then_current(self._mqtt_controller.client, config, event)
                sent_count = result.get("sent_count", 0)
                remaining_count = result.get("remaining_count", 0)
                sent_ids = result.get("sent_ids") or []
                performance_sent = performance_event.get("event_id") in sent_ids

                if result.get("current_sent"):
                    if sent_count > 1:
                        dashboard.show_toast(f"已補送 {sent_count - 1} 筆紀錄，並送出本次熄火紀錄", "success", 4500)
                    else:
                        dashboard.show_toast("本次熄火紀錄已送出", "success", 3500)
                else:
                    dashboard.show_toast("MQTT 傳送失敗，熄火紀錄已先儲存", "warning", 4500)

                if remaining_count:
                    print(f"[ShutdownMQTT] 尚有 {remaining_count} 筆 pending 未送出")
                if not performance_sent:
                    print("[ShutdownMQTT] 效能快照尚未送出，已保留 pending")
            except Exception as e:
                print(f"[ShutdownMQTT] 發送錯誤: {e}")
                dashboard.show_toast("MQTT 傳送失敗，熄火紀錄已先儲存", "warning", 4500)
            finally:
                self._publish_in_progress = False

        threading.Thread(target=_worker, daemon=True).start()
