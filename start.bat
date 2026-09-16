@echo off
title IG Lead Scraper — Starting...
color 0A

echo.
echo  ============================================
echo   IG Reel Business Lead Scraper
echo   Powered by FastAPI + instagrapi
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: Install dependencies if needed
echo [1/3] Checking Python dependencies...
pip install -r "%~dp0requirements.txt" --quiet --disable-pip-version-check
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies. Check your internet connection.
    pause
    exit /b 1
)

echo [2/3] Dependencies OK!
echo [3/3] Starting server at http://127.0.0.1:8000 ...
echo.
echo  ====================================================
echo   Open your browser and go to:
echo   http://127.0.0.1:8000
echo  ====================================================
echo.
echo  Press Ctrl+C to stop the server.
echo.

:: Open browser after 2 seconds
start "" /b cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"

:: Run the FastAPI server
cd /d "%~dp0backend"
python -m uvicorn main:app --host 127.0.0.1 --port 8000

pause
