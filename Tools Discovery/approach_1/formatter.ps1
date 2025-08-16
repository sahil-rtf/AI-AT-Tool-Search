Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Running Final Formatter" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Running Final Formatter..." -ForegroundColor Green
python formatter.py
Write-Host "Formatter complete. Check for 'ready_for_import.csv'." -ForegroundColor Green
Write-Host ""

if (Test-Path "ready_for_import.csv") {
    Write-Host "Appending new tools to active_tools.csv..." -ForegroundColor Green
    Get-Content "ready_for_import.csv" | Select-Object -Skip 1 | Add-Content "active_tools.csv"
    Write-Host "Append complete." -ForegroundColor Green
    Write-Host ""
    
    # Append results to Google Sheets
    Write-Host "Appending results to Google Sheets..." -ForegroundColor Green
    python append_to_google_sheets.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Google Sheets append complete." -ForegroundColor Green
    } else {
        Write-Host "Google Sheets append failed. Check the logs for details." -ForegroundColor Red
    }
    Write-Host ""
} else {
    Write-Host "No new tools were formatted. Skipping append." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "Updating vector database..." -ForegroundColor Green
Push-Location "../../vector_database"
python main.py
Pop-Location
Write-Host "Vector database updated." -ForegroundColor Green
Write-Host ""

Write-Host "Process complete! Check the final output file:" -ForegroundColor Yellow
Write-Host "- ready_for_import.csv - The final, ready-to-import tool list." -ForegroundColor White
Write-Host "- active_tools.csv - The updated master list of tools." -ForegroundColor White

if ($Host.UI.RawUI) {
    Write-Host "Press any key to continue..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
} 