from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import os
from backend.config import HISTORY_FOLDER, DASHBOARD_PORT, PASS_RATE_ALERT_THRESHOLD, AUTO_REFRESH_INTERVAL
from backend.services.run_loader import run_count

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsIn(BaseModel):
    historyFolder:       Optional[str] = None
    passRateThreshold:   Optional[float] = None
    autoRefreshInterval: Optional[int] = None


@router.get("")
def get_settings():
    folder = HISTORY_FOLDER
    try:
        size_bytes = sum(f.stat().st_size for f in folder.rglob("*.json") if f.is_file())
        size_mb    = round(size_bytes / (1024 * 1024), 2)
    except Exception:
        size_mb = 0.0

    return {
        "historyFolder":       str(folder),
        "port":                DASHBOARD_PORT,
        "passRateThreshold":   PASS_RATE_ALERT_THRESHOLD,
        "autoRefreshInterval": AUTO_REFRESH_INTERVAL,
        "runCount":            run_count(),
        "diskUsageMB":         size_mb,
        "version":             "1.0.0",
    }


@router.post("")
def update_settings(body: SettingsIn):
    if body.historyFolder:
        os.environ["DEEPEVAL_RESULTS_FOLDER"] = body.historyFolder
    if body.passRateThreshold is not None:
        os.environ["PASS_RATE_ALERT_THRESHOLD"] = str(body.passRateThreshold)
    if body.autoRefreshInterval is not None:
        os.environ["AUTO_REFRESH_INTERVAL"] = str(body.autoRefreshInterval)
    from backend.services.run_loader import force_refresh
    force_refresh()
    return {"success": True}
