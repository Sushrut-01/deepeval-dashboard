"""Fire HTTP POST webhooks with HMAC-SHA256 signature."""
import hashlib
import hmac
import json
import logging
import threading
import time
from typing import Optional

import httpx

from backend.config import WEBHOOKS_FILE
from backend.services.file_store import load_json, save_json

logger = logging.getLogger(__name__)


def fire_event(event: str, payload: dict):
    """Fire all webhooks subscribed to `event` in a background thread."""
    threading.Thread(target=_fire, args=(event, payload), daemon=True).start()


def _fire(event: str, payload: dict):
    hooks = load_json(WEBHOOKS_FILE()) or []
    for hook in hooks:
        if event not in (hook.get("events") or []):
            continue
        url    = hook.get("url", "")
        secret = hook.get("secret", "")
        if not url:
            continue
        body    = json.dumps({"event": event, "payload": payload})
        headers = {"Content-Type": "application/json", "X-DeepEval-Event": event}
        if secret:
            sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            headers["X-DeepEval-Signature"] = f"sha256={sig}"
        try:
            r = httpx.post(url, content=body, headers=headers, timeout=10)
            _log_delivery(hook.get("id"), event, r.status_code, url)
        except Exception as e:
            logger.warning(f"webhook_sender: failed to POST {url}: {e}")
            _log_delivery(hook.get("id"), event, 0, url, str(e))


def _log_delivery(hook_id: str, event: str, status: int, url: str, error: str = None):
    hooks = load_json(WEBHOOKS_FILE()) or []
    for h in hooks:
        if h.get("id") == hook_id:
            logs = h.setdefault("deliveries", [])
            logs.insert(0, {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "event": event,
                "status": status,
                "url": url,
                "error": error,
            })
            h["deliveries"] = logs[:50]  # keep last 50
            h["lastFired"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_json(WEBHOOKS_FILE(), hooks)
