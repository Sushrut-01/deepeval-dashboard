# ============================================================
# fix_dashboard_crash_loop.ps1 - paste into PowerShell as-is
# ============================================================

$dash    = "C:\Users\v-snistane\tools\deepeval-dashboard"
$venv    = "$dash\.venv"
$venvPy  = "$venv\Scripts\python.exe"
$sitePkg = "$venv\Lib\site-packages"
$hist    = "$dash\eval_history"

Write-Host "=== Step 1: Kill any running dashboard ===" -ForegroundColor Cyan
Get-Process python, pythonw -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
$still = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($still) { Write-Host "Port 5000 still LISTENING — reboot may be needed" -ForegroundColor Red }
else        { Write-Host "Port 5000 free" -ForegroundColor Green }

Write-Host "`n=== Step 2: Remove pip uninstall leftover dirs (~penai, ~nthropic, etc.) ===" -ForegroundColor Cyan
if (Test-Path $sitePkg) {
    $stale = Get-ChildItem -Path $sitePkg -Directory -Filter "~*" -ErrorAction SilentlyContinue
    if ($stale.Count -eq 0) { Write-Host "  None found." -ForegroundColor Green }
    foreach ($d in $stale) {
        Write-Host "  Removing $($d.Name)"
        Remove-Item -Path $d.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "  [WARN] venv not found at $sitePkg — re-run setup_dashboard_venv.py" -ForegroundColor Yellow
}

Write-Host "`n=== Step 3: Reinstall required packages into the dashboard venv ===" -ForegroundColor Cyan
if (Test-Path $venvPy) {
    & $venvPy -m pip install --force-reinstall --no-deps `
        fastapi uvicorn python-multipart starlette pydantic pydantic-core `
        openai anthropic
    Write-Host "  Done." -ForegroundColor Green
} else {
    Write-Host "  [FAIL] dashboard venv Python missing — re-run setup_dashboard_venv.py" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Step 4: Start dashboard with correct Python, NO --reload ===" -ForegroundColor Cyan
$env:DEEPEVAL_RESULTS_FOLDER = $hist
$env:DEEPEVAL_DISABLE_RELOAD = "1"     # informational — some run.py files honor this
Set-Location $dash

Write-Host "Booting dashboard...`n" -ForegroundColor Cyan
# Launch uvicorn directly (no --reload). This bypasses watchfiles entirely.
& $venvPy -m uvicorn backend.main:app --host 127.0.0.1 --port 5000