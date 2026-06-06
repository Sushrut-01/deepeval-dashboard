import time, uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from backend.config import QUEUES_FILE
from backend.services.file_store import load_or_default, save_json

router = APIRouter(prefix="/api/queues", tags=["queues"])


class QueueIn(BaseModel):
    name:         str
    description:  Optional[str] = None
    scoreConfigs: Optional[List[str]] = []
    assignees:    Optional[List[str]] = []


class ItemSubmitIn(BaseModel):
    runFile:         str
    caseName:        str
    scores:          Optional[dict] = {}
    correctedOutput: Optional[str] = None
    note:            Optional[str] = None
    reviewer:        Optional[str] = None


@router.get("")
def list_queues():
    queues = load_or_default(QUEUES_FILE(), [])
    return [{k: v for k, v in q.items() if k != "items"} for q in queues]


@router.post("")
def create_queue(body: QueueIn):
    queues = load_or_default(QUEUES_FILE(), [])
    q = {
        "id":           str(uuid.uuid4())[:8],
        "name":         body.name,
        "description":  body.description,
        "scoreConfigs": body.scoreConfigs,
        "assignees":    body.assignees,
        "items":        [],
        "createdAt":    time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    queues.append(q)
    save_json(QUEUES_FILE(), queues)
    return {"success": True, "id": q["id"]}


@router.get("/{queue_id}")
def get_queue(queue_id: str):
    queues = load_or_default(QUEUES_FILE(), [])
    q = next((q for q in queues if q["id"] == queue_id), None)
    if not q:
        raise HTTPException(404, "Queue not found")
    items      = q.get("items") or []
    reviewed   = sum(1 for i in items if i.get("reviewed"))
    return {**q, "itemCount": len(items), "reviewedCount": reviewed,
            "progress": round(reviewed / len(items), 4) if items else 0}


@router.post("/{queue_id}/items")
def add_item(queue_id: str, body: ItemSubmitIn):
    queues = load_or_default(QUEUES_FILE(), [])
    q = next((q for q in queues if q["id"] == queue_id), None)
    if not q:
        raise HTTPException(404, "Queue not found")
    item_id = str(uuid.uuid4())[:8]
    q.setdefault("items", []).append({
        "id":       item_id,
        "runFile":  body.runFile,
        "caseName": body.caseName,
        "reviewed": False,
        "addedAt":  time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    save_json(QUEUES_FILE(), queues)
    return {"success": True, "itemId": item_id}


@router.get("/{queue_id}/next")
def next_item(queue_id: str):
    queues = load_or_default(QUEUES_FILE(), [])
    q = next((q for q in queues if q["id"] == queue_id), None)
    if not q:
        raise HTTPException(404, "Queue not found")
    items = q.get("items") or []
    pending = [i for i in items if not i.get("reviewed")]
    if not pending:
        return {"done": True, "item": None}
    item = pending[0]
    # Attach test case data
    from backend.services.run_loader import get_run, get_test_case
    run = get_run(item["runFile"])
    tc  = get_test_case(run, item["caseName"]) if run else None
    return {"done": False, "item": item, "testCase": tc,
            "remaining": len(pending), "total": len(items)}


@router.post("/{queue_id}/items/{item_id}")
def submit_item(queue_id: str, item_id: str, body: ItemSubmitIn):
    queues = load_or_default(QUEUES_FILE(), [])
    q = next((q for q in queues if q["id"] == queue_id), None)
    if not q:
        raise HTTPException(404, "Queue not found")
    for item in (q.get("items") or []):
        if item["id"] == item_id:
            item["reviewed"]        = True
            item["scores"]          = body.scores
            item["correctedOutput"] = body.correctedOutput
            item["note"]            = body.note
            item["reviewer"]        = body.reviewer
            item["reviewedAt"]      = time.strftime("%Y-%m-%dT%H:%M:%S")
            save_json(QUEUES_FILE(), queues)
            # Also save to annotations
            from backend.routers.annotations import save_annotation, AnnotationIn
            save_annotation(AnnotationIn(
                runFile=item["runFile"], caseName=item["caseName"],
                scores=body.scores, correctedOutput=body.correctedOutput,
                note=body.note, reviewer=body.reviewer, queueId=queue_id,
            ))
            return {"success": True}
    raise HTTPException(404, "Item not found")


@router.delete("/{queue_id}")
def delete_queue(queue_id: str):
    queues = load_or_default(QUEUES_FILE(), [])
    queues = [q for q in queues if q["id"] != queue_id]
    save_json(QUEUES_FILE(), queues)
    return {"success": True}
