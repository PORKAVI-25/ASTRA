# Development launch helper for ASTRA

param (
    [string]$Service = "all"
)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Launching ASTRA Development Environment " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

if ($Service -eq "backend" -or $Service -eq "all") {
    Write-Host "Starting FastAPI Backend on http://127.0.0.1:8000..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\..'; .\.venv\Scripts\Activate.ps1; python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000"
}

if ($Service -eq "frontend" -or $Service -eq "all") {
    Write-Host "Starting Vite React Frontend on http://localhost:5173..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\..\frontend'; npm run dev"
}

Write-Host "`nASTRA services initiated." -ForegroundColor Cyan
Write-Host "Backend Docs: http://127.0.0.1:8000/docs"
Write-Host "Frontend App: http://localhost:5173"
