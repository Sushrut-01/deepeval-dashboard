from fastapi import APIRouter, Query
from typing import List
from backend.services.run_loader import get_run
from backend.services.aggregator import compare_runs, compare_test_case

router = APIRouter(prefix="/api/compare", tags=["compare"])


@router.get("")
def compare(runs: str = Query(..., description="Comma-separated filenames")):
    filenames = [f.strip() for f in runs.split(",") if f.strip()][:4]
    run_data  = [r for f in filenames for r in [get_run(f)] if r]
    return compare_runs(run_data)


@router.get("/cases")
def compare_cases(
    runs:      str = Query(..., description="Comma-separated filenames"),
    case_name: str = Query(..., alias="case"),
):
    filenames = [f.strip() for f in runs.split(",") if f.strip()][:4]
    run_data  = [r for f in filenames for r in [get_run(f)] if r]
    return compare_test_case(run_data, case_name)
