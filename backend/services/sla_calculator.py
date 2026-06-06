"""
SLA/SLI/SLO Calculator.
SLO  = target definition (stored in slos.json)
SLI  = measured value right now
SLA  = compliance % over a time window
"""
import time
from typing import Any, Dict, List, Optional

from backend.config import HISTORY_FOLDER
from backend.services.file_store import load_or_default, save_json
from backend.services.run_loader import get_all_runs, get_all_spans_from_run
from backend.services.aggregator import _percentile, _span_duration_ms

SLO_FILE    = lambda: HISTORY_FOLDER / "slos.json"
BREACH_FILE = lambda: HISTORY_FOLDER / "sla_breaches.json"


# ── SLO types ─────────────────────────────────────────────────────────────────
# metric_pass_rate   → passes/(passes+fails) for a named metric, last N runs
# metric_avg_score   → avg score for a named metric, last N runs
# latency_p95        → P95 latency (ms) for a span_type, last N runs
# latency_p99        → P99 latency (ms) for a span_type, last N runs
# error_rate         → errored_spans/total_spans, last N runs
# cost_per_run       → avg evaluationCost per run, last N runs
# pass_rate          → overall testPassed/(testPassed+testFailed), last N runs


def compute_sli(slo: dict, runs: List[dict]) -> Optional[float]:
    """Compute the current SLI value for a given SLO definition."""
    n      = slo.get("windowRuns", 10)
    recent = runs[:n]
    if not recent:
        return None

    stype = slo.get("type", "")

    if stype == "metric_pass_rate":
        metric = slo.get("metric", "")
        total_p = total_f = 0
        for run in recent:
            for ms in (run.get("metricsScores") or []):
                if ms.get("metric", "").lower() == metric.lower():
                    total_p += ms.get("passes", 0)
                    total_f += ms.get("fails",  0)
        denom = total_p + total_f
        return round(total_p / denom, 4) if denom else None

    if stype == "metric_avg_score":
        metric = slo.get("metric", "")
        scores = []
        for run in recent:
            for ms in (run.get("metricsScores") or []):
                if ms.get("metric", "").lower() == metric.lower():
                    scores.extend(ms.get("scores") or [])
        return round(sum(scores) / len(scores), 4) if scores else None

    if stype in ("latency_p95", "latency_p99"):
        span_type = slo.get("spanType", "llm")
        durations = []
        for run in recent:
            for span in get_all_spans_from_run(run):
                if span.get("type") == span_type:
                    d = _span_duration_ms(span)
                    if d is not None:
                        durations.append(d)
        if not durations:
            return None
        durations.sort()
        pct = 95 if stype == "latency_p95" else 99
        return _percentile(durations, pct)

    if stype == "error_rate":
        total = errored = 0
        for run in recent:
            spans = get_all_spans_from_run(run)
            total   += len(spans)
            errored += sum(1 for s in spans if (s.get("status") or "").upper() == "ERRORED")
        return round(errored / total, 4) if total else None

    if stype == "cost_per_run":
        costs = [(r.get("evaluationCost") or 0.0) for r in recent]
        return round(sum(costs) / len(costs), 6) if costs else None

    if stype == "pass_rate":
        p = sum(r.get("testPassed", 0) for r in recent)
        f = sum(r.get("testFailed", 0) for r in recent)
        return round(p / (p + f), 4) if (p + f) else None

    return None


def meets_slo(sli: Optional[float], slo: dict) -> Optional[bool]:
    """Return True if SLI meets the SLO target, False if breach, None if no data."""
    if sli is None:
        return None
    op     = slo.get("operator", ">=")
    target = float(slo.get("target", 0))
    if op == ">=": return sli >= target
    if op == "<=": return sli <= target
    if op == ">":  return sli >  target
    if op == "<":  return sli <  target
    if op == "==": return abs(sli - target) < 1e-9
    return None


