"""
setup_dashboard_venv.py
=======================
Creates a self-contained venv for the dashboard at:
    C:\\Users\\v-snistane\\tools\\deepeval-dashboard\\.venv

Installs all packages the dashboard backend needs (FastAPI, uvicorn, etc.)
so the dashboard can be started independently from any project.

Run:
    python setup_dashboard_venv.py
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

DASH = Path(r"C:\Users\v-snistane\tools\deepeval-dashboard")
VENV = DASH / ".venv"
VENV_PY = VENV / "Scripts" / "python.exe"
HISTORY = DASH / "eval_history"

# Minimum packages the dashboard needs (based on errors we've seen so far)
PACKAGES = [
    "fastapi",
    "uvicorn[standard]",
    "python-multipart",   # needed for form uploads
    "watchdog",           # needed for file watcher
    "pydantic",
    "python-dotenv",
    "httpx",
    "starlette",
    "websockets",         # for real-time UI updates
    "watchfiles",
    "httptools",
    "anyio",
    "click",
    "pyyaml",
]


def banner(msg: str) -> None:
    print("\n" + "=" * 70)
    print(msg)
    print("=" * 70)


def run(cmd: list[str]) -> int:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.call(cmd)


def main() -> int:
    banner("Setting up self-contained dashboard venv")

    if not DASH.exists():
        print(f"[FAIL] Dashboard folder not found: {DASH}")
        return 2

    # 1. Create venv if missing
    if VENV_PY.exists():
        print(f"[OK] venv already exists at {VENV}")
    else:
        print(f"[1/3] Creating venv at {VENV}")
        rc = run([sys.executable, "-m", "venv", str(VENV)])
        if rc != 0 or not VENV_PY.exists():
            print(f"[FAIL] venv creation failed (rc={rc})")
            return 3

    # 2. Upgrade pip
    print(f"\n[2/3] Upgrading pip / setuptools / wheel")
    run([str(VENV_PY), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"])

    # 3. Install dashboard requirements
    print(f"\n[3/3] Installing dashboard dependencies")
    req_file = DASH / "requirements.txt"
    if req_file.exists():
        print(f"  Found {req_file.name} — installing from it")
        run([str(VENV_PY), "-m", "pip", "install", "-r", str(req_file)])
    else:
        print("  No requirements.txt found — installing minimal package set")
        run([str(VENV_PY), "-m", "pip", "install", *PACKAGES])

    HISTORY.mkdir(parents=True, exist_ok=True)

    banner("Setup complete — how to start the dashboard")
    print("Option A) Use the helper script (recommended):")
    print(r"   C:\Users\v-snistane\tools\start-dashboard.ps1")
    print()
    print("Option B) Manual:")
    print(rf"   cd {DASH}")
    print(rf"   .\.venv\Scripts\Activate.ps1")
    print(rf'   $env:DEEPEVAL_RESULTS_FOLDER = "{HISTORY}"')
    print(r"   python run.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())