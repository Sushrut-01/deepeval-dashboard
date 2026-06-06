import uvicorn
import os
import webbrowser
import threading
from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv("DASHBOARD_PORT", 5000))


def _open_browser():
    import time
    time.sleep(1.5)
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    print(f"\n  DeepEval Local Dashboard")
    print(f"  Running at: http://localhost:{PORT}")
    print(f"  API docs:   http://localhost:{PORT}/docs")
    print(f"  Press Ctrl+C to stop\n")
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=PORT,
        reload=True,
        reload_excludes=["eval_history/*"],
        log_level="warning",
    )
