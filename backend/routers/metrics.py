from fastapi import APIRouter, Query
from typing import Optional
from backend.services.run_loader import get_all_runs
from backend.services.aggregator import (
    compute_metric_trends, compute_metric_summary,
    compute_score_distribution, detect_regressions,
    compute_metric_bot_comparison, compute_metric_heatmap,
)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/trends")
def metric_trends(
    env:      Optional[str] = None,
    version:  Optional[str] = None,
    group_by: Optional[str] = Query(None, description="tag|metadata|version|env"),
):
    runs = _filtered(env, version)
    return compute_metric_trends(runs, group_by=group_by)


@router.get("/summary")
def metric_summary(env: Optional[str] = None, version: Optional[str] = None):
    return compute_metric_summary(_filtered(env, version))


@router.get("/distribution/{metric_name}")
def score_distribution(metric_name: str, env: Optional[str] = None, version: Optional[str] = None):
    return compute_score_distribution(_filtered(env, version), metric_name)


@router.get("/regressions")
def regressions():
    runs = get_all_runs()
    return detect_regressions(runs)


@router.get("/grouped")
def grouped_metrics(group_by: str = "version", env: Optional[str] = None):
    runs = _filtered(env)
    return compute_metric_trends(runs, group_by=group_by)


@router.get("/bot-comparison")
def bot_comparison(
    env: Optional[str] = None,
    version: Optional[str] = None,
    group_by: Optional[str] = Query("auto", description="auto|evaluator|bot|version|env"),
):
    return compute_metric_bot_comparison(_filtered(env, version), group_by=group_by or "auto")


@router.get("/heatmap")
def metric_heatmap(env: Optional[str] = None, version: Optional[str] = None):
    return compute_metric_heatmap(_filtered(env, version))


def _filtered(env: Optional[str] = None, version: Optional[str] = None):
    runs = get_all_runs()
    # exclude pure load-test runs from metric analytics
    runs = [r for r in runs if not r["_filename"].startswith("test_run_loadtest_")]
    if env and env != "all":
        runs = [r for r in runs if r["_environment"] == env]
    if version and version != "all":
        runs = [r for r in runs if r["_version"] == version]
    return runs
