import json
import os
import re
import sqlite3
import uuid
from datetime import datetime


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "dashboard_history.db")
LEGACY_PENDING_FILE = os.path.join(PROJECT_ROOT, "shutdown_mqtt_pending.json")
DEFAULT_SHUTDOWN_TOPIC_BASE = "car/shutdown"


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def make_event_id(event_time=None):
    event_time = event_time or now_iso()
    safe_time = re.sub(r"[^0-9A-Za-z]+", "-", event_time).strip("-")
    return f"engine-off-{safe_time}-{uuid.uuid4().hex[:8]}"


def _connect(db_path=DB_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=DB_PATH):
    with _connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shutdown_events (
                event_id TEXT PRIMARY KEY,
                event_time TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT,
                lat REAL,
                lon REAL,
                location_fixed INTEGER NOT NULL DEFAULT 0,
                elapsed_time TEXT,
                distance_km REAL,
                avg_fuel_l_100km REAL,
                payload_json TEXT NOT NULL,
                mqtt_sent INTEGER NOT NULL DEFAULT 0,
                mqtt_sent_at TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_shutdown_events_mqtt_sent
            ON shutdown_events (mqtt_sent, event_time)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_shutdown_events_avg_fuel
            ON shutdown_events (avg_fuel_l_100km)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_shutdown_events_distance
            ON shutdown_events (distance_km)
        """)


def _event_to_row(event):
    location = event.get("location") or {}
    trip = event.get("trip") or {}
    return {
        "event_id": event.get("event_id"),
        "event_time": event.get("event_time") or now_iso(),
        "updated_at": event.get("updated_at") or now_iso(),
        "source": event.get("source"),
        "lat": location.get("lat"),
        "lon": location.get("lon"),
        "location_fixed": 1 if location.get("fixed") else 0,
        "elapsed_time": trip.get("elapsed_time"),
        "distance_km": trip.get("distance_km"),
        "avg_fuel_l_100km": trip.get("avg_fuel_l_100km"),
        "payload_json": json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        "created_at": now_iso(),
    }


def _row_to_event(row):
    try:
        event = json.loads(row["payload_json"])
    except Exception:
        event = {}

    event["event_id"] = row["event_id"]
    event["event_time"] = row["event_time"]
    event["updated_at"] = row["updated_at"]
    event["source"] = row["source"]
    event["location"] = {
        "lat": row["lat"],
        "lon": row["lon"],
        "fixed": bool(row["location_fixed"]),
    }
    event["trip"] = {
        "elapsed_time": row["elapsed_time"],
        "distance_km": row["distance_km"],
        "avg_fuel_l_100km": row["avg_fuel_l_100km"],
    }
    return event


def save_shutdown_event(event, db_path=DB_PATH):
    init_db(db_path)
    row = _event_to_row(event)
    with _connect(db_path) as conn:
        conn.execute("""
            INSERT INTO shutdown_events (
                event_id, event_time, updated_at, source, lat, lon, location_fixed,
                elapsed_time, distance_km, avg_fuel_l_100km, payload_json,
                mqtt_sent, mqtt_sent_at, created_at
            )
            VALUES (
                :event_id, :event_time, :updated_at, :source, :lat, :lon, :location_fixed,
                :elapsed_time, :distance_km, :avg_fuel_l_100km, :payload_json,
                0, NULL, :created_at
            )
            ON CONFLICT(event_id) DO UPDATE SET
                updated_at=excluded.updated_at,
                source=excluded.source,
                lat=excluded.lat,
                lon=excluded.lon,
                location_fixed=excluded.location_fixed,
                elapsed_time=excluded.elapsed_time,
                distance_km=excluded.distance_km,
                avg_fuel_l_100km=excluded.avg_fuel_l_100km,
                payload_json=excluded.payload_json
        """, row)


def upsert_pending_event(event, db_path=DB_PATH):
    save_shutdown_event(event, db_path)
    return get_unsent_events(db_path)


def get_unsent_events(db_path=DB_PATH, limit=100):
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("""
            SELECT * FROM shutdown_events
            WHERE mqtt_sent = 0
            ORDER BY event_time ASC
            LIMIT ?
        """, (limit,)).fetchall()
    return [_row_to_event(row) for row in rows]


def mark_events_sent(event_ids, db_path=DB_PATH):
    event_ids = [event_id for event_id in event_ids if event_id]
    if not event_ids:
        return
    init_db(db_path)
    sent_at = now_iso()
    placeholders = ",".join("?" for _ in event_ids)
    with _connect(db_path) as conn:
        conn.execute(
            f"""
            UPDATE shutdown_events
            SET mqtt_sent = 1, mqtt_sent_at = ?
            WHERE event_id IN ({placeholders})
            """,
            [sent_at, *event_ids],
        )


def count_unsent_events(db_path=DB_PATH):
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM shutdown_events WHERE mqtt_sent = 0").fetchone()
    return int(row["count"]) if row else 0


def get_best_fuel_events(db_path=DB_PATH, min_distance_km=3.0, limit=10):
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("""
            SELECT * FROM shutdown_events
            WHERE distance_km >= ?
              AND avg_fuel_l_100km IS NOT NULL
              AND avg_fuel_l_100km > 0
            ORDER BY avg_fuel_l_100km ASC, distance_km DESC
            LIMIT ?
        """, (min_distance_km, limit)).fetchall()
    return [_row_to_event(row) for row in rows]


def migrate_legacy_pending(db_path=DB_PATH, legacy_path=LEGACY_PENDING_FILE):
    if not os.path.exists(legacy_path):
        return 0

    try:
        with open(legacy_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ShutdownMQTT] 舊 pending 讀取失敗: {e}")
        return 0

    if not isinstance(data, list):
        return 0

    migrated = 0
    for event in data:
        if isinstance(event, dict) and event.get("event_id"):
            save_shutdown_event(event, db_path)
            migrated += 1

    if migrated:
        backup_path = f"{legacy_path}.migrated"
        try:
            os.replace(legacy_path, backup_path)
            print(f"[ShutdownMQTT] 已匯入 {migrated} 筆舊 pending，原檔移到 {backup_path}")
        except Exception as e:
            print(f"[ShutdownMQTT] 舊 pending 匯入完成，但移動原檔失敗: {e}")

    return migrated


def get_shutdown_topic_base(config):
    return str(config.get("shutdown_topic") or DEFAULT_SHUTDOWN_TOPIC_BASE).strip().rstrip("/")


def event_topics(config, event_id):
    base = get_shutdown_topic_base(config)
    return [
        f"{base}/events/{event_id}",
        f"{base}/latest",
    ]


def build_shutdown_event(
    lat=None,
    lon=None,
    location_fixed=False,
    elapsed_time=None,
    trip_distance=None,
    avg_fuel=None,
    source="dashboard",
):
    event_time = now_iso()
    event_id = make_event_id(event_time)

    return {
        "event_id": event_id,
        "type": "engine_off",
        "event_time": event_time,
        "updated_at": event_time,
        "source": source,
        "location": {
            "lat": lat,
            "lon": lon,
            "fixed": bool(location_fixed),
        },
        "trip": {
            "elapsed_time": elapsed_time,
            "distance_km": round(float(trip_distance), 2) if trip_distance is not None else None,
            "avg_fuel_l_100km": round(float(avg_fuel), 2) if avg_fuel is not None else None,
        },
    }


def _publish_one(client, config, event, timeout=5):
    payload_event = dict(event)
    payload_event["updated_at"] = now_iso()
    payload = json.dumps(payload_event, ensure_ascii=False, separators=(",", ":"))

    for topic in event_topics(config, payload_event["event_id"]):
        info = client.publish(topic, payload, qos=1, retain=True)
        if hasattr(info, "wait_for_publish"):
            info.wait_for_publish(timeout=timeout)
        if hasattr(info, "is_published") and not info.is_published():
            return False
        if getattr(info, "rc", 0) != 0:
            return False

    return True


def publish_pending_then_current(client, config, current_event, db_path=DB_PATH):
    migrate_legacy_pending(db_path)
    save_shutdown_event(current_event, db_path)

    sent_ids = []
    pending = get_unsent_events(db_path)

    for event in pending:
        if _publish_one(client, config, event):
            sent_ids.append(event.get("event_id"))
        else:
            break

    mark_events_sent(sent_ids, db_path)
    remaining_count = count_unsent_events(db_path)
    current_sent = current_event.get("event_id") in sent_ids

    return {
        "success": current_sent and remaining_count == 0,
        "sent_count": len(sent_ids),
        "remaining_count": remaining_count,
        "current_sent": current_sent,
    }
