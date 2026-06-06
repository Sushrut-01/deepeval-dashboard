from fastapi import APIRouter
from backend.services.run_loader import get_all_runs
from backend.services.aggregator import compute_daily_usage, compute_usage_summary

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/daily")
def daily_usage():
    return compute_daily_usage(get_all_runs())


@router.get("/summary")
def usage_summary():
    return compute_usage_summary(get_all_runs())


@router.get("/by-env")
def by_env():
    from backend.services.aggregator import _group_by_field
    return _group_by_field(get_all_runs(), "_environment")


@router.get("/by-version")
def by_version():
    from backend.services.aggregator import _group_by_field
    return _group_by_field(get_all_runs(), "_version")
