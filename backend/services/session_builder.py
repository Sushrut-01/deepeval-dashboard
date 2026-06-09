"""Groups traces into sessions/threads using threadId and userId from trace data."""
import json
import threading
from collections import defaultdict
from typing import Dict, List, Optional

from backend.config import SESSIONS_FILE
from backend.services.run_loader import get_all_runs

_lock = threading.Lock()


def get_all_sessions() -> List[dict]:
    sessions: Dict[str, dict] = defaultdict(lambda: {
        "sessionId": "", "userId": None, "traces": [],
        "traceCount": 0, "cost": 0.0, "lastActive": "",
    })

    for run in get_all_runs():
        for tc in (run.get("testCases") or []):
            trace = tc.get("trace")
            if not trace:
                continue
            thread_id = _resolve_thread_id(trace, run)
            user_id   = trace.get("userId")
            sid = thread_id

            sessions[sid]["sessionId"] = sid
            sessions[sid]["userId"]    = user_id
            sessions[sid]["traces"].append({
                "traceId":  trace.get("uuid"),
                "testCase": tc.get("name"),
                "filename": run["_filename"],
                "datetime": run["_datetime"],
                "input":    trace.get("input"),
                "output":   trace.get("output"),
                "status":   trace.get("status"),
            })
            sessions[sid]["traceCount"] += 1
            ts = trace.get("startTime") or trace.get("endTime") or ""
            if ts > sessions[sid]["lastActive"]:
                sessions[sid]["lastActive"] = ts

    result = []
    for sid, s in sessions.items():
        if not sid.startswith("__notrace_") and s["traceCount"] > 0:
            result.append({k: v for k, v in s.items() if k != "traces"})
    return sorted(result, key=lambda x: x["lastActive"], reverse=True)


def _resolve_thread_id(trace: dict, run: dict) -> str:
    run_id   = run.get("identifier") or run["_filename"].replace(".json", "")
    bot_type = (run.get("hyperparameters") or {}).get("bot_type", "")
    fallback = f"run-{run_id}" + (f"-{bot_type}" if bot_type else "")
    return trace.get("threadId") or fallback


def get_session(session_id: str) -> Optional[dict]:
    for run in get_all_runs():
        for tc in (run.get("testCases") or []):
            trace = tc.get("trace")
            if trace and _resolve_thread_id(trace, run) == session_id:
                # Collect all traces in this session
                traces = []
                for r in get_all_runs():
                    for t in (r.get("testCases") or []):
                        tr = t.get("trace")
                        if tr and _resolve_thread_id(tr, r) == session_id:
                            traces.append({
                                "traceId":  tr.get("uuid"),
                                "testCase": t.get("name"),
                                "filename": r["_filename"],
                                "datetime": r["_datetime"],
                                "input":    tr.get("input"),
                                "output":   tr.get("output"),
                                "status":   tr.get("status"),
                                "startTime": tr.get("startTime"),
                            })
                traces.sort(key=lambda x: x.get("startTime") or "")
                return {
                    "sessionId":  session_id,
                    "userId":     trace.get("userId"),
                    "traceCount": len(traces),
                    "traces":     traces,
                }
    return None
