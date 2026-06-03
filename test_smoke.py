"""Quick smoke test — run from local-dashboard/ folder."""
import sys, json, time
from pathlib import Path

sys.path.insert(0, ".")

# ── 1. Write sample test run ──────────────────────────────────────────────────
sample = {
    "testCases": [
        {
            "name": "test_faithfulness_1",
            "input": "What is the capital of France?",
            "actualOutput": "The capital of France is Paris.",
            "expectedOutput": "Paris",
            "retrievalContext": [
                "France is a country in Western Europe. Its capital city is Paris."
            ],
            "success": True,
            "metricsData": [
                {"name": "Faithfulness", "threshold": 0.7, "success": True,
                 "score": 0.92, "reason": "Output is supported by context.",
                 "evaluationModel": "gpt-4o", "evaluationCost": 0.0012},
                {"name": "AnswerRelevancy", "threshold": 0.7, "success": True,
                 "score": 0.88, "reason": "Directly answers the question.",
                 "evaluationModel": "gpt-4o", "evaluationCost": 0.001},
            ],
            "runDuration": 2.3, "evaluationCost": 0.0022, "tags": ["rag"],
        },
        {
            "name": "test_hallucination_1",
            "input": "Who invented the telephone?",
            "actualOutput": "Thomas Edison invented the telephone in 1876.",
            "expectedOutput": "Alexander Graham Bell invented the telephone.",
            "retrievalContext": [
                "Alexander Graham Bell is credited with inventing the telephone in 1876."
            ],
            "success": False,
            "metricsData": [
                {"name": "Faithfulness", "threshold": 0.7, "success": False,
                 "score": 0.21, "reason": "Output contradicts the context.",
                 "evaluationModel": "gpt-4o", "evaluationCost": 0.0015},
                {"name": "AnswerRelevancy", "threshold": 0.7, "success": True,
                 "score": 0.75, "reason": "Answers the question topic.",
                 "evaluationModel": "gpt-4o", "evaluationCost": 0.001},
            ],
            "runDuration": 1.8, "evaluationCost": 0.0025, "tags": ["history"],
            "trace": {
                "uuid": "trace-001",
                "startTime": "2026-06-01T10:00:00", "endTime": "2026-06-01T10:00:05",
                "status": "SUCCESS",
                "input": "Who invented the telephone?",
                "output": "Thomas Edison invented the telephone in 1876.",
                "llmSpans": [{
                    "uuid": "llm-001", "name": "gpt-4o-call", "type": "llm",
                    "status": "SUCCESS",
                    "startTime": "2026-06-01T10:00:01", "endTime": "2026-06-01T10:00:04",
                    "model": "gpt-4o", "inputTokenCount": 450, "outputTokenCount": 25,
                    "costPerInputToken": 0.000005, "costPerOutputToken": 0.000015,
                    "input": "Answer only from context. Context: ...",
                    "output": "Thomas Edison invented...",
                }],
                "retrieverSpans": [{
                    "uuid": "ret-001", "name": "vector_search", "type": "retriever",
                    "status": "SUCCESS",
                    "startTime": "2026-06-01T10:00:00", "endTime": "2026-06-01T10:00:01",
                    "embedder": "text-embedding-3-small", "topK": 3, "chunkSize": 128,
                    "output": ["Alexander Graham Bell is credited..."],
                }],
                "baseSpans": [], "agentSpans": [], "toolSpans": [],
            },
        },
    ],
    "conversationalTestCases": [],
    "metricsScores": [
        {"metric": "Faithfulness",    "scores": [0.92, 0.21], "passes": 1, "fails": 1, "errors": 0},
        {"metric": "AnswerRelevancy", "scores": [0.88, 0.75], "passes": 2, "fails": 0, "errors": 0},
    ],
    "testPassed": 1, "testFailed": 1,
    "runDuration": 4.1, "evaluationCost": 0.0047,
    "hyperparameters": {
        "model": "gpt-4o", "environment": "development",
        "version": "v1.0.0", "chunk_size": 128, "top_k": 3,
    },
    "identifier": "smoke-test-run",
}

Path("eval_history").mkdir(exist_ok=True)
fname = f"test_run_{int(time.time())}.json"
Path(f"eval_history/{fname}").write_text(json.dumps(sample, indent=2))
print(f"[1] Sample run written: {fname}")

# ── 2. Test run_loader ────────────────────────────────────────────────────────
from backend.services.run_loader import force_refresh, get_all_summaries, get_run, run_count
force_refresh()
print(f"[2] Runs loaded: {run_count()}")
s = get_all_summaries()[0]
print(f"    filename={s['filename']}, passed={s['testPassed']}, "
      f"failed={s['testFailed']}, passRate={s['passRate']}, "
      f"env={s['environment']}, ver={s['version']}")

# ── 3. Test aggregator ────────────────────────────────────────────────────────
from backend.services.aggregator import (
    compute_metric_summary, compute_latency_percentiles,
    compute_cost_breakdown, detect_regressions,
)
run = get_run(fname)
assert run is not None, "get_run returned None"
metric_sum = compute_metric_summary([run])
print(f"[3] Metric summary: {[(m['metric'], m['avg']) for m in metric_sum]}")

perc = compute_latency_percentiles([run])
print(f"    Latency percentiles: {list(perc.keys())}")

cost = compute_cost_breakdown([run])
print(f"    Cost by model: {cost['byModel']}")

# ── 4. Test bug detector ──────────────────────────────────────────────────────
from backend.services.bug_detector import analyze_run
report = analyze_run(run, [])
print(f"[4] Bugs detected: {report['total']} total, "
      f"{report['critical']} critical, {report['warning']} warning")
for b in report["bugs"]:
    print(f"    [{b['severity'].upper():8}] {b['bugId']} | {b['type']:20} | {b['title'][:55]}")

# ── 5. Test FastAPI routes import ─────────────────────────────────────────────
from backend.main import app
routes = [r.path for r in app.routes if hasattr(r, "path")]
print(f"[5] FastAPI routes: {len(routes)} registered")

print("\n  ALL CHECKS PASSED")
