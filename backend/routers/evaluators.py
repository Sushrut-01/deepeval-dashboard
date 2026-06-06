import uuid, time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.config import EVALUATORS_FILE
from backend.services.file_store import load_or_default, save_json

router = APIRouter(prefix="/api/evaluators", tags=["evaluators"])


class EvaluatorIn(BaseModel):
    name:         str
    metric:       str
    filter:       Optional[dict] = {}
    samplingRate: float = 1.0
    enabled:      bool = True
    runOn:        str = "every_new_run"  # every_new_run | manually


@router.get("")
def list_evaluators():
    return load_or_default(EVALUATORS_FILE(), [])


@router.post("")
def create_evaluator(body: EvaluatorIn):
    evs = load_or_default(EVALUATORS_FILE(), [])
    ev = {
        "id":           str(uuid.uuid4())[:8],
        "name":         body.name,
        "metric":       body.metric,
        "filter":       body.filter,
        "samplingRate": body.samplingRate,
        "enabled":      body.enabled,
        "runOn":        body.runOn,
        "results":      [],
        "lastRun":      None,
        "createdAt":    time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    evs.append(ev)
    save_json(EVALUATORS_FILE(), evs)
    return {"success": True, "id": ev["id"]}


@router.put("/{ev_id}")
def update_evaluator(ev_id: str, body: EvaluatorIn):
    evs = load_or_default(EVALUATORS_FILE(), [])
    for ev in evs:
        if ev["id"] == ev_id:
            ev.update({"name": body.name, "metric": body.metric, "filter": body.filter,
                        "samplingRate": body.samplingRate, "enabled": body.enabled})
            save_json(EVALUATORS_FILE(), evs)
            return {"success": True}
    raise HTTPException(404, "Evaluator not found")


@router.get("/{ev_id}/results")
def get_results(ev_id: str):
    evs = load_or_default(EVALUATORS_FILE(), [])
    ev  = next((e for e in evs if e["id"] == ev_id), None)
    if not ev:
        raise HTTPException(404, "Evaluator not found")
    return ev.get("results") or []


@router.post("/{ev_id}/run-now")
def run_now(ev_id: str):
    evs = load_or_default(EVALUATORS_FILE(), [])
    ev  = next((e for e in evs if e["id"] == ev_id), None)
    if not ev:
        raise HTTPException(404, "Evaluator not found")
    from backend.services.run_loader import get_all_runs
    from backend.services.online_eval_worker import _apply_evaluator
    runs = get_all_runs()
    if runs:
        _apply_evaluator(ev, runs[0]["_filename"], runs[0])
    return {"success": True, "message": f"Evaluator '{ev['name']}' triggered on latest run"}
