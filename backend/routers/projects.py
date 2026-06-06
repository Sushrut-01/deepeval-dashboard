"""
Multi-project support.
Projects are detected automatically from hyperparameters.project in run JSON.
Optionally, extra project folders can be configured in projects.json.
"""
import time, uuid
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from collections import defaultdict

from backend.config import HISTORY_FOLDER
from backend.services.file_store import load_or_default, save_json
from backend.services.run_loader import get_all_runs, get_all_summaries

router = APIRouter(prefix="/api/projects", tags=["projects"])

PROJECTS_FILE = lambda: HISTORY_FOLDER / "projects.json"

PROJECT_COLORS = [
    "#6366F1", "#10B981", "#F59E0B", "#EC4899",
    "#0891B2", "#7C3AED", "#E11D48", "#84CC16",
]


@router.get("")
def list_projects():
    """Return all projects — auto-discovered from runs + manually configured."""
    # Auto-discover from run hyperparameters
    discovered: dict = defaultdict(lambda: {"id": "", "name": "", "runCount": 0,
                                             "passed": 0, "failed": 0, "lastRun": ""})
    summaries = get_all_summaries()
    for s in summaries:
        pid = s.get("project", "default")
        discovered[pid]["id"]       = pid
        discovered[pid]["name"]     = pid
        discovered[pid]["runCount"] += 1
        discovered[pid]["passed"]   += s.get("testPassed", 0)
        discovered[pid]["failed"]   += s.get("testFailed", 0)
        if s.get("datetime", "") > discovered[pid]["lastRun"]:
            discovered[pid]["lastRun"] = s.get("datetime", "")

    # Merge with manually configured projects (for extra folder paths / display names)
    configured = load_or_default(PROJECTS_FILE(), []) or []
    cfg_map    = {p["id"]: p for p in configured}

    result = []
    for i, (pid, data) in enumerate(sorted(discovered.items())):
        total = data["passed"] + data["failed"]
        cfg   = cfg_map.get(pid, {})
        result.append({
            "id":       pid,
            "name":     cfg.get("name", pid),
            "color":    cfg.get("color", PROJECT_COLORS[i % len(PROJECT_COLORS)]),
            "folder":   cfg.get("folder"),
            "description": cfg.get("description", ""),
            "runCount": data["runCount"],
            "passed":   data["passed"],
            "failed":   data["failed"],
            "passRate": round(data["passed"] / total, 4) if total else 0.0,
            "lastRun":  data["lastRun"],
            "source":   "configured" if pid in cfg_map else "auto",
        })
    return result


@router.get("/ids")
def project_ids():
    """Return just the list of project IDs for the topbar dropdown."""
    seen = {s.get("project", "default") for s in get_all_summaries()}
    return sorted(seen)


class ProjectConfigIn(BaseModel):
    id:          str
    name:        Optional[str] = None
    color:       Optional[str] = None
    folder:      Optional[str] = None
    description: Optional[str] = None


@router.post("/configure")
def configure_project(body: ProjectConfigIn):
    """Set display name, color, or extra folder for a project."""
    configs = load_or_default(PROJECTS_FILE(), []) or []
    existing = next((p for p in configs if p["id"] == body.id), None)
    if existing:
        if body.name:        existing["name"]        = body.name
        if body.color:       existing["color"]       = body.color
        if body.folder:      existing["folder"]      = body.folder
        if body.description: existing["description"] = body.description
    else:
        configs.append({
            "id":          body.id,
            "name":        body.name or body.id,
            "color":       body.color or PROJECT_COLORS[len(configs) % len(PROJECT_COLORS)],
            "folder":      body.folder,
            "description": body.description or "",
        })
    save_json(PROJECTS_FILE(), configs)
    return {"success": True}


@router.get("/{project_id}/stats")
def project_stats(project_id: str):
    """Per-project summary: runs, pass rate, last run, top metrics."""
    runs = get_all_runs()
    proj_runs = [r for r in runs if r.get("_project") == project_id]
    if not proj_runs:
        return {"projectId": project_id, "runCount": 0}

    total_p = sum(r.get("testPassed", 0)  for r in proj_runs)
    total_f = sum(r.get("testFailed", 0)  for r in proj_runs)
    total   = total_p + total_f
    cost    = sum(r.get("evaluationCost") or 0.0 for r in proj_runs)

    # Metric averages across all runs for this project
    from collections import defaultdict
    metric_scores: dict = defaultdict(list)
    for r in proj_runs:
        for ms in (r.get("metricsScores") or []):
            metric_scores[ms["metric"]].extend(ms.get("scores") or [])

    return {
        "projectId":  project_id,
        "runCount":   len(proj_runs),
        "passed":     total_p,
        "failed":     total_f,
        "passRate":   round(total_p / total, 4) if total else 0.0,
        "totalCost":  round(cost, 6),
        "lastRun":    proj_runs[0]["_datetime"],
        "metrics":    [{"metric": k, "avg": round(sum(v) / len(v), 4)}
                       for k, v in sorted(metric_scores.items())],
    }
