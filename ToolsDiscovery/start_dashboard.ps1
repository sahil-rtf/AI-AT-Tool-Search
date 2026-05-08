# start_dashboard.ps1
# Launches the AT Tool Discovery web dashboard.
# Run from the ToolsDiscovery folder:
#   .\start_dashboard.ps1

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=== AT Tool Discovery -- Web Dashboard ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "Checking dependencies..." -ForegroundColor DarkGray
pip install flask --quiet

Write-Host "Starting dashboard at http://localhost:5000" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

python app.py
