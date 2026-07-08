"""MQTT 遙測控制器

從 main.py 的 Dashboard 拆出的 MQTT 連線與遙測上傳邏輯：
- 讀取 mqtt_config.json 並建立 paho MQTT 客戶端（背景執行緒 loop_forever 自動重連）
- 連線成功後在主執行緒啟動每 30 秒的遙測上傳 QTimer
- 收到導航訊息時透過 Signal 轉發回主執行緒

跨執行緒規則：paho callback 在網路執行緒執行，一律透過 pyqtSignal
回到主執行緒操作 QTimer / UI，不可直接呼叫。
"""

import os
import json
import time
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from core.utils import OdometerStorage


class MqttTelemetryController(QObject):
    """管理 MQTT 客戶端生命週期與車輛遙測上傳"""

    # paho 網路執行緒 -> 主執行緒：啟動 / 停止遙測上傳計時器
    signal_start_telemetry = pyqtSignal()
    signal_stop_telemetry = pyqtSignal()

    # paho 網路執行緒 -> 主執行緒：導航訊息
    signal_navigation_message = pyqtSignal(dict)

    def __init__(self, dashboard, config_path, parent=None):
        super().__init__(parent)
        self._dashboard = dashboard
        self._config_path = config_path

        self.client = None
        self.connected = False

        # 設定快取：初始化時讀一次，避免每次發布遙測都重新開檔 + json.load
        self._config = None
        self._publish_topic = 'car/telemetry'

        self._telemetry_timer = None

        # 連接跨執行緒 Signals 到主執行緒 Slots
        self.signal_start_telemetry.connect(self._start_telemetry_timer)
        self.signal_stop_telemetry.connect(self._stop_telemetry_timer)

    def get_cached_config(self):
        """取得初始化時快取的 MQTT 設定（可能為 None）"""
        return self._config

    def check_config(self):
        """檢查 MQTT 設定並自動連線"""
        if os.path.exists(self._config_path):
            print("[MQTT] 發現設定檔，嘗試自動連線...")
            self.init_client()
        else:
            print("[MQTT] 未發現設定檔，可從下拉面板進行設定")

    def init_client(self):
        """初始化 MQTT 客戶端（支援自動重連）"""
        if not os.path.exists(self._config_path):
            print("[MQTT] 設定檔不存在")
            return

        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            import paho.mqtt.client as mqtt

            # 快取設定，發布遙測時不再重新讀檔
            self._config = config
            self._publish_topic = config.get('publish_topic', 'car/telemetry')

            controller = self  # 保存 controller 參考供 callback 使用
            mqtt_publish_topic = self._publish_topic  # 上傳用的主題

            def on_connect(client, userdata, flags, rc, properties=None):
                if rc == 0:
                    controller.connected = True
                    print(f"[MQTT] ✅ 已連接到 {config['broker']}:{config['port']}")
                    # 訂閱主題
                    topic = config.get('topic', 'car/#')
                    client.subscribe(topic)
                    print(f"[MQTT] 已訂閱主題: {topic}")
                    print(f"[MQTT] 發布主題: {mqtt_publish_topic}")
                    # 透過 Signal 在主執行緒啟動數據上傳計時器
                    controller.signal_start_telemetry.emit()
                else:
                    controller.connected = False
                    print(f"[MQTT] ❌ 連線失敗，錯誤碼: {rc}")

            def on_disconnect(client, userdata, rc, properties=None, reason_code=None):
                controller.connected = False
                # 透過 Signal 回主執行緒停止遙測上傳計時器
                # （paho 網路執行緒不可直接操作 QTimer）
                controller.signal_stop_telemetry.emit()
                if rc != 0:
                    print(f"[MQTT] ⚠️ 意外斷線 (rc={rc})，將自動重連...")
                else:
                    print("[MQTT] 已斷線")

            def on_message(client, userdata, msg):
                try:
                    payload = msg.payload.decode('utf-8')
                    data = json.loads(payload)
                    print(f"[MQTT] 收到訊息: {msg.topic} -> {payload[:100]}...")

                    # 處理導航訊息 - 使用 Signal 確保在主執行緒更新 UI
                    if 'navigation' in msg.topic or 'nav' in msg.topic:
                        # 透過 Signal 傳遞資料到主執行緒
                        controller.signal_navigation_message.emit(data)

                except Exception as e:
                    print(f"[MQTT] 處理訊息錯誤: {e}")

            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            self.client.on_connect = on_connect
            self.client.on_disconnect = on_disconnect
            self.client.on_message = on_message

            # 啟用自動重連，指數退避（1秒起，最大 5 秒）
            self.client.reconnect_delay_set(min_delay=1, max_delay=5)

            # 設定認證
            username = config.get('username', '').strip()
            password = config.get('password', '').strip()
            if username:
                self.client.username_pw_set(username, password)

            # 在背景執行緒中連線
            mqtt_client = self.client

            def connect_mqtt():
                try:
                    mqtt_client.connect(config['broker'], config['port'], keepalive=60)
                    # 使用 loop_forever 會自動處理重連
                    mqtt_client.loop_forever(retry_first_connection=True)
                except Exception as e:
                    print(f"[MQTT] 連線錯誤: {e}")
                    controller.connected = False

            mqtt_thread = threading.Thread(target=connect_mqtt, daemon=True)
            mqtt_thread.start()

        except ImportError:
            print("[MQTT] paho-mqtt 未安裝")
        except Exception as e:
            print(f"[MQTT] 初始化失敗: {e}")

    def reconnect(self):
        """重新連接 MQTT"""
        # 先清理舊的連線
        self.stop()

        # 重新初始化
        self.init_client()

    def stop(self):
        """停止遙測 timer 並關閉 MQTT client。"""
        self._stop_telemetry_timer()
        if self.client is not None:
            try:
                self.client.disconnect()
                self.client.loop_stop()
            except Exception:
                pass
            self.client = None
        self.connected = False

    @pyqtSlot()
    def _start_telemetry_timer(self):
        """啟動 MQTT 車輛數據上傳計時器（主執行緒）"""
        if self._telemetry_timer is not None:
            self._telemetry_timer.stop()

        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.timeout.connect(self.publish_telemetry)
        self._telemetry_timer.start(30000)  # 每 30 秒上傳一次
        print("[MQTT] 車輛數據上傳已啟動 (每 30 秒)")

    @pyqtSlot()
    def _stop_telemetry_timer(self):
        """停止遙測上傳計時器（主執行緒）"""
        if self._telemetry_timer is not None:
            self._telemetry_timer.stop()
            print("[MQTT] 遙測上傳已暫停")

    def publish_telemetry(self):
        """發布車輛遙測數據到 MQTT（主執行緒，讀取 dashboard 狀態）"""
        if not self.connected or self.client is None:
            return

        dashboard = self._dashboard

        try:
            # 取得 ODO 和 Trip 資料
            storage = OdometerStorage()
            odo_total = storage.get_odo()
            trip1_distance, _ = storage.get_trip1()
            trip2_distance, _ = storage.get_trip2()

            # 取得門狀態 (開門 = "on", 關門 = "off")
            door_status = {}
            if hasattr(dashboard, 'door_card'):
                door_status = {
                    'FL': 'off' if dashboard.door_card.door_fl_closed else 'on',
                    'FR': 'off' if dashboard.door_card.door_fr_closed else 'on',
                    'RL': 'off' if dashboard.door_card.door_rl_closed else 'on',
                    'RR': 'off' if dashboard.door_card.door_rr_closed else 'on',
                    'BK': 'off' if dashboard.door_card.door_bk_closed else 'on'
                }

            # 水溫轉換：dashboard.temp 是百分比 (0-100)，轉換為攝氏度 (40-120°C)
            coolant_celsius = 40 + (dashboard.temp / 100) * 80 if dashboard.temp is not None else None

            # 計算引擎狀態 (status)
            # 電壓從 10 以上掉到 0 時，status 優先變成 false（熄火）
            # RPM > 100 時，status 變成 true（引擎運轉）
            status_fell, current_rpm = dashboard._update_engine_status()

            # 組裝數據
            telemetry = {
                'timestamp': time.time(),
                'status': dashboard._engine_status,
                'speed': int(dashboard.speed),  # 與儀表顯示一致，使用整數
                'rpm': current_rpm,  # 使用已計算的整數 RPM
                'coolant_temp': coolant_celsius,
                'fuel': dashboard.fuel,
                'gear': dashboard.gear,
                'turbo': dashboard.turbo,
                'battery': dashboard.battery,
                'odo': odo_total,
                'trip_a': trip1_distance,
                'trip_b': trip2_distance,
                'gps': {
                    'lat': dashboard.gps_lat,
                    'lon': dashboard.gps_lon,
                    'fixed': getattr(dashboard, 'is_gps_fixed', False)
                },
                'doors': door_status,
                'cruise': {
                    'switch': dashboard.cruise_switch,
                    'engaged': dashboard.cruise_engaged
                },
                'parking_brake': dashboard.parking_brake
            }

            # 發布主題使用初始化時快取的設定（不再每次重新讀檔）
            # 發布數據 (retain=True 讓新訂閱者能收到最後一筆訊息)
            payload = json.dumps(telemetry, ensure_ascii=False)
            self.client.publish(self._publish_topic, payload, qos=0, retain=True)

        except Exception as e:
            print(f"[MQTT] 發布遙測數據錯誤: {e}")
