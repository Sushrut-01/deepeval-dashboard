import os
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from typing import Optional

from backend.config import HISTORY_FOLDER
from backend.services.run_loader import (
    get_all_summaries, get_run, get_test_case,
    get_all_test_cases, force_refresh,
)

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("")
def list_runs(
    env:     Optional[str] = None,
    version: Optional[str] = None,
    project: Optional[str] = None,
    status:  Optional[str] = None,
    search:  Optional[str] = None,
    page:    int = Query(1, ge=1),
    limit:   int = Query(25, ge=1, le=100),
):
    summaries = get_all_summaries()

    if env and env != "all":
        summaries = [r for r in summaries if r["environment"] == env]
    if version and version != "all":
        summaries = [r for r in summaries if r["version"] == version]
    if project and project != "all":
        summaries = [r for r in summaries if r.get("project") == project]
    if status == "pass":
        summaries = [r for r in summaries if r["passRate"] >= 1.0]
    elif status == "fail":
        summaries = [r for r in summaries if r["passRate"] < 1.0]
    if search:
        q = search.lower()
        summaries = [r for r in summaries if q in r["filename"].lower()
                     or q in (r.get("identifier") or "").lower()]

    total = len(summaries)
    start = (page - 1) * limit
    return {"data": summaries[start:start + limit], "total": total, "page": page, "limit": limit}


@router.get("/envs")
def list_envs():
    return list({r["environment"] for r in get_all_summaries()})


@router.get("/versions")
def list_versions():
    return list({r["version"] for r in get_all_summaries()})


@router.get("/{filename}")
def get_run_detail(filename: str):
    run = get_run(filename)
    if not run:
        raise HTTPException(404, f"Run '{filename}' not found")
    return run


@router.get("/{filename}/summary")
def get_run_summary(filename: str):
    run = get_run(filename)
    if not run:
        raise HTTPException(404, f"Run '{filename}' not found")
    return {
        "filename":      run["_filename"],
        "datetime":      run["_datetime"],
        "environment":   run["_environment"],
        "version":       run["_version"],
        "testPassed":    run["testPassed"],
        "testFailed":    run["testFailed"],
        "passRate":      run["_passRate"],
        "errorRate":     run["_errorRate"],
        "runDuration":   run["runDuration"],
        "evaluationCost": run["evaluationCost"],
        "metricsScores": run["metricsScores"],
        "hyperparameters": run.get("hyperparameters"),
        "identifier":    run.get("identifier"),
        "datasetAlias":  run.get("datasetAlias"),
        "hasTraces":     run["_hasTraces"],
    }


@router.get("/{filename}/cases")
def get_run_cases(
    filename: str,
    status:   Optional[str] = None,
    metric:   Optional[str] = None,
    search:   Optional[str] = None,
    has_trace: Optional[bool] = None,
    has_bug:   Optional[bool] = None,
    tag:      Optional[str] = None,
    page:     int = Query(1, ge=1),
    limit:    int = Query(50, ge=1, le=200),
):
    run = get_run(filename)
    if not run:
        raise HTTPException(404, f"Run '{filename}' not found")

    cases = get_all_test_cases(run)

    if status == "pass":
        cases = [c for c in cases if c.get("success") is True]
    elif status == "fail":
        cases = [c for c in cases if c.get("success") is False]

    if metric:
        m_lower = metric.lower()
        cases = [c for c in cases if any(
            m.get("name", "").lower() == m_lower for m in (c.get("metricsData") or [])
        )]

    if search:
        q = search.lower()
        cases = [c for c in cases if q in c.get("name", "").lower()
                 or q in c.get("input", "").lower()]

    if has_trace is True:
        cases = [c for c in cases if c.get("trace")]
    elif has_trace is False:
        cases = [c for c in cases if not c.get("trace")]

    if tag:
        cases = [c for c in cases if tag in (c.get("tags") or [])]

    total = len(cases)
    start = (page - 1) * limit

    # Return lightweight case rows (no trace body)
    rows = []
    for c in cases[start:start + limit]:
        rows.append({
            "name":       c.get("name"),
            "type":       c.get("type"),
            "success":    c.get("success"),
            "tags":       c.get("tags"),
            "runDuration": c.get("runDuration"),
            "evaluationCost": c.get("evaluationCost"),
            "hasTrace":   bool(c.get("trace")),
            "metrics":    [{
                "name":    m.get("name"),
                "score":   m.get("score"),
                "success": m.get("success"),
                "threshold": m.get("threshold"),
            } for m in (c.get("metricsData") or [])],
        })

    return {"data": rows, "total": total, "page": page, "limit": limit}


@router.get("/{filename}/cases/{name}")
def get_case_detail(filename: str, name: str):
    run = get_run(filename)
    if not run:
        raise HTTPException(404, f"Run '{filename}' not found")
    tc = get_test_case(run, name)
    if not tc:
        raise HTTPException(404, f"Test case '{name}' not found in {filename}")
    # Return full case but exclude trace (it's fetched separately)
    result = {k: v for k, v in tc.items() if k != "trace"}
    result["hasTrace"] = bool(tc.get("trace"))
    return result


@router.get("/{filename}/cases/{name}/trace")
def get_case_trace(filename: str, name: str):
    run = get_run(filename)
    if not run:
        raise HTTPException(404, f"Run '{filename}' not found")
    tc = get_test_case(run, name)
    if not tc:
        raise HTTPException(404, f"Test case '{name}' not found")
    trace = tc.get("trace")
    if not trace:
        raise HTTPException(404, f"Test case '{name}' has no trace data")
    return trace


@router.get("/{filename}/export")
def export_run(filename: str):
    path = HISTORY_FOLDER / filename
    if not path.exists():
        raise HTTPException(404, f"File '{filename}' not found")
    return FileResponse(str(path), filename=filename, media_type="application/json")


@router.get("/{filename}/bug-report")
def get_run_bug_report(filename: str):
    from backend.config import BUG_REPORTS_FILE
    from backend.services.file_store import load_or_default
    reports = load_or_default(BUG_REPORTS_FILE(), {})
    report = reports.get(filename)
    if not report:
        # Generate on-demand if not cached
        run = get_run(filename)
        if not run:
            raise HTTPException(404, f"Run '{filename}' not found")
        from backend.services.bug_detector import analyze_run
        from backend.services.run_loader import get_all_runs
        all_runs = get_all_runs()
        prev = [r for r in all_runs if r["_filename"] != filename][:5]
        report = analyze_run(run, prev)
        reports[filename] = report
        from backend.services.file_store import save_json
        save_json(BUG_REPORTS_FILE(), reports)
    return report


@router.delete("/{filename}")
def delete_run(filename: str):
    path = HISTORY_FOLDER / filename
    if not path.exists():
        raise HTTPException(404, f"File '{filename}' not found")
    if not filename.startswith("test_run_") or not filename.endswith(".json"):
        raise HTTPException(400, "Only test_run_*.json files can be deleted")
    os.remove(path)
    force_refresh()
    return {"success": True, "deleted": filename}
