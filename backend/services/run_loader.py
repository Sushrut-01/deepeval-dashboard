"""
Core service: reads, parses, and caches all test_run_*.json files.
All other services and routers depend on this.
"""
import json
import threading
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.config import HISTORY_FOLDER, AUTO_REFRESH_INTERVAL

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: Dict[str, Any] = {
    "runs": {},          # filename -> full parsed run dict
    "summaries": {},     # filename -> lightweight summary dict
    "mtimes": {},        # filename -> mtime when parsed
    "file_list": [],     # sorted list of known filenames (newest first)
    "last_scan": 0.0,    # epoch time of last folder scan
}
_new_run_callbacks: List[Any] = []  # callables fired when a new run appears


# ── Public API ─────────────────────────────────────────────────────────────────

def register_new_run_callback(fn):
    """Register a function to call whenever a new run file is detected."""
    _new_run_callbacks.append(fn)


def get_all_summaries() -> List[dict]:
    """Lightweight list of all runs (no test case bodies)."""
    _refresh()
    with _lock:
        return [_cache["summaries"][f] for f in _cache["file_list"]]


def get_run(filename: str) -> Optional[dict]:
    """Full run data for one file."""
    _refresh()
    with _lock:
        return _cache["runs"].get(filename)


def get_all_runs() -> List[dict]:
    """Full run data for every file (expensive — use summaries where possible)."""
    _refresh()
    with _lock:
        return [_cache["runs"][f] for f in _cache["file_list"]]


def get_latest_run() -> Optional[dict]:
    _refresh()
    with _lock:
        if not _cache["file_list"]:
            return None
        return _cache["runs"].get(_cache["file_list"][0])


def run_count() -> int:
    _refresh()
    with _lock:
        return len(_cache["file_list"])


def force_refresh():
    with _lock:
        _cache["last_scan"] = 0.0
    _refresh()


# ── Internal ───────────────────────────────────────────────────────────────────

def _refresh():
    now = time.time()
    with _lock:
        if now - _cache["last_scan"] < AUTO_REFRESH_INTERVAL:
            return
    _scan_folder()


