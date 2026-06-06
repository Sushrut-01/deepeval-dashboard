import uuid, time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from backend.config import WEBHOOKS_FILE
from backend.services.file_store import load_or_default, save_json

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

VALID_EVENTS = ["new_run", "eval_failed", "bug_detected", "annotation_saved",
                "rule_matched", "regression_detected"]


class WebhookIn(BaseModel):
    name:   str
    url:    str
    secret: Optional[str] = ""
    events: Optional[List[str]] = ["new_run"]


@router.get("")
def list_webhooks():
    hooks = load_or_default(WEBHOOKS_FILE(), [])
    return [{k: v for k, v in h.items() if k != "secret"} for h in hooks]


@router.post("")
def create_webhook(body: WebhookIn):
    hooks = load_or_default(WEBHOOKS_FILE(), [])
    hook = {
        "id":         str(uuid.uuid4())[:8],
        "name":       body.name,
        "url":        body.url,
        "secret":     body.secret,
        "events":     body.events,
        "deliveries": [],
        "lastFired":  None,
        "createdAt":  time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    hooks.append(hook)
    save_json(WEBHOOKS_FILE(), hooks)
    return {"success": True, "id": hook["id"]}


@router.put("/{hook_id}")
def update_webhook(hook_id: str, body: WebhookIn):
    hooks = load_or_default(WEBHOOKS_FILE(), [])
    for h in hooks:
        if h["id"] == hook_id:
            h.update({"name": body.name, "url": body.url,
                       "events": body.events})
            if body.secret:
                h["secret"] = body.secret
            save_json(WEBHOOKS_FILE(), hooks)
            return {"success": True}
    raise HTTPException(404, "Webhook not found")


@router.post("/{hook_id}/test")
def test_webhook(hook_id: str):
    hooks = load_or_default(WEBHOOKS_FILE(), [])
    h = next((h for h in hooks if h["id"] == hook_id), None)
    if not h:
        raise HTTPException(404, "Webhook not found")
    import httpx
    try:
        r = httpx.post(h["url"], json={"event": "test", "payload": {"message": "DeepEval test ping"}}, timeout=10)
        return {"success": True, "status": r.status_code, "response": r.text[:500]}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/{hook_id}")
def delete_webhook(hook_id: str):
    hooks = load_or_default(WEBHOOKS_FILE(), [])
    hooks = [h for h in hooks if h["id"] != hook_id]
    save_json(WEBHOOKS_FILE(), hooks)
    return {"success": True}
