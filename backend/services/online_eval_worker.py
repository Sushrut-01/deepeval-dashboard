"""
Background worker:
  - watchdog fires _on_new_run() immediately when a new test_run_*.json appears
  - APScheduler polls every AUTO_REFRESH_INTERVAL seconds as a fallback
  - _on_new_run runs bug detection + online evaluators + automation rules
"""
import logging
import time
from typing import List

from apscheduler.schedulers.background import BackgroundScheduler

from backend.config import (
    AUTO_REFRESH_INTERVAL, EVALUATORS_FILE, AUTOMATIONS_FILE,
    BUG_REPORTS_FILE, HISTORY_FOLDER,
)
from backend.services.file_store import load_or_default, save_json
from backend.services.run_loader import register_new_run_callback, get_run, get_all_runs
from backend.services import file_watcher

logger = logging.getLogger(__name__)
_scheduler = None


# ── Metric class registry ─────────────────────────────────────────────────────

def _get_metric_map():
    """Build a name→class map from whatever deepeval metrics are importable."""
    try:
        from deepeval.metrics import (
            FaithfulnessMetric, AnswerRelevancyMetric,
            ContextualRecallMetric, ContextualPrecisionMetric,
            ContextualRelevancyMetric, HallucinationMetric,
            BiasMetric, ToxicityMetric, SummarizationMetric,
            JsonCorrectnessMetric, ToolCorrectnessMetric,
            TaskCompletionMetric, GEval, PIILeakageMetric,
            PromptAlignmentMetric, StepEfficiencyMetric,
            PlanAdherenceMetric, GoalAccuracyMetric,
            KnowledgeRetentionMetric, ConversationCompletenessMetric,
            RoleAdherenceMetric, TopicAdherenceMetric,
            NonAdviceMetric, MisuseMetric, RoleViolationMetric,
            ExactMatchMetric, PatternMatchMetric,
        )
        return {
            "Faithfulness":            FaithfulnessMetric,
            "AnswerRelevancy":         AnswerRelevancyMetric,
            "ContextualRecall":        ContextualRecallMetric,
            "ContextualPrecision":     ContextualPrecisionMetric,
            "ContextualRelevancy":     ContextualRelevancyMetric,
            "Hallucination":           HallucinationMetric,
            "Bias":                    BiasMetric,
            "Toxicity":                ToxicityMetric,
            "Summarization":           SummarizationMetric,
            "JsonCorrectness":         JsonCorrectnessMetric,
            "ToolCorrectness":         ToolCorrectnessMetric,
            "TaskCompletion":          TaskCompletionMetric,
            "PIILeakage":              PIILeakageMetric,
            "PromptAlignment":         PromptAlignmentMetric,
            "StepEfficiency":          StepEfficiencyMetric,
            "PlanAdherence":           PlanAdherenceMetric,
            "GoalAccuracy":            GoalAccuracyMetric,
            "KnowledgeRetention":      KnowledgeRetentionMetric,
            "ConversationCompleteness":ConversationCompletenessMetric,
            "RoleAdherence":           RoleAdherenceMetric,
            "TopicAdherence":          TopicAdherenceMetric,
            "NonAdvice":               NonAdviceMetric,
            "Misuse":                  MisuseMetric,
            "RoleViolation":           RoleViolationMetric,
            "ExactMatch":              ExactMatchMetric,
            "PatternMatch":            PatternMatchMetric,
        }
    except ImportError as e:
        logger.warning("online_eval_worker: deepeval metrics not importable: %s", e)
        return {}


# ── Startup / shutdown ────────────────────────────────────────────────────────

def start():
    global _scheduler

    # 1. Register run-loader callback (fires after every cache refresh)
    register_new_run_callback(_on_new_run)

    # 2. Start real-time file watcher (watchdog)
    file_watcher.register_callback(_on_new_run)
    file_watcher.start(HISTORY_FOLDER)

    # 3. APScheduler as fallback / periodic refresh
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _tick, "interval",
        seconds=AUTO_REFRESH_INTERVAL,
        id="eval_worker_poll",
        max_instances=1,
    )
    _scheduler.start()
    logger.info("online_eval_worker: started (watchdog + %ds poll)", AUTO_REFRESH_INTERVAL)


def stop():
    file_watcher.stop()
    if _scheduler:
        _scheduler.shutdown(wait=False)


def _tick():
    from backend.services import run_loader
    run_loader.force_refresh()


# ── New-run handler ───────────────────────────────────────────────────────────

_processing: set = set()  # guard against double-processing the same file

def _on_new_run(filename: str):
    if filename in _processing:
        return
    _processing.add(filename)
    try:
        logger.info("online_eval_worker: processing new run → %s", filename)
        run = get_run(filename)
        if not run:
            return
        _run_bug_detection(filename, run)
        _run_online_evaluators(filename, run)
        _run_automation_rules(filename, run)
        _run_sla_checks(filename)          # NEW: SLA breach detection
    finally:
        _processing.discard(filename)


