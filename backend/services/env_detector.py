"""Detect environment, version, and project from a run's hyperparameters."""


def detect_environment(run: dict) -> str:
    hyper = run.get("hyperparameters") or {}
    for key in ("environment", "CONFIDENT_TRACE_ENVIRONMENT", "env", "ENV"):
        if hyper.get(key):
            return str(hyper[key]).lower()
    return "untagged"


def detect_version(run: dict) -> str:
    hyper = run.get("hyperparameters") or {}
    for key in ("version", "APP_VERSION", "app_version", "release"):
        if hyper.get(key):
            return str(hyper[key])
    ident = run.get("identifier")
    if ident:
        return str(ident)
    return "unversioned"


def detect_project(run: dict) -> str:
    """
    Detect project name from hyperparameters.
    Set in your tests:  deepeval.log_hyperparameters(project="my-bot", ...)
    """
    hyper = run.get("hyperparameters") or {}
    for key in ("project", "PROJECT", "project_name", "app_name", "bot_name", "service"):
        if hyper.get(key):
            return str(hyper[key])
    return "default"
