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

def _detect_regressions_for_framework(latest: dict, history: List[dict]) -> List[dict]:
    """Compare `latest` run's test cases against up to 3 prior runs from the SAME evaluator framework."""
    regressions = []

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

    fw  = latest.get("_framework", "ragas")
    lbl = latest.get("_evaluatorLabel", "RAGAS Evaluator")

    for tc in get_all_test_cases(latest):
        name = tc.get("name", "")
        # Pass -> Fail flip
        prev_passes = hist_pass.get(name, [])
        if prev_passes and all(p is True for p in prev_passes) and tc.get("success") is False:
            regressions.append({
                "type":           "PASS_TO_FAIL",
                "testCase":       name,
                "filename":       latest["_filename"],
                "framework":      fw,
                "evaluatorLabel": lbl,
                "prevPasses":     len(prev_passes),
                "details":        "Test case flipped from PASS to FAIL",
            })
        # Score drop
        for m in (tc.get("metricsData") or []):
            prev = hist_scores.get((name, m["name"]), [])
            if prev and m.get("score") is not None:
                prev_avg = sum(prev) / len(prev)
                drop = prev_avg - m["score"]
                if drop > 0.15:
                    regressions.append({
                        "type":           "SCORE_DROP",
                        "testCase":       name,
                        "metric":         m["name"],
                        "filename":       latest["_filename"],
                        "framework":      fw,
                        "evaluatorLabel": lbl,
                        "prevAvg":        round(prev_avg, 3),
                        "current":        round(m["score"], 3),
                        "drop":           round(drop, 3),
                        "details":        f"Score dropped {drop:.2f} vs prev avg {prev_avg:.2f}",
                    })

    return regressions


def detect_regressions(runs: List[dict]) -> List[dict]:
    """Find test cases that passed in last 3 runs but now fail, or score dropped > 0.15.

    Scoped per-evaluator-framework: a run is only compared against its own
    framework's history (RAGAS vs RAGAS, Foundry vs Foundry, etc.), since
    metric names and scales differ across evaluators and a cross-framework
    comparison would be meaningless or spuriously empty.
    """
    if len(runs) < 2:
        return []

    by_framework: Dict[str, List[dict]] = defaultdict(list)
    for run in runs:
        by_framework[run.get("_framework", "ragas")].append(run)

    regressions: List[dict] = []
    for fw_runs in by_framework.values():
        if len(fw_runs) < 2:
            continue
        latest  = fw_runs[0]
        history = fw_runs[1:min(4, len(fw_runs))]
        regressions.extend(_detect_regressions_for_framework(latest, history))

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


def compute_metric_bot_comparison(runs: List[dict], group_by: str = "auto") -> dict:
    """Per-group per-metric avg score and pass rate for grouped bar comparison.

    group_by: "auto"      → bot_type if present, else evaluatorLabel
              "evaluator" → group by evaluatorLabel (_evaluatorLabel)
              "bot"       → group by bot_type hyperparameter
              "version"   → group by _version
              "env"       → group by _environment
    """
    from collections import defaultdict as _dd
    grp_metric: Dict[str, Dict[str, list]] = _dd(lambda: _dd(list))
    grp_pass:   Dict[str, Dict[str, int]]  = _dd(lambda: _dd(int))
    grp_fail:   Dict[str, Dict[str, int]]  = _dd(lambda: _dd(int))

    def _group_key(run: dict) -> str:
        hyper = run.get("hyperparameters") or {}
        bot_type = hyper.get("bot_type")
        if group_by == "evaluator":
            return run.get("_evaluatorLabel") or run.get("_framework", "Unknown")
        if group_by == "bot":
            return bot_type or "unknown-bot"
        if group_by == "version":
            return run.get("_version") or "no-version"
        if group_by == "env":
            return run.get("_environment") or "unknown"
        # auto: prefer bot_type, fall back to evaluator label
        if bot_type:
            return bot_type
        return run.get("_evaluatorLabel") or run.get("_framework", "unknown")

    for run in runs:
        key = _group_key(run)
        for ms in (run.get("metricsScores") or []):
            name = ms["metric"]
            grp_metric[key][name].extend(ms.get("scores") or [])
            grp_pass[key][name] += ms.get("passes", 0)
            grp_fail[key][name] += ms.get("fails", 0)

    all_metrics = sorted({m for bd in grp_metric.values() for m in bd})
    result = {}
    for grp, mdata in grp_metric.items():
        result[grp] = {}
        for m in all_metrics:
            scores = mdata.get(m, [])
            p = grp_pass[grp].get(m, 0)
            f = grp_fail[grp].get(m, 0)
            result[grp][m] = {
                "avg":      round(sum(scores) / len(scores), 4) if scores else None,
                "passRate": round(p / (p + f), 4) if (p + f) else None,
                "passes":   p,
                "fails":    f,
            }
    return {"bots": list(result.keys()), "metrics": all_metrics, "data": result, "groupBy": group_by}


