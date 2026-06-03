"""Metrics API — external consumption (Grafana, billing, rate-limiters)."""
from fastapi import APIRouter, Query
from typing import Optional
from backend.services.run_loader import get_all_runs
from backend.services.aggregator import compute_metric_summary, compute_usage_summary

router = APIRouter(prefix="/api/v1", tags=["metrics_export"])


@router.get("/metrics-export")
def export_metrics(
    env:     Optional[str] = None,
    version: Optional[str] = None,
    metric:  Optional[str] = None,
    from_:   Optional[str] = Query(None, alias="from"),
    to:      Optional[str] = None,
):
    runs = get_all_runs()
    if env and env != "all":
        runs = [r for r in runs if r["_environment"] == env]
    if version and version != "all":
        runs = [r for r in runs if r["_version"] == version]
    if from_:
        runs = [r for r in runs if r["_datetime"] >= from_]
    if to:
        runs = [r for r in runs if r["_datetime"] <= to]

    summary  = compute_metric_summary(runs)
    usage    = compute_usage_summary(runs)

    if metric:
        summary = [s for s in summary if s["metric"].lower() == metric.lower()]

    return {
        "metrics": summary,
        "usage":   usage,
        "filters": {"env": env, "version": version, "from": from_, "to": to},
    }
