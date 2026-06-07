from fastapi import APIRouter
from typing import Optional
from backend.services.run_loader import get_all_runs
from backend.services.aggregator import (
    compute_latency_percentiles, compute_latency_trends, get_slowest_spans,
    compute_loadtest_summary,
)

router = APIRouter(prefix="/api/latency", tags=["latency"])


@router.get("/percentiles")
def percentiles(env: Optional[str] = None, version: Optional[str] = None):
    runs = _filtered(env, version)
    return compute_latency_percentiles(runs)


@router.get("/trends")
def trends(env: Optional[str] = None, version: Optional[str] = None):
    runs = _filtered(env, version)
    return compute_latency_trends(runs)


@router.get("/slowest")
def slowest(limit: int = 20, span_type: Optional[str] = None):
    runs = get_all_runs()
    spans = get_slowest_spans(runs, limit * 3)
    if span_type:
        spans = [s for s in spans if s.get("type") == span_type]
    return spans[:limit]


def _filtered(env=None, version=None):
    runs = get_all_runs()
    if env and env != "all":
        runs = [r for r in runs if r["_environment"] == env]
    if version and version != "all":
        runs = [r for r in runs if r["_version"] == version]
    return runs


@router.get("/loadtest")
def loadtest(bot_type: Optional[str] = None):
    runs = get_all_runs()
    load_runs = [r for r in runs if (r.get("_filename") or "").startswith("test_run_loadtest_")]
    if bot_type and bot_type != "all":
        load_runs = [r for r in load_runs if (r.get("hyperparameters") or {}).get("bot_type") == bot_type]
    return compute_loadtest_summary(load_runs)


@router.get("/loadtest/trends")
def loadtest_trends(bot_type: Optional[str] = None):
    runs = get_all_runs()
    load_runs = [r for r in runs if (r.get("_filename") or "").startswith("test_run_loadtest_")]
    if bot_type and bot_type != "all":
        load_runs = [r for r in load_runs if (r.get("hyperparameters") or {}).get("bot_type") == bot_type]
    summary = compute_loadtest_summary(load_runs)
    return summary.get("trends", [])
