@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PORT=8770

echo [1/2] Building frontend...
cd frontend
call npx vite build
if %errorlevel% neq 0 (
    echo Frontend build failed!
    pause
    exit /b %errorlevel%
)
cd ..

echo [2/2] Starting server on port %PORT%...
set FINANCE_PORT=%PORT%
start "Finance-Server" cmd /c "call backend\.venv\Scripts\python backend\run.py"

timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo  Server:  http://localhost:%PORT%
echo  API Doc: http://localhost:%PORT%/docs
echo ========================================
start http://localhost:%PORT%
echo Close this window to stop the server.
pause
