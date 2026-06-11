@echo off
chcp 65001 >nul
title DeepAgent Chat - Development Server
cd /d "%~dp0"

echo ============================================
echo   DeepAgent Chat Launcher
echo ============================================

:: Check virtual environment
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please run deploy.bat first.
    pause
    exit /b 1
)

:: Check .env
if not exist ".env" (
    echo [WARNING] .env file not found, creating from .env.example...
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo .env created. Please edit API keys in .env
    ) else (
        echo [WARNING] .env.example not found either, skipping
    )
)

:: Check database initialization
echo [CHECK] Database status...
call venv\Scripts\python _check_db.py 2>nul
if errorlevel 1 (
    echo [WARNING] Database initialization error, please check .env
)

:: Launch
echo.
echo [START] Starting development server...
echo   Local address: http://localhost:5000
echo   Press Ctrl+C to stop
echo.
call venv\Scripts\activate && python run.py


pause