# run_bridge_with_tracing.ps1
# Runs the PlayReady RAGAS bridge with tracing enabled and pointed at the
# central dashboard history folder.

$proj = "C:\Users\v-snistane\playready-qa-automation"
$venv = "$proj\.venv\Scripts\Activate.ps1"

# Tell deepeval where to write traces and runs (same folder as the dashboard reads)
$env:DEEPEVAL_RESULTS_FOLDER = "C:\Users\v-snistane\tools\deepeval-dashboard\eval_history"
# Make sure tracing is enabled (some versions read this)
$env:DEEPEVAL_TELEMETRY_OPT_OUT = "YES"   # never call confident-ai cloud (compliance-safe)
$env:DEEPEVAL_TRACE_ENABLED     = "YES"

& $venv
Set-Location $proj
$env:PYTHONPATH = "."
python scripts\run_ragas_bridge.py