def get_slo_status(project: Optional[str] = None) -> List[dict]:
    """Return all SLOs with their current SLI and status."""
    slos = load_or_default(SLO_FILE(), []) or []
    runs = get_all_runs()
    if project and project != "all":
        runs = [r for r in runs if r.get("_project") == project]

    result = []
    for slo in slos:
        if not slo.get("enabled", True):
            continue
        sli    = compute_sli(slo, runs)
        status = meets_slo(sli, slo)
        result.append({
            "id":          slo["id"],
            "name":        slo["name"],
            "type":        slo["type"],
            "metric":      slo.get("metric"),
            "spanType":    slo.get("spanType"),
            "operator":    slo.get("operator", ">="),
            "target":      slo.get("target"),
            "windowRuns":  slo.get("windowRuns", 10),
            "sli":         sli,
            "status":      "ok" if status else ("breach" if status is False else "no_data"),
            "enabled":     slo.get("enabled", True),
        })
    return result


def get_compliance(project: Optional[str] = None) -> dict:
    """Overall SLA compliance: % of SLOs currently passing."""
    statuses = get_slo_status(project)
    if not statuses:
        return {"total": 0, "passing": 0, "breaching": 0, "compliance": None,
                "errorBudget": None, "slos": []}
    passing   = sum(1 for s in statuses if s["status"] == "ok")
    breaching = sum(1 for s in statuses if s["status"] == "breach")
    total     = len(statuses)
    compliance = round(passing / total, 4) if total else None
    return {
        "total":      total,
        "passing":    passing,
        "breaching":  breaching,
        "compliance": compliance,
        "slos":       statuses,
    }


def get_sli_history(slo_id: str, project: Optional[str] = None) -> List[dict]:
    """SLI value per run for a specific SLO."""
    slos = load_or_default(SLO_FILE(), []) or []
    slo  = next((s for s in slos if s["id"] == slo_id), None)
    if not slo:
        return []

    runs = get_all_runs()
    if project and project != "all":
        runs = [r for r in runs if r.get("_project") == project]

    rows = []
    for i, run in enumerate(runs):
        # Compute SLI using a window ending at this run
        window = runs[i:i + slo.get("windowRuns", 10)]
        sli    = compute_sli(slo, window)
        status = meets_slo(sli, slo)
        rows.append({
            "filename": run["_filename"],
            "datetime": run["_datetime"],
            "sli":      sli,
            "target":   slo.get("target"),
            "status":   "ok" if status else ("breach" if status is False else "no_data"),
        })
    return list(reversed(rows))  # newest first for display, reversed for chart


def record_breach(slo: dict, sli: float, filename: str):
    """Save a breach event."""
    breaches = load_or_default(BREACH_FILE(), []) or []
    breaches.insert(0, {
        "sloId":    slo["id"],
        "sloName":  slo["name"],
        "filename": filename,
        "sli":      sli,
        "target":   slo.get("target"),
        "operator": slo.get("operator", ">="),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "resolved": False,
    })
    save_json(BREACH_FILE(), breaches[:200])  # keep last 200


def check_and_fire_breaches(filename: str):
    """Called after each new run — checks all SLOs and fires webhooks on breach."""
    runs     = get_all_runs()
    slos     = load_or_default(SLO_FILE(), []) or []
    breaches = load_or_default(BREACH_FILE(), []) or []

    for slo in slos:
        if not slo.get("enabled", True):
            continue
        sli    = compute_sli(slo, runs)
        status = meets_slo(sli, slo)

        if status is False:
            # New breach — check if already recorded for this run
            already = any(b["sloId"] == slo["id"] and b["filename"] == filename
                          for b in breaches[:10])
            if not already:
                record_breach(slo, sli, filename)
                try:
                    from backend.services.webhook_sender import fire_event
                    fire_event("slo_breach", {
                        "sloId":    slo["id"],
                        "sloName":  slo["name"],
                        "sli":      sli,
                        "target":   slo["target"],
                        "operator": slo.get("operator", ">="),
                        "filename": filename,
                    })
                except Exception:
                    pass
