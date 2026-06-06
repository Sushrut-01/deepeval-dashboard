import uuid, time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.config import HISTORY_FOLDER
from backend.services.file_store import load_or_default, save_json
from backend.services.sla_calculator import (
    get_slo_status, get_compliance, get_sli_history,
    SLO_FILE, BREACH_FILE,
)

router = APIRouter(prefix="/api/sla", tags=["sla"])

SLO_TYPES = [
    "metric_pass_rate", "metric_avg_score",
    "latency_p95", "latency_p99",
    "error_rate", "cost_per_run", "pass_rate",
]


class SLOIn(BaseModel):
    name:       str
    type:       str
    metric:     Optional[str] = None
    spanType:   Optional[str] = "llm"
    operator:   str = ">="
    target:     float
    windowRuns: int = 10
    enabled:    bool = True
    description: Optional[str] = None


# ── SLO CRUD ──────────────────────────────────────────────────────────────────

@router.get("/slos")
def list_slos():
    return load_or_default(SLO_FILE(), []) or []


@router.post("/slos")
def create_slo(body: SLOIn):
    slos = load_or_default(SLO_FILE(), []) or []
    slo = {
        "id":          str(uuid.uuid4())[:8],
        "name":        body.name,
        "type":        body.type,
        "metric":      body.metric,
        "spanType":    body.spanType,
        "operator":    body.operator,
        "target":      body.target,
        "windowRuns":  body.windowRuns,
        "enabled":     body.enabled,
        "description": body.description,
        "createdAt":   time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    slos.append(slo)
    save_json(SLO_FILE(), slos)
    return {"success": True, "id": slo["id"]}


@router.put("/slos/{slo_id}")
def update_slo(slo_id: str, body: SLOIn):
    slos = load_or_default(SLO_FILE(), []) or []
    for s in slos:
        if s["id"] == slo_id:
            s.update({
                "name": body.name, "type": body.type,
                "metric": body.metric, "spanType": body.spanType,
                "operator": body.operator, "target": body.target,
                "windowRuns": body.windowRuns, "enabled": body.enabled,
                "description": body.description,
            })
            save_json(SLO_FILE(), slos)
            return {"success": True}
    raise HTTPException(404, "SLO not found")


@router.delete("/slos/{slo_id}")
def delete_slo(slo_id: str):
    slos = load_or_default(SLO_FILE(), []) or []
    slos = [s for s in slos if s["id"] != slo_id]
    save_json(SLO_FILE(), slos)
    return {"success": True}


# ── SLI / Compliance ──────────────────────────────────────────────────────────

@router.get("/status")
def slo_status(project: Optional[str] = None):
    return get_slo_status(project)


@router.get("/compliance")
def sla_compliance(project: Optional[str] = None):
    return get_compliance(project)


@router.get("/slis/{slo_id}/history")
def sli_history(slo_id: str, project: Optional[str] = None):
    return get_sli_history(slo_id, project)


# ── Breaches ──────────────────────────────────────────────────────────────────

@router.get("/breaches")
def list_breaches(limit: int = 50):
    breaches = load_or_default(BREACH_FILE(), []) or []
    return breaches[:limit]


@router.post("/breaches/{idx}/resolve")
def resolve_breach(idx: int):
    breaches = load_or_default(BREACH_FILE(), []) or []
    if idx < len(breaches):
        breaches[idx]["resolved"] = True
        save_json(BREACH_FILE(), breaches)
    return {"success": True}


# ── Default SLOs (seed on first use) ─────────────────────────────────────────

@router.post("/seed-defaults")
def seed_defaults():
    """Create default SLOs if none exist yet."""
    existing = load_or_default(SLO_FILE(), []) or []
    if existing:
        return {"message": "SLOs already configured", "count": len(existing)}

    defaults = [
        {"name": "Faithfulness Reliability",   "type": "metric_pass_rate",  "metric": "Faithfulness",    "operator": ">=", "target": 0.80, "windowRuns": 10},
        {"name": "Answer Relevancy Quality",   "type": "metric_pass_rate",  "metric": "AnswerRelevancy", "operator": ">=", "target": 0.75, "windowRuns": 10},
        {"name": "Hallucination Safety",       "type": "metric_avg_score",  "metric": "Hallucination",   "operator": ">=", "target": 0.85, "windowRuns": 10},
        {"name": "LLM P95 Latency",           "type": "latency_p95",       "spanType": "llm",           "operator": "<=", "target": 5000, "windowRuns": 10},
        {"name": "Retrieval P95 Latency",     "type": "latency_p95",       "spanType": "retriever",     "operator": "<=", "target": 2000, "windowRuns": 10},
        {"name": "Overall Pass Rate",         "type": "pass_rate",                                      "operator": ">=", "target": 0.70, "windowRuns": 10},
        {"name": "Eval Cost Budget",          "type": "cost_per_run",                                   "operator": "<=", "target": 0.10, "windowRuns": 10},
        {"name": "Pipeline Error Rate",       "type": "error_rate",                                     "operator": "<=", "target": 0.05, "windowRuns": 10},
    ]
    slos = []
    for d in defaults:
        d["id"]        = str(uuid.uuid4())[:8]
        d["enabled"]   = True
        d["createdAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        d.setdefault("metric",   None)
        d.setdefault("spanType", "llm")
        slos.append(d)
    save_json(SLO_FILE(), slos)
    return {"success": True, "created": len(slos)}


@router.get("/types")
def slo_types():
    return SLO_TYPES
