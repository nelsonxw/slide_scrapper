@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo     PowerPoint Web Scraper ^& Slide Preview Studio
echo     Firebase: gs://slide-preview.firebasestorage.app
echo ===================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: 1. Check Python installation
echo [1/5] Checking Python environment...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found in your PATH!
    echo Please install Python 3.11+ and ensure 'Add Python to PATH' is checked.
    pause
    exit /b 1
)

:: 2. Check Node.js / npm installation
echo [2/5] Checking Node.js / npm environment...
where npm.cmd >nul 2>nul
if %errorlevel% neq 0 (
    where npm >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Node.js / npm is not found in your PATH!
        echo Please install Node.js from https://nodejs.org/
        pause
        exit /b 1
    )
)

:: 3. Check configuration (.env)
echo [3/5] Checking configuration (.env)...
if not exist ".env" (
    if exist ".env.example" (
        echo Creating .env from .env.example...
        copy ".env.example" ".env" >nul
    )
)

:: 4. Check & install Python backend dependencies
echo [4/5] Verifying Python backend dependencies...
python -c "import fastapi, uvicorn, pptx, bs4, httpx, PIL, firebase_admin, pydantic" 2>nul
if %errorlevel% neq 0 (
    echo Installing missing backend packages from backend/requirements.txt...
    python -m pip install -r "%SCRIPT_DIR%backend\requirements.txt"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install Python dependencies.
        pause
        exit /b 1
    )
) else (
    echo Backend dependencies verified.
)

:: 5. Check & install Frontend npm dependencies
echo [5/5] Verifying Frontend dependencies...
if not exist "%SCRIPT_DIR%frontend\node_modules" (
    echo Installing frontend packages with npm...
    cd /d "%SCRIPT_DIR%frontend"
    call npm.cmd install
    if %errorlevel% neq 0 (
        call npm install
    )
    cd /d "%SCRIPT_DIR%"
) else (
    echo Frontend dependencies verified.
)

echo.
echo ===================================================
echo  Starting Application Services...
echo ===================================================

:: Start Backend API Server
set "PYTHONPATH=%SCRIPT_DIR%backend"
start "Slide Scrapper - Backend API" cmd /k "cd /d "%SCRIPT_DIR%backend" && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

:: Start Frontend UI Dev Server
start "Slide Scrapper - Frontend UI" cmd /k "cd /d "%SCRIPT_DIR%frontend" && npm.cmd run dev"

echo.
echo ===================================================
echo  All services are running!
echo    - Frontend UI:  http://localhost:5173
echo    - Backend API:  http://localhost:8000
echo    - API Docs:     http://localhost:8000/docs
echo ===================================================
echo.
timeout /t 3 >nul
start http://localhost:5173