def compute_metric_heatmap(runs: List[dict]) -> dict:
    """Metric × run grid: avg score per metric per run for heatmap."""
    rows = []
    for run in runs:
        row = {
            "filename":       run["_filename"],
            "datetime":       run["_datetime"],
            "framework":      run.get("_framework", "ragas"),
            "evaluatorLabel": run.get("_evaluatorLabel", "RAGAS Evaluator"),
        }
        for ms in (run.get("metricsScores") or []):
            scores = ms.get("scores") or []
            row[ms["metric"]] = round(sum(scores) / len(scores), 3) if scores else None
        rows.append(row)
    reserved = {"filename", "datetime", "framework", "evaluatorLabel"}
    all_metrics = sorted({k for r in rows for k in r if k not in reserved})
    return {"runs": rows, "metrics": all_metrics}


def compute_trace_stats(runs: List[dict]) -> dict:
    """Summary stats for the Tracer View page KPIs and charts."""
    from datetime import datetime as _dt
    total = errored = 0
    span_type_counts: Dict[str, int] = defaultdict(int)
    dur_buckets = {"<1s": 0, "1-5s": 0, "5-10s": 0, "10-30s": 0, "30s+": 0}
    total_tokens = 0
    all_durations = []

    for run in runs:
        for tc in (run.get("testCases") or []):
            trace = tc.get("trace")
            if not trace:
                continue
            total += 1
            st = (trace.get("status") or "").upper()
            if st == "ERRORED":
                errored += 1
            for bucket in ("llmSpans", "retrieverSpans", "toolSpans", "agentSpans", "baseSpans"):
                stype = bucket.replace("Spans", "").lower()
                spans = trace.get(bucket) or []
                span_type_counts[stype] += len(spans)
                for span in spans:
                    tok = (span.get("inputTokenCount") or 0) + (span.get("outputTokenCount") or 0)
                    total_tokens += tok
            dur = _span_duration_ms({"startTime": trace.get("startTime"), "endTime": trace.get("endTime")})
            if dur is not None:
                all_durations.append(dur)
                s = dur / 1000
                if   s <  1: dur_buckets["<1s"]   += 1
                elif s <  5: dur_buckets["1-5s"]  += 1
                elif s < 10: dur_buckets["5-10s"] += 1
                elif s < 30: dur_buckets["10-30s"]+= 1
                else:        dur_buckets["30s+"]  += 1

    total_spans = sum(span_type_counts.values())
    avg_dur = round(sum(all_durations) / len(all_durations), 2) if all_durations else 0
    p95_dur = _percentile(sorted(all_durations), 95) if all_durations else 0

    return {
        "total":           total,
        "errored":         errored,
        "ok":              total - errored,
        "errorRate":       round(errored / total, 4) if total else 0,
        "totalSpans":      total_spans,
        "avgSpansPerTrace":round(total_spans / total, 1) if total else 0,
        "avgDurationMs":   avg_dur,
        "p95DurationMs":   p95_dur,
        "totalTokens":     total_tokens,
        "spanTypeCounts":  dict(span_type_counts),
        "durationBuckets": dur_buckets,
    }


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


# ── Load Test Summary ─────────────────────────────────────────────────────────

def _apdex(lats_ms: list, t_ms: float = 3000.0) -> float:
    """Apdex score: satisfied(<T) + tolerating(<4T)*0.5, divided by total."""
    if not lats_ms:
        return 0.0
    satisfied  = sum(1 for l in lats_ms if l <= t_ms)
    tolerating = sum(1 for l in lats_ms if t_ms < l <= 4 * t_ms)
    return round((satisfied + tolerating * 0.5) / len(lats_ms), 3)


def _stddev(values: list) -> float:
    if len(values) < 2:
        return 0.0
    import math as _math
    mean = sum(values) / len(values)
    return round(_math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)), 2)


