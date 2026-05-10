import json
import os
import re
import uuid
from datetime import datetime


DEFAULT_SHUTDOWN_TOPIC_BASE = "car/shutdown"
PENDING_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shutdown_mqtt_pending.json")


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def make_event_id(event_time=None):
    event_time = event_time or now_iso()
    safe_time = re.sub(r"[^0-9A-Za-z]+", "-", event_time).strip("-")
    return f"engine-off-{safe_time}-{uuid.uuid4().hex[:8]}"


def load_pending_events(path=PENDING_FILE):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [event for event in data if isinstance(event, dict)]
    except Exception as e:
        print(f"[ShutdownMQTT] 讀取 pending 失敗: {e}")
    return []


def save_pending_events(events, path=PENDING_FILE):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ShutdownMQTT] 儲存 pending 失敗: {e}")


def upsert_pending_event(event, path=PENDING_FILE):
    pending = load_pending_events(path)
    event_id = event.get("event_id")
    if event_id:
        pending = [item for item in pending if item.get("event_id") != event_id]
    pending.append(event)
    save_pending_events(pending, path)
    return pending


def remove_pending_events(sent_event_ids, path=PENDING_FILE):
    sent_event_ids = set(sent_event_ids)
    pending = [
        event for event in load_pending_events(path)
        if event.get("event_id") not in sent_event_ids
    ]
    save_pending_events(pending, path)
    return pending


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


def publish_pending_then_current(client, config, current_event, path=PENDING_FILE):
    pending = upsert_pending_event(current_event, path)
    sent_ids = []

    for event in pending:
        if _publish_one(client, config, event):
            sent_ids.append(event.get("event_id"))
        else:
            break

    remaining = remove_pending_events(sent_ids, path)
    current_sent = current_event.get("event_id") in sent_ids
    return {
        "success": current_sent and not remaining,
        "sent_count": len(sent_ids),
        "remaining_count": len(remaining),
        "current_sent": current_sent,
    }
