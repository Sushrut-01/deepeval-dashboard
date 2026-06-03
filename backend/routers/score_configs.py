import uuid, time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from backend.config import SCORE_CONFIGS_FILE
from backend.services.file_store import load_or_default, save_json

router = APIRouter(prefix="/api/score-configs", tags=["score_configs"])


class ScoreConfigIn(BaseModel):
    name:       str
    type:       str          # numeric | boolean | categorical
    rangeMin:   Optional[float] = 0.0
    rangeMax:   Optional[float] = 1.0
    categories: Optional[List[str]] = []
    description: Optional[str] = None


@router.get("")
def list_configs():
    return load_or_default(SCORE_CONFIGS_FILE(), [])


@router.post("")
def create_config(body: ScoreConfigIn):
    configs = load_or_default(SCORE_CONFIGS_FILE(), [])
    cfg = {
        "id":          str(uuid.uuid4())[:8],
        "name":        body.name,
        "type":        body.type,
        "rangeMin":    body.rangeMin,
        "rangeMax":    body.rangeMax,
        "categories":  body.categories,
        "description": body.description,
        "createdAt":   time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    configs.append(cfg)
    save_json(SCORE_CONFIGS_FILE(), configs)
    return {"success": True, "id": cfg["id"]}


@router.put("/{config_id}")
def update_config(config_id: str, body: ScoreConfigIn):
    configs = load_or_default(SCORE_CONFIGS_FILE(), [])
    for cfg in configs:
        if cfg["id"] == config_id:
            cfg.update({"name": body.name, "type": body.type,
                        "rangeMin": body.rangeMin, "rangeMax": body.rangeMax,
                        "categories": body.categories, "description": body.description})
            save_json(SCORE_CONFIGS_FILE(), configs)
            return {"success": True}
    raise HTTPException(404, "Score config not found")


@router.delete("/{config_id}")
def delete_config(config_id: str):
    configs = load_or_default(SCORE_CONFIGS_FILE(), [])
    configs = [c for c in configs if c["id"] != config_id]
    save_json(SCORE_CONFIGS_FILE(), configs)
    return {"success": True}
