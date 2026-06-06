import csv, io, time, uuid
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from backend.config import ANNOTATIONS_FILE
from backend.services.file_store import load_or_default, save_json

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


class AnnotationIn(BaseModel):
    runFile:         str
    caseName:        str
    label:           Optional[str] = None   # correct | incorrect | needs_review
    note:            Optional[str] = None
    correctedOutput: Optional[str] = None
    scores:          Optional[Dict[str, Any]] = None
    reviewer:        Optional[str] = None
    queueId:         Optional[str] = None


@router.get("")
def list_annotations(
    run:    Optional[str] = None,
    label:  Optional[str] = None,
    queue:  Optional[str] = None,
    annotated: Optional[bool] = None,
):
    data = load_or_default(ANNOTATIONS_FILE(), [])
    if run:
        data = [a for a in data if a.get("runFile") == run]
    if label:
        data = [a for a in data if a.get("label") == label]
    if queue:
        data = [a for a in data if a.get("queueId") == queue]
    if annotated is True:
        data = [a for a in data if a.get("label")]
    elif annotated is False:
        data = [a for a in data if not a.get("label")]
    return data


@router.post("")
def save_annotation(body: AnnotationIn):
    data = load_or_default(ANNOTATIONS_FILE(), [])
    key = f"{body.runFile}::{body.caseName}"
    # Update existing or append new
    for item in data:
        if item.get("_key") == key:
            item.update({
                "label":           body.label,
                "note":            body.note,
                "correctedOutput": body.correctedOutput,
                "scores":          body.scores,
                "reviewer":        body.reviewer,
                "queueId":         body.queueId,
                "updatedAt":       time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            save_json(ANNOTATIONS_FILE(), data)
            return {"success": True, "id": item["id"]}

    entry = {
        "id":              str(uuid.uuid4())[:8],
        "_key":            key,
        "runFile":         body.runFile,
        "caseName":        body.caseName,
        "label":           body.label,
        "note":            body.note,
        "correctedOutput": body.correctedOutput,
        "scores":          body.scores or {},
        "reviewer":        body.reviewer,
        "queueId":         body.queueId,
        "createdAt":       time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updatedAt":       time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    data.append(entry)
    save_json(ANNOTATIONS_FILE(), data)
    return {"success": True, "id": entry["id"]}


@router.put("/{annotation_id}")
def update_annotation(annotation_id: str, body: AnnotationIn):
    data = load_or_default(ANNOTATIONS_FILE(), [])
    for item in data:
        if item.get("id") == annotation_id:
            item.update({
                "label":           body.label,
                "note":            body.note,
                "correctedOutput": body.correctedOutput,
                "scores":          body.scores,
                "updatedAt":       time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            save_json(ANNOTATIONS_FILE(), data)
            return {"success": True}
    return {"success": False, "error": "Not found"}


@router.get("/stats")
def annotation_stats():
    data = load_or_default(ANNOTATIONS_FILE(), [])
    total  = len(data)
    labels = [a.get("label") for a in data if a.get("label")]
    from collections import Counter
    counts = Counter(labels)
    return {
        "total":        total,
        "annotated":    len(labels),
        "correct":      counts.get("correct", 0),
        "incorrect":    counts.get("incorrect", 0),
        "needsReview":  counts.get("needs_review", 0),
    }


@router.get("/export/csv")
def export_csv():
    data = load_or_default(ANNOTATIONS_FILE(), [])
    fields = ["id", "runFile", "caseName", "label", "note", "correctedOutput", "reviewer", "createdAt"]
    buf = io.StringIO()
    w   = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(data)
    buf.seek(0)
    return StreamingResponse(io.BytesIO(buf.getvalue().encode()),
                             media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=annotations.csv"})
