from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from backend.services.run_loader import get_all_runs

router = APIRouter(prefix="/api/traces", tags=["traces"])


@router.get("")
def list_traces(
    search:   Optional[str] = None,
    env:      Optional[str] = None,
    status:   Optional[str] = None,
    page:     int = Query(1, ge=1),
    limit:    int = Query(50, ge=1, le=200),
):
    rows = []
    for run in get_all_runs():
        if env and env != "all" and run["_environment"] != env:
            continue
        for tc in (run.get("testCases") or []):
            trace = tc.get("trace")
            if not trace:
                continue
            if status and (trace.get("status") or "").upper() != status.upper():
                continue
            if search:
                q = search.lower()
                match = (q in (trace.get("name") or "").lower() or
                         q in tc.get("name", "").lower() or
                         q in str(trace.get("tags") or "").lower())
                if not match:
                    continue
            rows.append({
                "traceId":   trace.get("uuid"),
                "traceName": trace.get("name"),
                "testCase":  tc.get("name"),
                "filename":  run["_filename"],
                "datetime":  run["_datetime"],
                "status":    trace.get("status"),
                "startTime": trace.get("startTime"),
                "endTime":   trace.get("endTime"),
                "userId":    trace.get("userId"),
                "threadId":  trace.get("threadId"),
                "tags":      trace.get("tags"),
                "spanCount": _span_count(trace),
            })

    total = len(rows)
    start = (page - 1) * limit
    return {"data": rows[start:start + limit], "total": total, "page": page}


@router.get("/errors")
def errored_traces():
    rows = []
    for run in get_all_runs():
        for tc in (run.get("testCases") or []):
            trace = tc.get("trace")
            if not trace:
                continue
            all_spans = _all_spans(trace)
            errored   = [s for s in all_spans if (s.get("status") or "").upper() == "ERRORED"]
            if errored or (trace.get("status") or "").upper() == "ERRORED":
                rows.append({
                    "traceId":      trace.get("uuid"),
                    "testCase":     tc.get("name"),
                    "filename":     run["_filename"],
                    "erroredSpans": len(errored),
                    "firstError":   errored[0].get("error") if errored else None,
                })
    return rows


@router.get("/search")
def search_traces(q: str):
    q_lower = q.lower()
    results = []
    for run in get_all_runs():
        for tc in (run.get("testCases") or []):
            trace = tc.get("trace")
            if not trace:
                continue
            for span in _all_spans(trace):
                if (q_lower in (span.get("name") or "").lower() or
                    q_lower in (span.get("model") or "").lower() or
                    q_lower in str(span.get("tags") or "").lower()):
                    results.append({
                        "spanName":  span.get("name"),
                        "spanType":  span.get("type"),
                        "model":     span.get("model"),
                        "testCase":  tc.get("name"),
                        "filename":  run["_filename"],
                        "traceId":   trace.get("uuid"),
                    })
    return results[:100]


@router.get("/{trace_id}")
def get_trace(trace_id: str):
    for run in get_all_runs():
        for tc in (run.get("testCases") or []):
            trace = tc.get("trace")
            if trace and trace.get("uuid") == trace_id:
                return trace
    raise HTTPException(404, f"Trace '{trace_id}' not found")


def _span_count(trace: dict) -> int:
    return sum(len(trace.get(k) or [])
               for k in ("baseSpans", "agentSpans", "llmSpans", "retrieverSpans", "toolSpans"))


def _all_spans(trace: dict) -> list:
    spans = []
    for k in ("baseSpans", "agentSpans", "llmSpans", "retrieverSpans", "toolSpans"):
        spans.extend(trace.get(k) or [])
    return spans
