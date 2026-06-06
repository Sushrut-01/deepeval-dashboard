"""
DeepEval Local Dashboard — FastAPI Backend
Port: 5000 | Start: python run.py
"""
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import HISTORY_FOLDER, DASHBOARD_PORT
from backend.services import run_loader
from backend.services import online_eval_worker
from backend.routers.auth import AUTH_ENABLED, get_current_user

# ── Routers ────────────────────────────────────────────────────────────────────
from backend.routers import (
    dashboard, runs, metrics, latency, cost,
    traces, sessions, users, usage, feedback,
    annotations, queues, score_configs, evaluators,
    automations, webhooks, datasets, prompts,
    bugs, compare, settings, metrics_export,
)
from backend.routers import auth, playground, projects, benchmarks
from backend.routers import sla

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

# Routes that never require auth (login page, health, static files)
_PUBLIC_PREFIXES = (
    "/api/auth/",
    "/api/health",
    "/static/",
    "/docs",
    "/redoc",
    "/openapi.json",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────────────
    HISTORY_FOLDER.mkdir(parents=True, exist_ok=True)
    run_loader.force_refresh()
    n = run_loader.run_count()
    print(f"  History folder : {HISTORY_FOLDER}")
    print(f"  Loaded runs    : {n}")
    # Point 3: real-time watchdog + APScheduler fallback
    online_eval_worker.start()
    print(f"  File watcher   : started (instant new-run detection)")
    print(f"  Worker         : started (auto-eval + bug detection + SLA checks)")
    # Seed default SLOs if none configured yet
    from backend.services.sla_calculator import SLO_FILE
    from backend.services.file_store import load_or_default
    if not (load_or_default(SLO_FILE(), []) or []):
        from backend.routers.sla import seed_defaults
        seed_defaults()
        print(f"  SLOs           : 8 default SLOs seeded")
    auth_status = "enabled (admin/admin123)" if AUTH_ENABLED else "disabled"
    print(f"  Auth           : {auth_status}")
    print()
    yield
    # ── Shutdown ───────────────────────────────────────────────────────────────
    online_eval_worker.stop()


app = FastAPI(
    title="DeepEval Local Dashboard",
    description="Self-hosted Confident AI + LangSmith + Langfuse — with Bug Detection",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ── Auth middleware (Point 2) ──────────────────────────────────────────────────
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Always allow public routes
    is_public = any(path.startswith(p) for p in _PUBLIC_PREFIXES)
    # Also allow GET / (serves dashboard.html which has its own login page)
    if path == "/" or path.startswith("/theme") or not path.startswith("/api/"):
        is_public = True

    if AUTH_ENABLED and not is_public:
        user = get_current_user(request)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication required", "loginUrl": "/"},
            )

    response = await call_next(request)
    return response

# ── Timing middleware ──────────────────────────────────────────────────────────
@app.middleware("http")
async def add_timing(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    ms = round((time.time() - t0) * 1000, 1)
    response.headers["X-Response-Time"] = f"{ms}ms"
    return response

# ── Global error handler ───────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_error(request: Request, exc: Exception):
    logger.error("Unhandled error on %s: %s", request.url, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"error": str(exc)})

# ── API Routers ────────────────────────────────────────────────────────────────
for r in [
    auth.router, playground.router,
    sla.router, projects.router, benchmarks.router,   # SLA + multi-project + benchmarks
    dashboard.router, runs.router, metrics.router, latency.router, cost.router,
    traces.router, sessions.router, users.router, usage.router, feedback.router,
    annotations.router, queues.router, score_configs.router, evaluators.router,
    automations.router, webhooks.router, datasets.router, prompts.router,
    bugs.router, compare.router, settings.router, metrics_export.router,
]:
    app.include_router(r)

# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["health"])
def health():
    return {
        "status":      "ok",
        "runCount":    run_loader.run_count(),
        "port":        DASHBOARD_PORT,
        "version":     "1.0.0",
        "folder":      str(HISTORY_FOLDER),
        "authEnabled": AUTH_ENABLED,
    }

# ── Static files ───────────────────────────────────────────────────────────────
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
@app.get("/{path:path}", include_in_schema=False)
async def serve_spa(path: str = ""):
    # Serve specific static files (theme previews, etc.)
    if path and (STATIC_DIR / path).is_file():
        return FileResponse(str(STATIC_DIR / path))
    index = STATIC_DIR / "dashboard.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse(
        status_code=503,
        content={"message": "dashboard.html not found.", "api_docs": f"http://localhost:{DASHBOARD_PORT}/docs"},
    )