def _run_sla_checks(filename: str):
    """Check all SLOs after a new run and fire webhooks on breach."""
    try:
        from backend.services.sla_calculator import check_and_fire_breaches
        check_and_fire_breaches(filename)
        logger.info("online_eval_worker: SLA checks complete for %s", filename)
    except Exception as e:
        logger.warning("online_eval_worker: SLA check failed for %s: %s", filename, e)


# ── Point 1: Bug detection ────────────────────────────────────────────────────

def _run_bug_detection(filename: str, run: dict):
    try:
        from backend.services.bug_detector import analyze_run
        all_runs  = get_all_runs()
        prev_runs = [r for r in all_runs if r["_filename"] != filename][:5]
        report    = analyze_run(run, prev_runs)
        reports   = load_or_default(BUG_REPORTS_FILE(), {})
        reports[filename] = report
        save_json(BUG_REPORTS_FILE(), reports)
        logger.info("bug_detection: %s bugs in %s", report["total"], filename)
        if report["critical"] > 0:
            from backend.services.webhook_sender import fire_event
            fire_event("bug_detected", {
                "filename": filename,
                "critical": report["critical"],
                "total":    report["total"],
                "firstBug": report["bugs"][0]["title"] if report["bugs"] else "",
            })
    except Exception as e:
        logger.warning("bug_detection failed for %s: %s", filename, e)


# ── Point 1 core: Online evaluators actually run metrics ─────────────────────

def _run_online_evaluators(filename: str, run: dict):
    import random
    evaluators = load_or_default(EVALUATORS_FILE(), [])
    metric_map = _get_metric_map()
    if not metric_map:
        logger.info("online_eval_worker: deepeval not available, skipping metric execution")
        return

    for ev in evaluators:
        if not ev.get("enabled"):
            continue
        sampling = ev.get("samplingRate", 1.0)
        if random.random() > sampling:
            continue
        try:
            _execute_evaluator(ev, filename, run, metric_map, evaluators)
        except Exception as e:
            logger.warning("evaluator '%s' failed: %s", ev.get("name"), e)

    save_json(EVALUATORS_FILE(), evaluators)


def _execute_evaluator(ev: dict, filename: str, run: dict, metric_map: dict, evaluators_list: list):
    """Actually instantiate and run a DeepEval metric on the run's test cases."""
    from deepeval import evaluate
    from deepeval.test_case import LLMTestCase

    metric_name  = ev.get("metric", "")
    threshold    = float(ev.get("threshold", 0.5))
    MetricClass  = metric_map.get(metric_name)
    if not MetricClass:
        logger.warning("evaluator: unknown metric '%s'", metric_name)
        return

    results = []
    test_cases = run.get("testCases") or []
    # Limit to 10 per evaluator run to avoid cost explosions
    for tc in test_cases[:10]:
        name = tc.get("name", "")
        try:
            case = LLMTestCase(
                input             = tc.get("input", ""),
                actual_output     = tc.get("actualOutput", "") or "",
                expected_output   = tc.get("expectedOutput"),
                retrieval_context = tc.get("retrievalContext") or [],
            )
            metric = MetricClass(threshold=threshold)
            metric.measure(case)
            results.append({
                "caseName":  name,
                "filename":  filename,
                "metric":    metric_name,
                "score":     round(metric.score, 4) if metric.score is not None else None,
                "success":   metric.success,
                "reason":    metric.reason,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "status":    "completed",
            })
            logger.info(
                "evaluator '%s': %s → %.3f (%s)",
                ev["name"], name, metric.score or 0, "PASS" if metric.success else "FAIL"
            )
        except Exception as e:
            results.append({
                "caseName":  name,
                "filename":  filename,
                "metric":    metric_name,
                "error":     str(e)[:200],
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "status":    "error",
            })
            logger.warning("evaluator '%s' on case '%s': %s", ev["name"], name, e)

    # Persist results back into the evaluator config
    for e in evaluators_list:
        if e.get("id") == ev.get("id"):
            e["results"] = (results + (e.get("results") or []))[:100]
            e["lastRun"]  = time.strftime("%Y-%m-%dT%H:%M:%S")
            e["lastRunCount"] = len(results)
            break


# ── Automation rules ──────────────────────────────────────────────────────────

def _run_automation_rules(filename: str, run: dict):
    import random
    rules = load_or_default(AUTOMATIONS_FILE(), [])
    for rule in rules:
        if not rule.get("enabled"):
            continue
        if random.random() > rule.get("samplingRate", 1.0):
            continue
        try:
            _apply_rule(rule, filename, run)
        except Exception as e:
            logger.warning("rule '%s' failed: %s", rule.get("name"), e)
    save_json(AUTOMATIONS_FILE(), rules)


def _apply_rule(rule: dict, filename: str, run: dict):
    action = rule.get("action", "")
    rule.setdefault("history", []).insert(0, {
        "filename":  filename,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "action":    action,
    })
    rule["history"]      = rule["history"][:20]
    rule["triggerCount"] = rule.get("triggerCount", 0) + 1

    if action == "webhook":
        from backend.services.webhook_sender import fire_event
        fire_event("rule_matched", {"rule": rule.get("name"), "filename": filename})

    logger.info("rule '%s': action '%s' on %s", rule.get("name"), action, filename)
