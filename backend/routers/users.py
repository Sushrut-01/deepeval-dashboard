from fastapi import APIRouter, HTTPException
from backend.services.run_loader import get_all_runs
from backend.services.aggregator import compute_user_stats

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
def list_users():
    return compute_user_stats(get_all_runs())


@router.get("/{user_id}")
def get_user(user_id: str):
    runs = get_all_runs()
    traces = []
    total_cost = 0.0
    for run in runs:
        for tc in (run.get("testCases") or []):
            trace = tc.get("trace")
            if not trace or trace.get("userId") != user_id:
                continue
            traces.append({
                "traceId":  trace.get("uuid"),
                "testCase": tc.get("name"),
                "filename": run["_filename"],
                "datetime": run["_datetime"],
                "status":   trace.get("status"),
                "threadId": trace.get("threadId"),
            })
    if not traces:
        raise HTTPException(404, f"User '{user_id}' not found")
    return {"userId": user_id, "traceCount": len(traces), "traces": traces}
