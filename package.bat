@echo off
chcp 65001 >nul
cd /d "%~dp0"

set VENV=backend\.venv
set BUILD_DIR=dist\FinanceSettlement
set VERSION=1.0.0

echo ========================================
echo   Financial Settlement System
echo   Package Builder v%VERSION%
echo ========================================
echo.

rem ---- Step 1: Clean previous build ----
echo [1/7] Cleaning previous build...
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "dist\FinanceSettlement.exe" del "dist\FinanceSettlement.exe"

rem ---- Step 2: Validate ----
echo [2/7] Validating environment...
if not exist "%VENV%\Scripts\python.exe" (
    echo ERROR: Virtual environment not found. Run setup.bat first.
    exit /b 1
)

rem ---- Step 3: Install dependencies ----
echo [3/7] Installing Python dependencies...
call "%VENV%\Scripts\pip" install --quiet -r backend\requirements.txt

rem ---- Step 4: Ensure version.json ----
echo [4/7] Ensuring version.json...
if not exist version.json (
    echo {"version": "1.0.0", "build": 1, "release_date": "2026-05-02", "update_url": ""} > version.json
)

rem ---- Step 5: Build frontend ----
echo [5/7] Building frontend...
cd frontend
call npx vite build
if %errorlevel% neq 0 ( echo ERROR: Frontend build failed & exit /b %errorlevel% )
cd ..

rem ---- Step 6: Install PyInstaller + build ----
echo [6/7] Installing PyInstaller...
call "%VENV%\Scripts\pip" install --quiet pyinstaller

where upx >nul 2>&1 && echo       UPX compression: enabled || echo       UPX compression: not found

echo.
echo Running PyInstaller (this may take several minutes)...
call "%VENV%\Scripts\pyinstaller" FinanceSettlement.spec --clean --noconfirm
if %errorlevel% neq 0 ( echo ERROR: PyInstaller build failed & exit /b %errorlevel% )

rem ---- Step 7: Copy root-level files to dist root ----
echo [7/7] Copying distribution files...
copy version.json "%BUILD_DIR%\" >nul
copy config.env.example "%BUILD_DIR%\config.env.example" >nul

rem ---- Step 8: Verify ----
echo [8/7] Verifying output...
set FAILED=0
if not exist "%BUILD_DIR%\FinanceSettlement.exe" set FAILED=1
if not exist "%BUILD_DIR%\version.json" set FAILED=1
if not exist "%BUILD_DIR%\_internal\frontend\dist\index.html" set FAILED=1
if not exist "%BUILD_DIR%\_internal\templates\games.xlsx" set FAILED=1
if "%FAILED%"=="1" ( echo ERROR: Verification failed - missing files & exit /b 1 )

echo.
echo ========================================
echo  BUILD SUCCESSFUL
echo  Output: %BUILD_DIR%
echo  Size:
dir /s "%BUILD_DIR%" | find "File(s)"
echo.
echo  To test: %BUILD_DIR%\FinanceSettlement.exe
echo ========================================
pause
