"""
Real-time file watcher for eval_history/.
Uses watchdog (inotify/FSEvents/ReadDirectoryChanges) to detect new
test_run_*.json files instantly — no 30-second polling lag.
Falls back to APScheduler polling if watchdog is unavailable.
"""
import logging
import threading
import time
from pathlib import Path
from typing import Callable, List

logger = logging.getLogger(__name__)

_callbacks: List[Callable[[str], None]] = []
_observer = None


def register_callback(fn: Callable[[str], None]):
    """Call fn(filename) whenever a new test_run_*.json is written."""
    _callbacks.append(fn)


def _fire(filename: str):
    from backend.services import run_loader
    # Small delay: let the writer fully flush the file before we read it
    time.sleep(0.4)
    run_loader.force_refresh()
    for cb in _callbacks:
        try:
            cb(filename)
        except Exception as e:
            logger.warning("file_watcher callback error for %s: %s", filename, e)


def start(folder: Path):
    global _observer
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory:
                    return
                p = Path(event.src_path)
                if p.name.startswith("test_run_") and p.suffix == ".json":
                    logger.info("file_watcher: new run → %s", p.name)
                    threading.Thread(target=_fire, args=(p.name,), daemon=True).start()

            def on_modified(self, event):
                # Some OS/editors trigger modified instead of created
                if event.is_directory:
                    return
                p = Path(event.src_path)
                if p.name.startswith("test_run_") and p.suffix == ".json":
                    logger.debug("file_watcher: modified → %s", p.name)

        folder.mkdir(parents=True, exist_ok=True)
        _observer = Observer()
        _observer.schedule(_Handler(), str(folder), recursive=False)
        _observer.start()
        logger.info("file_watcher: watchdog observer started on %s", folder)

    except Exception as e:
        logger.warning("file_watcher: watchdog unavailable (%s) — using 30s polling", e)
        _observer = None


def stop():
    global _observer
    if _observer:
        try:
            _observer.stop()
            _observer.join(timeout=3)
        except Exception:
            pass
        _observer = None
