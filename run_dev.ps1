# Livelihood Navigator (SIH26097) - PowerShell Dev Launcher
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Livelihood Navigator (SIH26097) - Starting Local Stack" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path "backend\.env")) {
    Write-Host "Creating backend\.env from .env.example..." -ForegroundColor Yellow
    Copy-Item "backend\.env.example" "backend\.env"
}

Write-Host "`nStarting Backend (FastAPI on http://127.0.0.1:8000)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd backend; python -m uvicorn app.main:app --reload --port 8000"

Write-Host "`nStarting Frontend (Vite on http://localhost:5173)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm run dev"

Write-Host "`nStack is booting up!" -ForegroundColor Cyan
Write-Host "  - App:      http://localhost:5173" -ForegroundColor White
Write-Host "  - Admin:    http://localhost:5173/admin" -ForegroundColor White
Write-Host "  - Swagger:  http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
