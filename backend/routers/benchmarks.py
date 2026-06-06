"""
Benchmark results page.
DeepEval benchmarks (ARC, MMLU, HumanEval, BIG-Bench, etc.) write results
separately from test runs. We scan:
  1. eval_history/benchmarks/*.json  (manually saved benchmark results)
  2. Any JSON in eval_history/ matching benchmark naming patterns

Users can also POST benchmark results manually via the API.
"""
import json
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.config import HISTORY_FOLDER
from backend.services.file_store import load_or_default, save_json

router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])

BENCH_DIR  = lambda: HISTORY_FOLDER / "benchmarks"
BENCH_FILE = lambda: HISTORY_FOLDER / "benchmarks" / "_index.json"

# Known DeepEval benchmark names
KNOWN_BENCHMARKS = [
    "ARC", "MMLU", "HumanEval", "HumanEvalPlus", "BIG-Bench-Hard",
    "TruthfulQA", "HellaSwag", "GSM8K", "DROP", "LAMBADA",
    "BoolQ", "LogiQA", "SquAD", "MATH-QA", "WinoGrande",
    "BBQ", "IfEval", "METEOR", "Equity-Med-QA",
]


def _load_index() -> list:
    BENCH_DIR().mkdir(parents=True, exist_ok=True)
    return load_or_default(BENCH_FILE(), []) or []


def _save_index(data: list):
    BENCH_DIR().mkdir(parents=True, exist_ok=True)
    save_json(BENCH_FILE(), data)


@router.get("")
def list_benchmarks():
    """All saved benchmark results."""
    return _load_index()


@router.get("/names")
def benchmark_names():
    return KNOWN_BENCHMARKS


class BenchmarkIn(BaseModel):
    benchmark:   str
    model:       str
    score:       float
    tasks:       Optional[int] = None
    correct:     Optional[int] = None
    mode:        Optional[str] = None
    notes:       Optional[str] = None
    environment: Optional[str] = None
    project:     Optional[str] = None


@router.post("")
def add_benchmark(body: BenchmarkIn):
    """Manually record a benchmark result."""
    index = _load_index()
    entry = {
        "id":          str(uuid.uuid4())[:8],
        "benchmark":   body.benchmark,
        "model":       body.model,
        "score":       round(body.score, 4),
        "tasks":       body.tasks,
        "correct":     body.correct,
        "accuracy":    round(body.correct / body.tasks, 4) if body.tasks and body.correct else None,
        "mode":        body.mode,
        "notes":       body.notes,
        "environment": body.environment or "untagged",
        "project":     body.project or "default",
        "timestamp":   time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    index.insert(0, entry)
    _save_index(index)
    return {"success": True, "id": entry["id"]}


@router.post("/upload")
async def upload_benchmark_json(file: UploadFile = File(...)):
    """Upload a DeepEval benchmark result JSON file."""
    content = await file.read()
    try:
        data = json.loads(content)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Invalid JSON: {e}"})

    index = _load_index()
    # Handle both list and single result
    entries = data if isinstance(data, list) else [data]
    saved = 0
    for entry in entries:
        entry.setdefault("id", str(uuid.uuid4())[:8])
        entry.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%S"))
        index.insert(0, entry)
        saved += 1

    _save_index(index)
    return {"success": True, "imported": saved}


@router.delete("/{bench_id}")
def delete_benchmark(bench_id: str):
    index = _load_index()
    index = [e for e in index if e.get("id") != bench_id]
    _save_index(index)
    return {"success": True}


@router.get("/summary")
def benchmark_summary():
    """Aggregated: best score per benchmark across all models."""
    index = _load_index()
    by_bench: dict = {}
    for e in index:
        name = e.get("benchmark", "Unknown")
        if name not in by_bench:
            by_bench[name] = {"benchmark": name, "results": [], "best": None, "bestModel": None}
        by_bench[name]["results"].append(e)
        score = e.get("score", 0)
        if by_bench[name]["best"] is None or score > by_bench[name]["best"]:
            by_bench[name]["best"] = score
            by_bench[name]["bestModel"] = e.get("model")

    return sorted(by_bench.values(), key=lambda x: x["benchmark"])