def _scan_folder():
    if not HISTORY_FOLDER.exists():
        HISTORY_FOLDER.mkdir(parents=True, exist_ok=True)
        return

    try:
        files = sorted(
            HISTORY_FOLDER.glob("test_run_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception as e:
        logger.warning(f"run_loader: folder scan failed: {e}")
        return

    new_files = []
    with _lock:
        for f in files:
            fname = f.name
            mtime = f.stat().st_mtime
            if fname not in _cache["mtimes"] or _cache["mtimes"][fname] != mtime:
                try:
                    raw = json.loads(f.read_text(encoding="utf-8"))
                    parsed = _parse_run(raw, fname, mtime)
                    _cache["runs"][fname] = parsed
                    _cache["summaries"][fname] = _make_summary(parsed)
                    _cache["mtimes"][fname] = mtime
                    if fname not in _cache["file_list"]:
                        new_files.append(fname)
                except Exception as e:
                    logger.warning(f"run_loader: skipping {fname}: {e}")

        _cache["file_list"] = sorted(
            [f.name for f in files if f.name in _cache["runs"]],
            key=lambda n: _cache["mtimes"].get(n, 0),
            reverse=True,
        )
        _cache["last_scan"] = time.time()

    for fname in new_files:
        for cb in _new_run_callbacks:
            try:
                cb(fname)
            except Exception as e:
                logger.warning(f"run_loader: callback error for {fname}: {e}")


def _parse_run(raw: dict, filename: str, mtime: float) -> dict:
    """Normalise a raw JSON dict into our internal run format."""
    from backend.services.env_detector import detect_environment, detect_version, detect_project

    hyper = raw.get("hyperparameters") or {}
    env   = detect_environment(raw)
    ver   = detect_version(raw)
    proj  = detect_project(raw)

    # Normalise test cases
    test_cases = [_parse_llm_case(tc) for tc in (raw.get("testCases") or [])]
    conv_cases = [_parse_conv_case(tc) for tc in (raw.get("conversationalTestCases") or [])]

    passed = raw.get("testPassed") or sum(1 for tc in test_cases + conv_cases if tc.get("success"))
    failed = raw.get("testFailed") or sum(1 for tc in test_cases + conv_cases if tc.get("success") is False)
    total  = passed + failed

    metrics_scores = _parse_metrics_scores(raw.get("metricsScores") or [])

    # Collect all span data for error rate
    all_spans = _collect_all_spans(test_cases)
    errored   = sum(1 for s in all_spans if (s.get("status") or "").upper() == "ERRORED")
    error_rate = round(errored / len(all_spans), 4) if all_spans else 0.0

    return {
        "_filename":    filename,
        "_mtime":       mtime,
        "_datetime":    _fmt_time(mtime),
        "_environment": env,
        "_version":     ver,
        "_project":     proj,
        "testFile":     raw.get("testFile"),
        "testCases":    test_cases,
        "conversationalTestCases": conv_cases,
        "metricsScores":   metrics_scores,
        "traceMetricsScores": raw.get("traceMetricsScores"),
        "hyperparameters": hyper,
        "identifier":   raw.get("identifier"),
        "datasetAlias": raw.get("datasetAlias"),
        "datasetId":    raw.get("datasetId"),
        "testPassed":   passed,
        "testFailed":   failed,
        "runDuration":  raw.get("runDuration") or 0.0,
        "evaluationCost": raw.get("evaluationCost") or 0.0,
        "_passRate":    round(passed / total, 4) if total else 0.0,
        "_errorRate":   error_rate,
        "_caseCount":   len(test_cases) + len(conv_cases),
        "_hasTraces":   any(tc.get("trace") for tc in test_cases),
    }


def _parse_llm_case(tc: dict) -> dict:
    return {
        "type":           "llm",
        "name":           tc.get("name", ""),
        "input":          tc.get("input", ""),
        "actualOutput":   tc.get("actualOutput", ""),
        "expectedOutput": tc.get("expectedOutput"),
        "context":        tc.get("context") or [],
        "retrievalContext": tc.get("retrievalContext") or [],
        "toolsCalled":    tc.get("toolsCalled") or [],
        "expectedTools":  tc.get("expectedTools") or [],
        "tokenCost":      tc.get("tokenCost"),
        "completionTime": tc.get("completionTime"),
        "tags":           tc.get("tags") or [],
        "success":        tc.get("success"),
        "metricsData":    [_parse_metric(m) for m in (tc.get("metricsData") or [])],
        "runDuration":    tc.get("runDuration") or 0.0,
        "evaluationCost": tc.get("evaluationCost") or 0.0,
        "order":          tc.get("order"),
        "metadata":       tc.get("metadata") or {},
        "comments":       tc.get("comments"),
        "trace":          _parse_trace(tc.get("trace")) if tc.get("trace") else None,
    }


def _parse_conv_case(tc: dict) -> dict:
    return {
        "type":            "conversational",
        "name":            tc.get("name", ""),
        "success":         tc.get("success"),
        "metricsData":     [_parse_metric(m) for m in (tc.get("metricsData") or [])],
        "runDuration":     tc.get("runDuration") or 0.0,
        "evaluationCost":  tc.get("evaluationCost") or 0.0,
        "turns":           tc.get("turns") or [],
        "order":           tc.get("order"),
        "scenario":        tc.get("scenario"),
        "expectedOutcome": tc.get("expectedOutcome"),
        "userDescription": tc.get("userDescription"),
        "context":         tc.get("context") or [],
        "comments":        tc.get("comments"),
        "metadata":        tc.get("metadata") or {},
        "tags":            tc.get("tags") or [],
    }


def _parse_metric(m: dict) -> dict:
    return {
        "name":            m.get("name", ""),
        "threshold":       m.get("threshold", 0.5),
        "success":         m.get("success", False),
        "score":           m.get("score"),
        "reason":          m.get("reason"),
        "strictMode":      m.get("strictMode", False),
        "evaluationModel": m.get("evaluationModel"),
        "error":           m.get("error"),
        "evaluationCost":  m.get("evaluationCost"),
        "verboseLogs":     m.get("verboseLogs"),
    }


def _parse_trace(t: dict) -> dict:
    if not t:
        return None
    return {
        "uuid":           t.get("uuid", ""),
        "name":           t.get("name"),
        "startTime":      t.get("startTime"),
        "endTime":        t.get("endTime"),
        "status":         t.get("status", "SUCCESS"),
        "input":          t.get("input"),
        "output":         t.get("output"),
        "metadata":       t.get("metadata") or {},
        "tags":           t.get("tags") or [],
        "environment":    t.get("environment"),
        "threadId":       t.get("threadId"),
        "userId":         t.get("userId"),
        "metricsData":    [_parse_metric(m) for m in (t.get("metricsData") or [])],
        "baseSpans":      [_parse_span(s) for s in (t.get("baseSpans") or [])],
        "agentSpans":     [_parse_span(s) for s in (t.get("agentSpans") or [])],
        "llmSpans":       [_parse_span(s) for s in (t.get("llmSpans") or [])],
        "retrieverSpans": [_parse_span(s) for s in (t.get("retrieverSpans") or [])],
        "toolSpans":      [_parse_span(s) for s in (t.get("toolSpans") or [])],
    }


def _parse_span(s: dict) -> dict:
    return {
        "uuid":             s.get("uuid", ""),
        "name":             s.get("name"),
        "status":           s.get("status", "SUCCESS"),
        "type":             s.get("type", "base"),
        "parentUuid":       s.get("parentUuid"),
        "startTime":        s.get("startTime"),
        "endTime":          s.get("endTime"),
        "metadata":         s.get("metadata") or {},
        "input":            s.get("input"),
        "output":           s.get("output"),
        "error":            s.get("error"),
        "retrievalContext": s.get("retrievalContext") or [],
        "context":          s.get("context") or [],
        "expectedOutput":   s.get("expectedOutput"),
        "toolsCalled":      s.get("toolsCalled") or [],
        "expectedTools":    s.get("expectedTools") or [],
        "availableTools":   s.get("availableTools") or [],
        "agentHandoffs":    s.get("agentHandoffs") or [],
        "description":      s.get("description"),
        "embedder":         s.get("embedder"),
        "topK":             s.get("topK"),
        "chunkSize":        s.get("chunkSize"),
        "model":            s.get("model"),
        "provider":         s.get("provider"),
        "inputTokenCount":  s.get("inputTokenCount"),
        "outputTokenCount": s.get("outputTokenCount"),
        "costPerInputToken":  s.get("costPerInputToken"),
        "costPerOutputToken": s.get("costPerOutputToken"),
        "metricsData":      [_parse_metric(m) for m in (s.get("metricsData") or [])],
        "integration":      s.get("integration"),
    }


def _parse_metrics_scores(raw_list: list) -> list:
    result = []
    for ms in raw_list:
        scores = ms.get("scores") or []
        result.append({
            "metric": ms.get("metric", ""),
            "scores": scores,
            "passes": ms.get("passes", 0),
            "fails":  ms.get("fails", 0),
            "errors": ms.get("errors", 0),
            "avg":    round(sum(scores) / len(scores), 4) if scores else 0.0,
        })
    return result


def _make_summary(run: dict) -> dict:
    """Lightweight summary for list views (no test case bodies)."""
    return {
        "filename":     run["_filename"],
        "datetime":     run["_datetime"],
        "mtime":        run["_mtime"],
        "environment":  run["_environment"],
        "version":      run["_version"],
        "project":      run["_project"],
        "testPassed":   run["testPassed"],
        "testFailed":   run["testFailed"],
        "runDuration":  run["runDuration"],
        "evaluationCost": run["evaluationCost"],
        "passRate":     run["_passRate"],
        "errorRate":    run["_errorRate"],
        "caseCount":    run["_caseCount"],
        "hasTraces":    run["_hasTraces"],
        "metricsScores": run["metricsScores"],
        "identifier":   run.get("identifier"),
        "datasetAlias": run.get("datasetAlias"),
    }


def _collect_all_spans(test_cases: list) -> list:
    spans = []
    for tc in test_cases:
        trace = tc.get("trace")
        if not trace:
            continue
        for bucket in ("baseSpans", "agentSpans", "llmSpans", "retrieverSpans", "toolSpans"):
            spans.extend(trace.get(bucket) or [])
    return spans


def _fmt_time(mtime: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")


# ── Helper: get test case by name from a run ───────────────────────────────────

def get_test_case(run: dict, name: str) -> Optional[dict]:
    for tc in (run.get("testCases") or []):
        if tc.get("name") == name:
            return tc
    for tc in (run.get("conversationalTestCases") or []):
        if tc.get("name") == name:
            return tc
    return None


def get_all_spans_from_run(run: dict) -> List[dict]:
    """Flat list of all spans across all test cases in a run."""
    return _collect_all_spans(run.get("testCases") or [])


def get_all_test_cases(run: dict) -> List[dict]:
    return (run.get("testCases") or []) + (run.get("conversationalTestCases") or [])