def _hist_buckets(lats_ms: list) -> dict:
    """Response-time distribution in industry-standard buckets (ms)."""
    buckets = {"0-1s": 0, "1-3s": 0, "3-5s": 0, "5-8s": 0, "8-12s": 0, "12s+": 0}
    for l in lats_ms:
        if   l <  1000: buckets["0-1s"]  += 1
        elif l <  3000: buckets["1-3s"]  += 1
        elif l <  5000: buckets["3-5s"]  += 1
        elif l <  8000: buckets["5-8s"]  += 1
        elif l < 12000: buckets["8-12s"] += 1
        else:           buckets["12s+"]  += 1
    return buckets


def compute_loadtest_summary(runs: List[dict]) -> dict:
    """Enterprise-grade load test summary — P50/P75/P90/P95/P99, Apdex, stddev, histogram."""
    import re as _re
    if not runs:
        return {
            "summary": {}, "by_bot": {}, "trends": [],
            "error_breakdown": {}, "slowest_requests": [], "histogram": {},
        }

    by_bot: Dict[str, dict] = defaultdict(lambda: {
        "latencies_ms": [], "tokens": [], "passed": 0, "failed": 0, "runs": 0
    })
    error_breakdown: Dict[str, int] = defaultdict(int)
    slowest: list = []
    trends: list = []
    all_hist: Dict[str, int] = {"0-1s": 0, "1-3s": 0, "3-5s": 0, "5-8s": 0, "8-12s": 0, "12s+": 0}

    for run in runs:
        hp         = run.get("hyperparameters") or {}
        bot_type   = hp.get("bot_type", "public")
        sla_p95_ms = float(hp.get("sla_p95_target_seconds", 12)) * 1000

        run_lats, run_tokens = [], []
        for span in get_all_spans_from_run(run):
            dur = _span_duration_ms(span)
            if dur is not None:
                run_lats.append(dur)
                by_bot[bot_type]["latencies_ms"].append(dur)
            tok = (span.get("inputTokenCount") or 0) + (span.get("outputTokenCount") or 0)
            if tok:
                run_tokens.append(tok)
                by_bot[bot_type]["tokens"].append(tok)

        passed = run.get("testPassed", 0)
        failed = run.get("testFailed", 0)
        total  = passed + failed
        by_bot[bot_type]["passed"] += passed
        by_bot[bot_type]["failed"] += failed
        by_bot[bot_type]["runs"]   += 1

        for tc in (run.get("testCases") or []):
            if not tc.get("success"):
                for md in (tc.get("metricsData") or []):
                    if md.get("name") == "RequestSuccess":
                        m = _re.search(r"failed:\s*(.+?)(?::|$)", md.get("reason", ""))
                        key = m.group(1).strip() if m else "RequestFailed"
                        error_breakdown[key] += 1
            dur_s = tc.get("runDuration")
            if dur_s:
                slowest.append({
                    "name":       (tc.get("name") or "")[:50],
                    "latency_ms": round(float(dur_s) * 1000, 0),
                    "bot_type":   bot_type,
                    "status":     "SUCCESS" if tc.get("success") else "FAILED",
                    "input":      (tc.get("input") or "")[:80],
                })

        run_dur    = run.get("runDuration") or 0
        throughput = round(total / run_dur, 3) if run_dur else 0
        fail_rate  = round(failed / total * 100, 1) if total else 0
        avg_tok    = round(sum(run_tokens) / len(run_tokens), 0) if run_tokens else 0
        s_lats     = sorted(run_lats)
        p95_run    = _percentile(s_lats, 95)
        run_hist   = _hist_buckets(s_lats)
        for k in all_hist:
            all_hist[k] += run_hist.get(k, 0)

        trends.append({
            "filename":          run.get("_filename", ""),
            "datetime":          run.get("_datetime", ""),
            "bot_type":          bot_type,
            "users":             hp.get("users", ""),
            "repeat":            hp.get("repeat", ""),
            "agent_name":        hp.get("agent_name", ""),
            # all percentiles
            "p50_ms":            _percentile(s_lats, 50),
            "p75_ms":            _percentile(s_lats, 75),
            "p90_ms":            _percentile(s_lats, 90),
            "p95_ms":            p95_run,
            "p99_ms":            _percentile(s_lats, 99),
            # distribution stats
            "avg_ms":            round(sum(s_lats) / len(s_lats), 2) if s_lats else 0,
            "min_ms":            round(min(s_lats), 2) if s_lats else 0,
            "max_ms":            round(max(s_lats), 2) if s_lats else 0,
            "stddev_ms":         _stddev(s_lats),
            "apdex":             _apdex(s_lats),
            # throughput / reliability
            "throughput_rps":    throughput,
            "failure_rate_pct":  fail_rate,
            "passed":            passed,
            "failed":            failed,
            "total":             total,
            "duration_s":        round(run_dur, 2),
            "avg_tokens":        avg_tok,
            # SLA
            "sla_p95_target_ms": sla_p95_ms,
            "sla_pass":          p95_run <= sla_p95_ms if s_lats else False,
            # per-run histogram
            "histogram":         run_hist,
        })

    bot_summary: dict = {}
    for bot, d in by_bot.items():
        lats  = sorted(d["latencies_ms"])
        total = d["passed"] + d["failed"]
        bot_summary[bot] = {
            "p50":            _percentile(lats, 50),
            "p75":            _percentile(lats, 75),
            "p90":            _percentile(lats, 90),
            "p95":            _percentile(lats, 95),
            "p99":            _percentile(lats, 99),
            "avg":            round(sum(lats) / len(lats), 2) if lats else 0,
            "min":            round(min(lats), 2) if lats else 0,
            "max":            round(max(lats), 2) if lats else 0,
            "stddev":         _stddev(lats),
            "apdex":          _apdex(lats),
            "failure_rate":   round(d["failed"] / total * 100, 1) if total else 0,
            "avg_tokens":     round(sum(d["tokens"]) / len(d["tokens"]), 0) if d["tokens"] else 0,
            "total_requests": total,
            "runs":           d["runs"],
        }

    all_lats    = sorted(l for d in by_bot.values() for l in d["latencies_ms"])
    tot_passed  = sum(d["passed"] for d in by_bot.values())
    tot_failed  = sum(d["failed"] for d in by_bot.values())
    tot_req     = tot_passed + tot_failed
    sla_tgt     = trends[0]["sla_p95_target_ms"] if trends else 12000
    p95_overall = _percentile(all_lats, 95)
    avg_tput    = round(sum(t["throughput_rps"] for t in trends) / len(trends), 3) if trends else 0
    sorted_trends = sorted(trends, key=lambda x: x["datetime"])

    # run-over-run delta for p95 and failure_rate
    for i, t in enumerate(sorted_trends):
        prev = sorted_trends[i - 1] if i > 0 else None
        t["p95_delta_ms"]       = round(t["p95_ms"] - prev["p95_ms"], 2) if prev else None
        t["fail_rate_delta_pct"] = round(t["failure_rate_pct"] - prev["failure_rate_pct"], 2) if prev else None

    return {
        "summary": {
            "total_runs":           len(runs),
            "total_requests":       tot_req,
            "total_passed":         tot_passed,
            "total_failed":         tot_failed,
            "avg_throughput_rps":   avg_tput,
            "avg_failure_rate_pct": round(tot_failed / tot_req * 100, 1) if tot_req else 0,
            "p50_ms":               _percentile(all_lats, 50),
            "p75_ms":               _percentile(all_lats, 75),
            "p90_ms":               _percentile(all_lats, 90),
            "p95_ms":               p95_overall,
            "p99_ms":               _percentile(all_lats, 99),
            "avg_ms":               round(sum(all_lats) / len(all_lats), 2) if all_lats else 0,
            "min_ms":               round(min(all_lats), 2) if all_lats else 0,
            "max_ms":               round(max(all_lats), 2) if all_lats else 0,
            "stddev_ms":            _stddev(all_lats),
            "apdex":                _apdex(all_lats),
            "sla_p95_target_ms":    sla_tgt,
            "sla_pass":             p95_overall <= sla_tgt,
        },
        "by_bot":           bot_summary,
        "trends":           sorted_trends,
        "error_breakdown":  dict(error_breakdown),
        "slowest_requests": sorted(slowest, key=lambda x: -x["latency_ms"])[:15],
        "histogram":        all_hist,
    }


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
            "filename":       run["_filename"],
            "datetime":       run["_datetime"],
            "environment":    run["_environment"],
            "version":        run["_version"],
            "framework":      run.get("_framework", "ragas"),
            "evaluatorLabel": run.get("_evaluatorLabel", "RAGAS Evaluator"),
            "passRate":       run["_passRate"],
            "cost":           run.get("evaluationCost", 0.0),
            "duration":       run.get("runDuration", 0.0),
            "passed":         run.get("testPassed", 0),
            "failed":         run.get("testFailed", 0),
            "metrics":        metrics,
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
