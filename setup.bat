@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] Creating Python virtual environment...
python -m venv backend\.venv

echo [2/3] Installing backend dependencies...
call backend\.venv\Scripts\pip install -r backend\requirements.txt
echo [2.1/3] Installing dev dependencies...
call backend\.venv\Scripts\pip install -r backend\requirements-dev.txt

echo [3/3] Installing frontend dependencies...
cd frontend
call npm install
cd ..

echo.
echo ========================================
echo  Setup complete!
echo.
echo  Start dev servers:
echo    Terminal 1: backend\.venv\Scripts\uvicorn backend.main:app --reload --port 8770
echo    Terminal 2: cd frontend ^&^& npx vite --port 5173
echo.
echo  Or run production:
echo    start.bat
echo ========================================
pause
