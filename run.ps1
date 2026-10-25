# VitaranIQ Engine PowerShell Launcher
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  VitaranIQ: AI-Powered FMCG Distribution Intelligence Engine" -ForegroundColor Green
Write-Host "  Problem Statement 2 | Team Innovate-x (Lead: Devendra Nimbalkar)" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

& "$PSScriptRoot\backend\.venv\Scripts\python.exe" "$PSScriptRoot\run_vitaraniq.py" $args
