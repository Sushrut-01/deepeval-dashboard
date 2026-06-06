import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

HISTORY_FOLDER = Path(os.getenv("DEEPEVAL_RESULTS_FOLDER", "./eval_history")).resolve()
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 5000))
PASS_RATE_ALERT_THRESHOLD = float(os.getenv("PASS_RATE_ALERT_THRESHOLD", 0.70))
AUTO_REFRESH_INTERVAL = int(os.getenv("AUTO_REFRESH_INTERVAL", 30))

# Storage files inside history folder
def get_store_path(filename: str) -> Path:
    HISTORY_FOLDER.mkdir(parents=True, exist_ok=True)
    return HISTORY_FOLDER / filename

ANNOTATIONS_FILE   = lambda: get_store_path("annotations.json")
QUEUES_FILE        = lambda: get_store_path("queues.json")
SCORE_CONFIGS_FILE = lambda: get_store_path("score_configs.json")
EVALUATORS_FILE    = lambda: get_store_path("evaluators.json")
AUTOMATIONS_FILE   = lambda: get_store_path("automations.json")
WEBHOOKS_FILE      = lambda: get_store_path("webhooks.json")
PROMPTS_FILE       = lambda: get_store_path("prompts.json")
SESSIONS_FILE      = lambda: get_store_path("sessions.json")
FEEDBACK_FILE      = lambda: get_store_path("feedback.json")
BUG_REPORTS_FILE   = lambda: get_store_path("bug_reports.json")
