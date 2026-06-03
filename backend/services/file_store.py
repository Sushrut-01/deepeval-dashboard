"""Thread-safe JSON file read/write for persistent storage."""
import json
import threading
from pathlib import Path
from typing import Any, Optional

_locks: dict = {}
_meta_lock = threading.Lock()


def _get_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _meta_lock:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with _get_lock(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _get_lock(path):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_or_default(path: Path, default: Any) -> Any:
    result = load_json(path)
    return result if result is not None else default
