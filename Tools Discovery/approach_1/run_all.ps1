Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Running All Scripts" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Loading Google Sheets with Formatting..." -ForegroundColor Green
python load_google_sheets_with_formatting.py
Write-Host "Google Sheets with Formatting complete. Added/Updated active_tools.csv and removed_tools.csv" -ForegroundColor Green
Write-Host ""

Write-Host "Running Gemini Search with Web..." -ForegroundColor Green
python gemini_search_with_web.py
Write-Host "Gemini search with web complete. Check for new_tools.csv" -ForegroundColor Green
Write-Host ""

Write-Host "Running Main Second Pass Script (Filtering, Verification, Enrichment)..." -ForegroundColor Green
python second_pass.py
Write-Host "Main second pass complete. Check for new_tools_filtered.csv and new_tools_final.csv" -ForegroundColor Green
Write-Host ""

Write-Host "Running URL Checker..." -ForegroundColor Green
python url_checker.py
Write-Host "URL check complete. Check for new_tools_with_validation.csv" -ForegroundColor Green
Write-Host ""

Write-Host "Running Third Pass (Data Completion)..." -ForegroundColor Green
python third_pass.py
Write-Host "Third pass complete. Check for new_tools_complete.csv" -ForegroundColor Green
Write-Host ""

# This is the crucial step to ensure the next run uses the most up-to-date data.
Write-Host "Synchronizing the final, completed data for the next run..." -ForegroundColor Cyan
if (Test-Path -Path "new_tools_complete.csv") {
    Copy-Item -Path "new_tools_complete.csv" -Destination "new_tools.csv" -Force
    Write-Host "Synchronization successful. 'new_tools.csv' is now up to date." -ForegroundColor Cyan
} else {
    Write-Host "Warning: 'new_tools_complete.csv' not found. Synchronization skipped." -ForegroundColor Yellow
}
Write-Host ""


Write-Host "Process complete! Check the final output file:" -ForegroundColor Yellow
Write-Host "- new_tools_complete.csv - The most up-to-date and complete tool list." -ForegroundColor White


Write-Host "Before running the final formatter, You will need to manually verify the new_tools_complete.csv file. Change the status of the tools from 'Unverfied' to 'Verified'. All the tools that are AI verified and Hyuman Verfied would be selected for the final formatter." -ForegroundColor White

Write-Host "Once done, run formatter.ps1" -ForegroundColor Yellow

if ($Host.UI.RawUI) {
    Write-Host "Press any key to continue..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") 
} 