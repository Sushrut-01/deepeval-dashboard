# start-dashboard.ps1 — one-click dashboard launcher
# Independent of any project's venv.

$dash = "C:\Users\v-snistane\tools\deepeval-dashboard"
$venv = "$dash\.venv\Scripts\Activate.ps1"
$hist = "$dash\eval_history"

if (-not (Test-Path $venv)) {
    Write-Host "Dashboard venv not found. Run setup_dashboard_venv.py first." -ForegroundColor Red
    exit 1
}

# Activate the dashboard's own venv
& $venv

# Set history folder for THIS session
$env:DEEPEVAL_RESULTS_FOLDER = $hist
Write-Host "DEEPEVAL_RESULTS_FOLDER = $env:DEEPEVAL_RESULTS_FOLDER" -ForegroundColor Cyan

# Boot
Set-Location $dash
python run.py