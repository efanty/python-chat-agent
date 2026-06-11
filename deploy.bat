@echo off
chcp 65001 >nul
title DeepAgent Chat - Setup
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo [1/5] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.10+
    echo        https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    if %%a lss 3 (
        echo ERROR: Need Python 3.10+, found: %PYVER%
        pause & exit /b 1
    )
    if %%a equ 3 if %%b lss 10 (
        echo ERROR: Need Python 3.10+, found: %PYVER%
        pause & exit /b 1
    )
)
echo   Python %PYVER% OK

echo [2/5] Setting up virtual environment...
if not exist "venv\Scripts\python.exe" (
    echo   Creating venv...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo ERROR: Failed to create virtual environment
        pause & exit /b 1
    )
    echo   Virtual environment created
) else (
    echo   Virtual environment already exists
)

echo [3/5] Installing Python packages...
call venv\Scripts\python -m pip install --upgrade pip -q
call venv\Scripts\pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo ERROR: Package installation failed. Check network.
    pause & exit /b 1
)
echo   Dependencies installed

echo [4/5] Initializing project...
if not exist ".env" (
    if exist ".env.example" (
        echo   Creating .env from .env.example...
        copy ".env.example" ".env" >nul
        echo   .env file created. Edit it to add your API keys.
    ) else (
        echo   WARNING: .env.example not found
    )
)

call venv\Scripts\python _deploy_setup.py
if !errorlevel! neq 0 (
    echo ERROR: Project initialization failed. Check .env configuration.
    pause & exit /b 1
)

echo [5/5] Starting development server...
echo.
echo ============================================
echo   DeepAgent Chat is ready
echo   Open:  http://localhost:5000
echo   Admin: admin (password printed above)
echo   Press Ctrl+C to stop the server
echo ============================================
echo.

call venv\Scripts\python run.py

echo.
echo Server stopped.
pause
endlocal
