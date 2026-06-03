from fastapi import APIRouter
from typing import Optional
from backend.services.run_loader import get_all_runs
from backend.services.aggregator import (
    compute_latency_percentiles, compute_latency_trends, get_slowest_spans,
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
