"""
Aggregation functions: trends, averages, cost breakdowns, latency percentiles,
regression detection, token breakdowns, user stats, version comparison.
All functions operate on already-parsed run dicts from run_loader.
"""
import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from backend.services.run_loader import get_all_runs, get_all_spans_from_run, get_all_test_cases


# ── Pass Rate ─────────────────────────────────────────────────────────────────

def compute_overall_pass_rate(runs: List[dict]) -> float:
    total_passed = sum(r.get("testPassed", 0) for r in runs)
    total_cases  = sum(r.get("_caseCount", 0) for r in runs)
    return round(total_passed / total_cases, 4) if total_cases else 0.0


# ── Metric Trends ─────────────────────────────────────────────────────────────

def compute_metric_trends(runs: List[dict], group_by: str = None) -> List[dict]:
    """Per-metric avg score per run over time.
    Returns list of {datetime, filename, metric, avg, passes, fails} dicts.
    """
    rows = []
    for run in runs:
        for ms in (run.get("metricsScores") or []):
            row = {
                "datetime":    run["_datetime"],
                "filename":    run["_filename"],
                "mtime":       run["_mtime"],
                "environment": run["_environment"],
                "version":     run["_version"],
                "metric":      ms["metric"],
                "avg":         ms["avg"],
                "passes":      ms["passes"],
                "fails":       ms["fails"],
                "errors":      ms.get("errors", 0),
                "passRate":    round(ms["passes"] / (ms["passes"] + ms["fails"]), 4)
                               if (ms["passes"] + ms["fails"]) else 0.0,
            }
            if group_by:
                row["groupValue"] = run.get(f"_{group_by}", run.get(group_by, "unknown"))
            rows.append(row)
    return rows


def compute_metric_summary(runs: List[dict]) -> List[dict]:
    """All-time per-metric: avg, best, worst, total passes/fails, trend."""
    metric_data: Dict[str, list] = defaultdict(list)
    metric_passes: Dict[str, int] = defaultdict(int)
    metric_fails:  Dict[str, int] = defaultdict(int)
    metric_errors: Dict[str, int] = defaultdict(int)

    for run in runs:
        for ms in (run.get("metricsScores") or []):
            name = ms["metric"]
            metric_data[name].extend(ms.get("scores") or [])
            metric_passes[name] += ms.get("passes", 0)
            metric_fails[name]  += ms.get("fails", 0)
            metric_errors[name] += ms.get("errors", 0)

    result = []
    for name, scores in metric_data.items():
        if not scores:
            continue
        avg   = round(sum(scores) / len(scores), 4)
        best  = round(max(scores), 4)
        worst = round(min(scores), 4)
        total = metric_passes[name] + metric_fails[name]
        result.append({
            "metric":   name,
            "avg":      avg,
            "best":     best,
            "worst":    worst,
            "passes":   metric_passes[name],
            "fails":    metric_fails[name],
            "errors":   metric_errors[name],
            "total":    total,
            "passRate": round(metric_passes[name] / total, 4) if total else 0.0,
            "trend":    _calc_trend(scores),
        })
    return sorted(result, key=lambda x: x["metric"])


