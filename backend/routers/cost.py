from fastapi import APIRouter
from typing import Optional
from backend.services.run_loader import get_all_runs
from backend.services.aggregator import (
    compute_cost_breakdown, compute_token_breakdown, compute_cost_per_user,
)

router = APIRouter(prefix="/api", tags=["cost"])


@router.get("/cost/breakdown")
def cost_breakdown(env: Optional[str] = None, version: Optional[str] = None):
    return compute_cost_breakdown(_filtered(env, version))


@router.get("/cost/trends")
def cost_trends(env: Optional[str] = None, version: Optional[str] = None):
    runs = _filtered(env, version)
    return [{"filename": r["_filename"], "datetime": r["_datetime"],
             "cost": r.get("evaluationCost") or 0.0} for r in runs]


@router.get("/tokens/breakdown")
def token_breakdown(env: Optional[str] = None, version: Optional[str] = None):
    return compute_token_breakdown(_filtered(env, version))


@router.get("/tokens/per-model")
def tokens_per_model():
    from collections import defaultdict
    runs = get_all_runs()
    model_tokens: dict = defaultdict(lambda: {"input": 0, "output": 0, "total": 0})
    for r in runs:
        from backend.services.run_loader import get_all_spans_from_run
        for span in get_all_spans_from_run(r):
            if span.get("type") == "llm":
                model = span.get("model") or "unknown"
                inp = int(span.get("inputTokenCount") or 0)
                out = int(span.get("outputTokenCount") or 0)
                model_tokens[model]["input"]  += inp
                model_tokens[model]["output"] += out
                model_tokens[model]["total"]  += inp + out
    return [{"model": k, **v} for k, v in sorted(model_tokens.items(), key=lambda x: -x[1]["total"])]


@router.get("/cost/per-user")
def cost_per_user():
    return compute_cost_per_user(get_all_runs())


def _filtered(env=None, version=None):
    runs = get_all_runs()
    if env and env != "all":
        runs = [r for r in runs if r["_environment"] == env]
    if version and version != "all":
        runs = [r for r in runs if r["_version"] == version]
    return runs
