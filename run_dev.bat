@echo off
echo ============================================================
echo   Livelihood Navigator (SIH26097) - Starting Local Stack
echo ============================================================

REM Check for backend .env
if not exist "backend\.env" (
    echo Creating backend\.env from .env.example...
    copy "backend\.env.example" "backend\.env" >nul
)

echo.
echo Starting Backend (FastAPI on http://127.0.0.1:8000)...
start "Backend - Livelihood Navigator" cmd /k "cd backend && python -m uvicorn app.main:app --reload --port 8000"

echo.
echo Starting Frontend (Vite on http://localhost:5173)...
start "Frontend - Livelihood Navigator" cmd /k "cd frontend && npm run dev"

echo.
echo Stack is booting up!
echo   - App:      http://localhost:5173
echo   - Admin:    http://localhost:5173/admin
echo   - Swagger:  http://127.0.0.1:8000/docs
echo ============================================================
