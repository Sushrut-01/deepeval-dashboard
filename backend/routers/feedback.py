import time, uuid
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from backend.config import FEEDBACK_FILE
from backend.services.file_store import load_or_default, save_json

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackIn(BaseModel):
    runFile:   str
    caseName:  str
    spanId:    Optional[str] = None
    type:      str  # "thumbs_up" | "thumbs_down" | "numeric"
    score:     Optional[float] = None
    comment:   Optional[str] = None


@router.get("")
def list_feedback(run: Optional[str] = None):
    data = load_or_default(FEEDBACK_FILE(), [])
    if run:
        data = [f for f in data if f.get("runFile") == run]
    return data


@router.post("")
def save_feedback(body: FeedbackIn):
    data = load_or_default(FEEDBACK_FILE(), [])
    entry = {
        "id":        str(uuid.uuid4())[:8],
        "runFile":   body.runFile,
        "caseName":  body.caseName,
        "spanId":    body.spanId,
        "type":      body.type,
        "score":     body.score,
        "comment":   body.comment,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    data.insert(0, entry)
    save_json(FEEDBACK_FILE(), data)
    return {"success": True, "id": entry["id"]}


@router.get("/summary")
def feedback_summary():
    data = load_or_default(FEEDBACK_FILE(), [])
    if not data:
        return {"thumbsUp": 0, "thumbsDown": 0, "avgScore": None, "total": 0}
    up   = sum(1 for f in data if f.get("type") == "thumbs_up")
    down = sum(1 for f in data if f.get("type") == "thumbs_down")
    nums = [f["score"] for f in data if f.get("type") == "numeric" and f.get("score") is not None]
    return {
        "thumbsUp":   up,
        "thumbsDown": down,
        "thumbsUpPct": round(up / (up + down), 4) if (up + down) else 0,
        "avgScore":   round(sum(nums) / len(nums), 3) if nums else None,
        "total":      len(data),
    }
