import time, uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.config import PROMPTS_FILE
from backend.services.file_store import load_or_default, save_json

router = APIRouter(prefix="/api/prompts", tags=["prompts"])

VALID_LABELS = {"draft", "staging", "production"}


class PromptIn(BaseModel):
    alias:   str
    version: str
    text:    str
    label:   Optional[str] = "draft"


class LabelIn(BaseModel):
    label: str


@router.get("")
def list_prompts():
    prompts = load_or_default(PROMPTS_FILE(), [])
    # Return one entry per alias with current label
    by_alias: dict = {}
    for p in prompts:
        alias = p["alias"]
        if alias not in by_alias:
            by_alias[alias] = {"alias": alias, "versions": [], "currentLabel": None, "updatedAt": ""}
        by_alias[alias]["versions"].append(p["version"])
        if p.get("label") == "production":
            by_alias[alias]["currentLabel"] = "production"
        by_alias[alias]["updatedAt"] = max(by_alias[alias]["updatedAt"], p.get("createdAt", ""))
    return list(by_alias.values())


@router.get("/{alias}")
def get_prompt(alias: str):
    prompts = load_or_default(PROMPTS_FILE(), [])
    versions = [p for p in prompts if p["alias"] == alias]
    if not versions:
        raise HTTPException(404, f"Prompt alias '{alias}' not found")
    return sorted(versions, key=lambda x: x.get("createdAt", ""), reverse=True)


@router.post("")
def save_prompt(body: PromptIn):
    prompts = load_or_default(PROMPTS_FILE(), [])
    entry = {
        "id":        str(uuid.uuid4())[:8],
        "alias":     body.alias,
        "version":   body.version,
        "text":      body.text,
        "label":     body.label,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    prompts.append(entry)
    save_json(PROMPTS_FILE(), prompts)
    return {"success": True, "id": entry["id"]}


@router.put("/{alias}/label")
def set_label(alias: str, body: LabelIn):
    if body.label not in VALID_LABELS:
        raise HTTPException(400, f"Invalid label. Use one of: {VALID_LABELS}")
    prompts = load_or_default(PROMPTS_FILE(), [])
    # If promoting to production, demote existing production
    if body.label == "production":
        for p in prompts:
            if p["alias"] == alias and p.get("label") == "production":
                p["label"] = "staging"
    # Set latest version of this alias to new label
    alias_versions = sorted([p for p in prompts if p["alias"] == alias],
                             key=lambda x: x.get("createdAt", ""), reverse=True)
    if not alias_versions:
        raise HTTPException(404, f"Alias '{alias}' not found")
    alias_versions[0]["label"] = body.label
    save_json(PROMPTS_FILE(), prompts)
    return {"success": True, "alias": alias, "label": body.label}


@router.delete("/{alias}/{version}")
def delete_prompt(alias: str, version: str):
    prompts = load_or_default(PROMPTS_FILE(), [])
    prompts = [p for p in prompts if not (p["alias"] == alias and p["version"] == version)]
    save_json(PROMPTS_FILE(), prompts)
    return {"success": True}
