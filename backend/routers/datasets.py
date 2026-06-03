import csv, io, json
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse
from collections import defaultdict
from backend.services.run_loader import get_all_runs, get_all_test_cases

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("")
def list_dataset_cases(search: str = None):
    """All unique test case names grouped with input + score history."""
    cases: dict = defaultdict(lambda: {"name": "", "input": "", "expectedOutput": None,
                                        "runs": [], "scores": []})
    for run in get_all_runs():
        for tc in get_all_test_cases(run):
            name = tc.get("name", "")
            if search and search.lower() not in (tc.get("input") or "").lower() \
                       and search.lower() not in name.lower():
                continue
            d = cases[name]
            d["name"]           = name
            d["input"]          = d["input"] or tc.get("input", "")
            d["expectedOutput"] = d["expectedOutput"] or tc.get("expectedOutput")
            d["runs"].append(run["_filename"])
            for m in (tc.get("metricsData") or []):
                if m.get("score") is not None:
                    d["scores"].append({"filename": run["_filename"], "metric": m["name"],
                                        "score": m["score"], "datetime": run["_datetime"]})

    result = []
    for name, d in cases.items():
        avg_score = round(sum(s["score"] for s in d["scores"]) / len(d["scores"]), 3) if d["scores"] else None
        result.append({
            "name":          name,
            "input":         (d["input"] or "")[:200],
            "expectedOutput": d["expectedOutput"],
            "runCount":      len(set(d["runs"])),
            "avgScore":      avg_score,
        })
    return sorted(result, key=lambda x: x["name"])


@router.get("/{case_name}")
def get_dataset_case(case_name: str):
    history = []
    for run in get_all_runs():
        for tc in get_all_test_cases(run):
            if tc.get("name") == case_name:
                history.append({
                    "filename":  run["_filename"],
                    "datetime":  run["_datetime"],
                    "success":   tc.get("success"),
                    "input":     tc.get("input"),
                    "actualOutput": tc.get("actualOutput"),
                    "expectedOutput": tc.get("expectedOutput"),
                    "metrics": [{
                        "name":    m.get("name"),
                        "score":   m.get("score"),
                        "success": m.get("success"),
                    } for m in (tc.get("metricsData") or [])],
                })
    return {"name": case_name, "history": history}


@router.get("/export")
def export_dataset(fmt: str = "json"):
    cases = list_dataset_cases()
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["name", "input", "expectedOutput", "runCount", "avgScore"])
        w.writeheader()
        w.writerows(cases)
        buf.seek(0)
        return StreamingResponse(io.BytesIO(buf.getvalue().encode()), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=dataset.csv"})
    return StreamingResponse(
        io.BytesIO(json.dumps(cases, indent=2).encode()),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=dataset.json"},
    )


@router.post("/import")
async def import_dataset(file: UploadFile = File(...)):
    content = await file.read()
    try:
        data = json.loads(content)
    except Exception as e:
        return {"success": False, "error": f"Invalid JSON: {e}"}
    if isinstance(data, list):
        return {"success": True, "imported": len(data), "preview": data[:3]}
    return {"success": False, "error": "Expected a JSON array of test cases"}