def compute_score_distribution(runs: List[dict], metric_name: str) -> List[dict]:
    """Histogram buckets [0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0]."""
    buckets = [0, 0, 0, 0, 0]
    labels  = ["0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]
    for run in runs:
        for ms in (run.get("metricsScores") or []):
            if ms["metric"] == metric_name:
                for score in (ms.get("scores") or []):
                    idx = min(int(score * 5), 4)
                    buckets[idx] += 1
    return [{"label": labels[i], "count": buckets[i]} for i in range(5)]


def _calc_trend(scores: list) -> str:
    if len(scores) < 2:
        return "stable"
    recent = scores[-3:] if len(scores) >= 3 else scores
    prev   = scores[-6:-3] if len(scores) >= 6 else scores[:max(1, len(scores)-3)]
    if not prev:
        return "stable"
    r_avg = sum(recent) / len(recent)
    p_avg = sum(prev)   / len(prev)
    if r_avg - p_avg > 0.05:
        return "up"
    if p_avg - r_avg > 0.05:
        return "down"
    return "stable"


# ── Regression Detection ──────────────────────────────────────────────────────

def detect_regressions(runs: List[dict]) -> List[dict]:
    """Find test cases that passed in last 3 runs but now fail, or score dropped > 0.15."""
    if len(runs) < 2:
        return []

    regressions = []
    latest = runs[0]
    history = runs[1:min(4, len(runs))]

    # Build score history per (test_case, metric)
    hist_scores: Dict[Tuple[str, str], list] = defaultdict(list)
    hist_pass:   Dict[str, list] = defaultdict(list)

    for run in history:
        for tc in get_all_test_cases(run):
            name = tc.get("name", "")
            hist_pass[name].append(tc.get("success"))
            for m in (tc.get("metricsData") or []):
                if m.get("score") is not None:
                    hist_scores[(name, m["name"])].append(m["score"])

    for tc in get_all_test_cases(latest):
        name = tc.get("name", "")
        # Pass → Fail flip
        prev_passes = hist_pass.get(name, [])
        if prev_passes and all(p is True for p in prev_passes) and tc.get("success") is False:
            regressions.append({
                "type":       "PASS_TO_FAIL",
                "testCase":   name,
                "filename":   latest["_filename"],
                "prevPasses": len(prev_passes),
                "details":    "Test case flipped from PASS to FAIL",
            })
        # Score drop
        for m in (tc.get("metricsData") or []):
            prev = hist_scores.get((name, m["name"]), [])
            if prev and m.get("score") is not None:
                prev_avg = sum(prev) / len(prev)
                drop = prev_avg - m["score"]
                if drop > 0.15:
                    regressions.append({
                        "type":      "SCORE_DROP",
                        "testCase":  name,
                        "metric":    m["name"],
                        "filename":  latest["_filename"],
                        "prevAvg":   round(prev_avg, 3),
                        "current":   round(m["score"], 3),
                        "drop":      round(drop, 3),
                        "details":   f"Score dropped {drop:.2f} vs prev avg {prev_avg:.2f}",
                    })

    return regressions


# ── Cost & Token Breakdown ────────────────────────────────────────────────────

def compute_cost_breakdown(runs: List[dict]) -> dict:
    by_model: Dict[str, float] = defaultdict(float)
    by_tag:   Dict[str, float] = defaultdict(float)
    by_env:   Dict[str, float] = defaultdict(float)
    by_run:   list = []

    for run in runs:
        run_cost = 0.0
        for span in get_all_spans_from_run(run):
            cost = _span_cost(span)
            run_cost += cost
            model = span.get("model") or "unknown"
            by_model[model] += cost
            for tag in (span.get("tags") or []):
                by_tag[tag] += cost
        by_env[run["_environment"]] += run_cost or run.get("evaluationCost", 0.0)
        by_run.append({
            "filename": run["_filename"],
            "datetime": run["_datetime"],
            "cost":     round(run_cost or run.get("evaluationCost", 0.0), 6),
        })

    return {
        "byModel": [{"model": k, "cost": round(v, 6)} for k, v in sorted(by_model.items(), key=lambda x: -x[1])],
        "byTag":   [{"tag":   k, "cost": round(v, 6)} for k, v in sorted(by_tag.items(), key=lambda x: -x[1])],
        "byEnv":   [{"env":   k, "cost": round(v, 6)} for k, v in sorted(by_env.items(), key=lambda x: -x[1])],
        "byRun":   by_run,
    }


def compute_token_breakdown(runs: List[dict]) -> List[dict]:
    rows = []
    for run in runs:
        inp = out = cached = 0.0
        for span in get_all_spans_from_run(run):
            if span.get("type") == "llm":
                inp    += span.get("inputTokenCount")  or 0.0
                out    += span.get("outputTokenCount") or 0.0
        rows.append({
            "filename":    run["_filename"],
            "datetime":    run["_datetime"],
            "inputTokens": int(inp),
            "outputTokens": int(out),
            "cachedTokens": int(cached),
            "totalTokens":  int(inp + out + cached),
        })
    return rows


def compute_cost_per_user(runs: List[dict]) -> List[dict]:
    user_cost: Dict[str, float] = defaultdict(float)
    for run in runs:
        for tc in (run.get("testCases") or []):
            trace = tc.get("trace")
            if not trace:
                continue
            uid = trace.get("userId")
            if not uid:
                continue
            for span in _all_spans_from_trace(trace):
                user_cost[uid] += _span_cost(span)
    return [{"userId": k, "cost": round(v, 6)}
            for k, v in sorted(user_cost.items(), key=lambda x: -x[1])[:20]]


def _span_cost(span: dict) -> float:
    cpi = span.get("costPerInputToken")  or 0.0
    cpo = span.get("costPerOutputToken") or 0.0
    inp = span.get("inputTokenCount")    or 0.0
    out = span.get("outputTokenCount")   or 0.0
    return cpi * inp + cpo * out


# ── Latency Percentiles ───────────────────────────────────────────────────────

def compute_latency_percentiles(runs: List[dict]) -> dict:
    by_type: Dict[str, list] = defaultdict(list)
    for run in runs:
        for span in get_all_spans_from_run(run):
            dur = _span_duration_ms(span)
            if dur is not None:
                by_type[span.get("type", "base")].append(dur)

    result = {}
    for span_type, durations in by_type.items():
        durations.sort()
        result[span_type] = {
            "p50": _percentile(durations, 50),
            "p95": _percentile(durations, 95),
            "p99": _percentile(durations, 99),
            "avg": round(sum(durations) / len(durations), 2) if durations else 0,
            "count": len(durations),
        }
    return result


def compute_latency_trends(runs: List[dict]) -> List[dict]:
    rows = []
    for run in runs:
        by_type: Dict[str, list] = defaultdict(list)
        for span in get_all_spans_from_run(run):
            dur = _span_duration_ms(span)
            if dur is not None:
                by_type[span.get("type", "base")].append(dur)
        row = {"filename": run["_filename"], "datetime": run["_datetime"]}
        for stype, durs in by_type.items():
            if durs:
                row[f"{stype}_avg"] = round(sum(durs) / len(durs), 2)
                row[f"{stype}_p95"] = _percentile(sorted(durs), 95)
        rows.append(row)
    return rows


def get_slowest_spans(runs: List[dict], limit: int = 20) -> List[dict]:
    spans_with_meta = []
    for run in runs:
        for span in get_all_spans_from_run(run):
            dur = _span_duration_ms(span)
            if dur is not None:
                spans_with_meta.append({
                    "name":     span.get("name"),
                    "type":     span.get("type"),
                    "filename": run["_filename"],
                    "datetime": run["_datetime"],
                    "duration": dur,
                    "status":   span.get("status"),
                    "model":    span.get("model"),
                })
    return sorted(spans_with_meta, key=lambda x: -x["duration"])[:limit]


def _span_duration_ms(span: dict) -> Optional[float]:
    from datetime import datetime
    s = span.get("startTime")
    e = span.get("endTime")
    if not s or not e:
        return None
    try:
        fmt_s = s.replace("Z", "+00:00")
        fmt_e = e.replace("Z", "+00:00")
        dt_s = datetime.fromisoformat(fmt_s)
        dt_e = datetime.fromisoformat(fmt_e)
        return round((dt_e - dt_s).total_seconds() * 1000, 2)
    except Exception:
        return None


def _percentile(sorted_data: list, pct: float) -> float:
    if not sorted_data:
        return 0.0
    idx = (pct / 100) * (len(sorted_data) - 1)
    lo  = int(idx)
    hi  = lo + 1
    if hi >= len(sorted_data):
        return round(sorted_data[-1], 2)
    frac = idx - lo
    return round(sorted_data[lo] + frac * (sorted_data[hi] - sorted_data[lo]), 2)


# ── Usage / Platform Stats ────────────────────────────────────────────────────

def compute_daily_usage(runs: List[dict]) -> List[dict]:
    from collections import Counter
    import datetime

    day_runs:   Counter = Counter()
    day_spans:  Counter = Counter()
    day_tokens: Counter = Counter()
    day_cost:   Dict[str, float] = defaultdict(float)

    for run in runs:
        day = run["_datetime"][:10]  # YYYY-MM-DD
        day_runs[day] += 1
        all_spans = get_all_spans_from_run(run)
        day_spans[day] += len(all_spans)
        for span in all_spans:
            day_tokens[day] += int((span.get("inputTokenCount") or 0) + (span.get("outputTokenCount") or 0))
            day_cost[day]   += _span_cost(span)

    all_days = sorted(set(list(day_runs.keys()) + list(day_spans.keys())))
    return [{
        "date":   d,
        "runs":   day_runs[d],
        "spans":  day_spans[d],
        "tokens": day_tokens[d],
        "cost":   round(day_cost[d], 6),
    } for d in all_days]


def compute_usage_summary(runs: List[dict]) -> dict:
    total_spans  = sum(len(get_all_spans_from_run(r)) for r in runs)
    total_tokens = sum(
        int((s.get("inputTokenCount") or 0) + (s.get("outputTokenCount") or 0))
        for r in runs for s in get_all_spans_from_run(r)
    )
    total_cost = sum(r.get("evaluationCost") or 0.0 for r in runs)
    return {
        "totalRuns":   len(runs),
        "totalSpans":  total_spans,
        "totalTokens": total_tokens,
        "totalCost":   round(total_cost, 6),
        "envBreakdown": _group_by_field(runs, "_environment"),
        "versionBreakdown": _group_by_field(runs, "_version"),
    }


def _group_by_field(runs: list, field: str) -> List[dict]:
    groups: Dict[str, dict] = defaultdict(lambda: {"runs": 0, "passed": 0, "failed": 0, "cost": 0.0})
    for r in runs:
        key = r.get(field, "unknown")
        groups[key]["runs"] += 1
        groups[key]["passed"] += r.get("testPassed", 0)
        groups[key]["failed"] += r.get("testFailed", 0)
        groups[key]["cost"]   += r.get("evaluationCost") or 0.0
    return [{"value": k, **v} for k, v in groups.items()]


# ── User Stats ────────────────────────────────────────────────────────────────

def compute_user_stats(runs: List[dict]) -> List[dict]:
    user_data: Dict[str, dict] = defaultdict(lambda: {
        "traceCount": 0, "sessionIds": set(), "cost": 0.0, "lastSeen": ""
    })
    for run in runs:
        for tc in (run.get("testCases") or []):
            trace = tc.get("trace")
            if not trace:
                continue
            uid = trace.get("userId")
            if not uid:
                continue
            user_data[uid]["traceCount"] += 1
            if trace.get("threadId"):
                user_data[uid]["sessionIds"].add(trace["threadId"])
            for span in _all_spans_from_trace(trace):
                user_data[uid]["cost"] += _span_cost(span)
            ts = trace.get("startTime", "")
            if ts > user_data[uid]["lastSeen"]:
                user_data[uid]["lastSeen"] = ts

    return [{
        "userId":       uid,
        "traceCount":   d["traceCount"],
        "sessionCount": len(d["sessionIds"]),
        "cost":         round(d["cost"], 6),
        "lastSeen":     d["lastSeen"],
    } for uid, d in sorted(user_data.items(), key=lambda x: -x[1]["traceCount"])]


def _all_spans_from_trace(trace: dict) -> list:
    spans = []
    for bucket in ("baseSpans", "agentSpans", "llmSpans", "retrieverSpans", "toolSpans"):
        spans.extend(trace.get(bucket) or [])
    return spans


# ── Compare ───────────────────────────────────────────────────────────────────

def compare_runs(runs: List[dict]) -> List[dict]:
    result = []
    for run in runs:
        metrics = {}
        for ms in (run.get("metricsScores") or []):
            total = ms["passes"] + ms["fails"]
            metrics[ms["metric"]] = {
                "avg":      ms["avg"],
                "passes":   ms["passes"],
                "fails":    ms["fails"],
                "passRate": round(ms["passes"] / total, 4) if total else 0.0,
            }
        result.append({
            "filename":    run["_filename"],
            "datetime":    run["_datetime"],
            "environment": run["_environment"],
            "version":     run["_version"],
            "passRate":    run["_passRate"],
            "cost":        run.get("evaluationCost", 0.0),
            "duration":    run.get("runDuration", 0.0),
            "passed":      run.get("testPassed", 0),
            "failed":      run.get("testFailed", 0),
            "metrics":     metrics,
        })
    return result


def compare_test_case(runs: List[dict], case_name: str) -> List[dict]:
    result = []
    for run in runs:
        for tc in get_all_test_cases(run):
            if tc.get("name") == case_name:
                result.append({
                    "filename":  run["_filename"],
                    "datetime":  run["_datetime"],
                    "version":   run["_version"],
                    "success":   tc.get("success"),
                    "metrics":   {
                        m["name"]: {"score": m.get("score"), "success": m.get("success")}
                        for m in (tc.get("metricsData") or [])
                    },
                })
    return result


# ── Error Rate ────────────────────────────────────────────────────────────────

def compute_error_rate_trends(runs: List[dict]) -> List[dict]:
    rows = []
    for run in runs:
        all_spans = get_all_spans_from_run(run)
        errored   = sum(1 for s in all_spans if (s.get("status") or "").upper() == "ERRORED")
        rows.append({
            "filename":  run["_filename"],
            "datetime":  run["_datetime"],
            "total":     len(all_spans),
            "errored":   errored,
            "errorRate": round(errored / len(all_spans), 4) if all_spans else 0.0,
        })
    return rows
