"""
Tiny JSON-file storage helper.
Every model (notification, chat_message, buyer_price, material_category, etc.)
reads and writes through this instead of touching files directly.
"""
import json
import os
from threading import Lock

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

_lock = Lock()


def _path(collection: str) -> str:
    return os.path.join(DATA_DIR, f"{collection}.json")


def read_all(collection: str) -> list:
    path = _path(collection)
    if not os.path.exists(path):
        return []
    with _lock:
        with open(path, "r") as f:
            content = f.read().strip()
            return json.loads(content) if content else []


def write_all(collection: str, records: list) -> None:
    path = _path(collection)
    with _lock:
        with open(path, "w") as f:
            json.dump(records, f, indent=2, default=str)


def next_id(records: list) -> int:
    if not records:
        return 1
    return max(r.get("id", 0) for r in records) + 1