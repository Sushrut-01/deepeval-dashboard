import uuid, time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.config import AUTOMATIONS_FILE
from backend.services.file_store import load_or_default, save_json

router = APIRouter(prefix="/api/automations", tags=["automations"])


class AutomationIn(BaseModel):
    name:         str
    filter:       Optional[dict] = {}
    samplingRate: float = 1.0
    action:       str   # addToQueue | addToDataset | webhook | alert
    actionTarget: Optional[str] = None
    enabled:      bool = True


@router.get("")
def list_rules():
    return load_or_default(AUTOMATIONS_FILE(), [])


@router.post("")
def create_rule(body: AutomationIn):
    rules = load_or_default(AUTOMATIONS_FILE(), [])
    rule = {
        "id":           str(uuid.uuid4())[:8],
        "name":         body.name,
        "filter":       body.filter,
        "samplingRate": body.samplingRate,
        "action":       body.action,
        "actionTarget": body.actionTarget,
        "enabled":      body.enabled,
        "triggerCount": 0,
        "history":      [],
        "createdAt":    time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    rules.append(rule)
    save_json(AUTOMATIONS_FILE(), rules)
    return {"success": True, "id": rule["id"]}


@router.put("/{rule_id}")
def update_rule(rule_id: str, body: AutomationIn):
    rules = load_or_default(AUTOMATIONS_FILE(), [])
    for r in rules:
        if r["id"] == rule_id:
            r.update({"name": body.name, "filter": body.filter,
                       "samplingRate": body.samplingRate, "action": body.action,
                       "actionTarget": body.actionTarget, "enabled": body.enabled})
            save_json(AUTOMATIONS_FILE(), rules)
            return {"success": True}
    raise HTTPException(404, "Rule not found")


@router.delete("/{rule_id}")
def delete_rule(rule_id: str):
    rules = load_or_default(AUTOMATIONS_FILE(), [])
    rules = [r for r in rules if r["id"] != rule_id]
    save_json(AUTOMATIONS_FILE(), rules)
    return {"success": True}
