from fastapi import APIRouter
from backend.services.run_loader import get_all_runs, get_all_summaries, run_count
from backend.services.aggregator import (
    compute_overall_pass_rate, compute_metric_summary,
    compute_error_rate_trends, compute_cost_breakdown,
    compute_token_breakdown, compute_latency_percentiles,
)
from backend.config import PASS_RATE_ALERT_THRESHOLD

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard():
    runs = get_all_runs()
    if not runs:
        return {"totalRuns": 0, "overallPassRate": 0, "totalCost": 0,
                "avgDuration": 0, "lastRunTime": None, "errorRate": 0, "tokenTotal": 0,
                "alert": False, "alertMessage": ""}

    total_cost   = sum(r.get("evaluationCost") or 0.0 for r in runs)
    avg_duration = round(sum(r.get("runDuration") or 0.0 for r in runs) / len(runs), 2)
    pass_rate    = compute_overall_pass_rate(runs)
    err_trends   = compute_error_rate_trends(runs)
    avg_err_rate = round(sum(e["errorRate"] for e in err_trends) / len(err_trends), 4) if err_trends else 0.0

    token_data   = compute_token_breakdown(runs)
    total_tokens = sum(t["totalTokens"] for t in token_data)

    alert = pass_rate < PASS_RATE_ALERT_THRESHOLD
    return {
        "totalRuns":       run_count(),
        "overallPassRate": pass_rate,
        "totalCost":       round(total_cost, 6),
        "avgDuration":     avg_duration,
        "lastRunTime":     runs[0]["_datetime"] if runs else None,
        "errorRate":       avg_err_rate,
        "tokenTotal":      total_tokens,
        "alert":           alert,
        "alertMessage":    f"Pass rate {pass_rate:.0%} is below threshold {PASS_RATE_ALERT_THRESHOLD:.0%}" if alert else "",
    }


@router.get("/sparklines")
def get_sparklines():
    runs = get_all_summaries()[:10]
    return [{
        "filename":  r["filename"],
        "datetime":  r["datetime"],
        "passRate":  r["passRate"],
        "cost":      r["evaluationCost"],
        "errorRate": r["errorRate"],
        "duration":  r["runDuration"],
    } for r in reversed(runs)]


@router.get("/prebuilt")
def get_prebuilt_sections():
    runs = get_all_runs()
    if not runs:
        return {}

    # Section 1: Traces
    traces_data = [{"filename": r["_filename"], "datetime": r["_datetime"],
                    "traceCount": sum(1 for tc in (r.get("testCases") or []) if tc.get("trace")),
                    "errorRate": r["_errorRate"]} for r in runs[-20:]]

    # Section 2: LLM Calls
    llm_calls = []
    for r in runs[-20:]:
        count = sum(len(tc.get("trace", {}).get("llmSpans") or [])
                    for tc in (r.get("testCases") or []) if tc.get("trace"))
        llm_calls.append({"filename": r["_filename"], "datetime": r["_datetime"], "llmCallCount": count})

    # Section 3: Cost & Tokens
    token_rows = compute_token_breakdown(runs[-20:])

    # Section 4: Top tools
    tool_stats: dict = {}
    for r in runs:
        for tc in (r.get("testCases") or []):
            trace = tc.get("trace")
            if not trace:
                continue
            for span in (trace.get("toolSpans") or []):
                n = span.get("name") or "unknown"
                tool_stats.setdefault(n, {"name": n, "calls": 0, "errors": 0})
                tool_stats[n]["calls"] += 1
                if (span.get("status") or "").upper() == "ERRORED":
                    tool_stats[n]["errors"] += 1
    top_tools = sorted(tool_stats.values(), key=lambda x: -x["calls"])[:5]

    # Section 5: Run types (span type distribution)
    span_type_counts: dict = {}
    for r in runs:
        for tc in (r.get("testCases") or []):
            trace = tc.get("trace")
            if not trace:
                continue
            for bkt, stype in [("llmSpans", "llm"), ("retrieverSpans", "retriever"),
                                ("toolSpans", "tool"), ("agentSpans", "agent"), ("baseSpans", "base")]:
                n = len(trace.get(bkt) or [])
                span_type_counts[stype] = span_type_counts.get(stype, 0) + n
    run_types = [{"type": k, "count": v} for k, v in span_type_counts.items()]

    return {
        "traces":    traces_data,
        "llmCalls":  llm_calls,
        "costTokens": token_rows,
        "tools":     top_tools,
        "runTypes":  run_types,
    }
