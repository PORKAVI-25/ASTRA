# PowerShell script to run all ASTRA test suites and verifications

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Running ASTRA Phase 0 Automated Tests    " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Backend Pytest
Write-Host "`n[1/3] Running Backend Pytest Suite..." -ForegroundColor Yellow
$pytestResult = & .\.venv\Scripts\python.exe -m pytest tests/ -v
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Backend tests failed!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Backend tests passed." -ForegroundColor Green

# 2. Frontend Type Check & Build
Write-Host "`n[2/3] Checking Frontend TypeScript & Vite Build..." -ForegroundColor Yellow
Push-Location frontend
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Frontend build failed!" -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location
Write-Host "✅ Frontend build passed." -ForegroundColor Green

# 3. Offline Policy Compliance Check
Write-Host "`n[3/3] Scanning for Offline Policy Compliance..." -ForegroundColor Yellow
& .\.venv\Scripts\python.exe scripts/check_offline.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Offline policy violations detected!" -ForegroundColor Red
    exit 1
}

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host " ALL PHASE 0 VERIFICATIONS PASSED!       " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
