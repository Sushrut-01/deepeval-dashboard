from fastapi import APIRouter, HTTPException
from collections import defaultdict
from backend.config import BUG_REPORTS_FILE
from backend.services.file_store import load_or_default, save_json
from backend.services.run_loader import get_all_runs, get_run

router = APIRouter(prefix="/api/bugs", tags=["bugs"])


def _get_all_reports() -> dict:
    return load_or_default(BUG_REPORTS_FILE(), {})


def _ensure_report(filename: str) -> dict:
    reports = _get_all_reports()
    if filename not in reports:
        run = get_run(filename)
        if not run:
            raise HTTPException(404, f"Run '{filename}' not found")
        from backend.services.bug_detector import analyze_run
        prev = [r for r in get_all_runs() if r["_filename"] != filename][:5]
        report = analyze_run(run, prev)
        reports[filename] = report
        save_json(BUG_REPORTS_FILE(), reports)
    return reports[filename]


@router.get("/run/{filename}")
def get_run_bugs(filename: str):
    return _ensure_report(filename)


@router.post("/analyze/{filename}")
def force_analyze(filename: str):
    run = get_run(filename)
    if not run:
        raise HTTPException(404, f"Run '{filename}' not found")
    from backend.services.bug_detector import analyze_run
    reports = _get_all_reports()
    prev = [r for r in get_all_runs() if r["_filename"] != filename][:5]
    report = analyze_run(run, prev)
    reports[filename] = report
    save_json(BUG_REPORTS_FILE(), reports)
    return report


@router.get("/summary")
def bug_summary():
    reports = _get_all_reports()
    type_counts: dict = defaultdict(int)
    total = critical = warning = info = 0
    for report in reports.values():
        total    += report.get("total", 0)
        critical += report.get("critical", 0)
        warning  += report.get("warning", 0)
        info     += report.get("info", 0)
        for bug in (report.get("bugs") or []):
            type_counts[bug.get("type", "UNKNOWN")] += 1
    return {
        "totalBugs": total, "critical": critical, "warning": warning, "info": info,
        "byType": [{"type": k, "count": v} for k, v in sorted(type_counts.items(), key=lambda x: -x[1])],
    }


@router.get("/patterns")
def recurring_patterns():
    reports = _get_all_reports()
    pattern: dict = defaultdict(list)
    for fname, report in reports.items():
        for bug in (report.get("bugs") or []):
            key = f"{bug.get('type')}::{bug.get('testCase')}"
            pattern[key].append({"filename": fname, "bugId": bug.get("bugId"),
                                  "title": bug.get("title"), "severity": bug.get("severity")})
    recurring = [{"pattern": k, "count": len(v), "occurrences": v}
                 for k, v in pattern.items() if len(v) >= 2]
    return sorted(recurring, key=lambda x: -x["count"])


@router.get("/regressions")
def get_regressions():
    reports = _get_all_reports()
    regs = []
    for fname, report in reports.items():
        for bug in (report.get("bugs") or []):
            if bug.get("type") == "REGRESSION":
                regs.append({**bug, "filename": fname})
    return regs


@router.get("/run/{filename}/gate")
def ci_gate(filename: str):
    report = _ensure_report(filename)
    passed = report.get("critical", 0) == 0
    return {
        "pass":          passed,
        "critical":      report.get("critical", 0),
        "warning":       report.get("warning", 0),
        "total":         report.get("total", 0),
        "summary":       f"{report.get('critical',0)} critical, {report.get('warning',0)} warnings",
        "recommendation": "Deploy blocked — fix critical bugs first." if not passed else "Clear to deploy.",
    }


@router.post("/run/{filename}/resolve/{bug_id}")
def resolve_bug(filename: str, bug_id: str):
    reports = _get_all_reports()
    report  = reports.get(filename)
    if not report:
        raise HTTPException(404, "Report not found")
    for bug in (report.get("bugs") or []):
        if bug.get("bugId") == bug_id:
            bug["resolved"] = True
            save_json(BUG_REPORTS_FILE(), reports)
            return {"success": True}
    raise HTTPException(404, "Bug not found")
