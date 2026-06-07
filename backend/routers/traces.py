from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from backend.services.run_loader import get_all_runs
from backend.services.aggregator import compute_trace_stats

router = APIRouter(prefix="/api/traces", tags=["traces"])


@router.get("/stats")
def trace_stats(env: Optional[str] = None):
    runs = get_all_runs()
    if env and env != "all":
        runs = [r for r in runs if r["_environment"] == env]
    return compute_trace_stats(runs)


@router.get("")
def list_traces(
    search:    Optional[str] = None,
    env:       Optional[str] = None,
    status:    Optional[str] = None,
    span_type: Optional[str] = None,
    min_ms:    Optional[float] = None,
    max_ms:    Optional[float] = None,
    page:      int = Query(1, ge=1),
    limit:     int = Query(50, ge=1, le=200),
):
    rows = []
    for run in get_all_runs():
        if env and env != "all" and run["_environment"] != env:
            continue
        for tc in (run.get("testCases") or []):
            trace = tc.get("trace")
            if not trace:
                continue
            ts = (trace.get("status") or "OK").upper()
            if status and status != "all" and ts != status.upper():
                continue
            if search:
                q = search.lower()
                match = (q in (trace.get("name") or "").lower() or
                         q in tc.get("name", "").lower() or
                         q in str(trace.get("tags") or "").lower() or
                         q in (tc.get("input") or "").lower())
                if not match:
                    continue
            # span type filter
            st_counts = _span_type_counts(trace)
            if span_type and span_type != "all" and st_counts.get(span_type, 0) == 0:
                continue
            # duration filter
            dur_ms = _trace_duration_ms(trace)
            if min_ms is not None and (dur_ms is None or dur_ms < min_ms):
                continue
            if max_ms is not None and (dur_ms is None or dur_ms > max_ms):
                continue
            rows.append({
                "traceId":        trace.get("uuid"),
                "traceName":      trace.get("name"),
                "testCase":       tc.get("name"),
                "input":          (tc.get("input") or "")[:120],
                "filename":       run["_filename"],
                "datetime":       run["_datetime"],
                "status":         ts,
                "startTime":      trace.get("startTime"),
                "endTime":        trace.get("endTime"),
                "durationMs":     dur_ms,
                "userId":         trace.get("userId"),
                "threadId":       trace.get("threadId"),
                "tags":           trace.get("tags") or [],
                "spanCount":      _span_count(trace),
                "spanTypeCounts": st_counts,
                "totalTokens":    _trace_tokens(trace),
                "errorMsg":       _first_error(trace),
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


def _span_type_counts(trace: dict) -> dict:
    return {
        "llm":       len(trace.get("llmSpans")       or []),
        "retriever": len(trace.get("retrieverSpans")  or []),
        "tool":      len(trace.get("toolSpans")       or []),
        "agent":     len(trace.get("agentSpans")      or []),
        "base":      len(trace.get("baseSpans")       or []),
    }


def _trace_duration_ms(trace: dict) -> Optional[float]:
    from datetime import datetime
    s, e = trace.get("startTime"), trace.get("endTime")
    if not s or not e:
        return None
    try:
        return round((datetime.fromisoformat(e.replace("Z","+00:00")) -
                      datetime.fromisoformat(s.replace("Z","+00:00"))).total_seconds() * 1000, 1)
    except Exception:
        return None


def _trace_tokens(trace: dict) -> int:
    total = 0
    for span in (trace.get("llmSpans") or []):
        total += (span.get("inputTokenCount") or 0) + (span.get("outputTokenCount") or 0)
    return total


def _first_error(trace: dict) -> Optional[str]:
    for k in ("llmSpans", "retrieverSpans", "toolSpans", "agentSpans", "baseSpans"):
        for span in (trace.get(k) or []):
            if (span.get("status") or "").upper() == "ERRORED" and span.get("error"):
                return str(span["error"])[:200]
    return None


def _all_spans(trace: dict) -> list:
    spans = []
    for k in ("baseSpans", "agentSpans", "llmSpans", "retrieverSpans", "toolSpans"):
        spans.extend(trace.get(k) or [])
    return spans
