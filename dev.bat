@echo off
rem Development helper scripts (directive §280)

if "%1"=="" goto help
if "%1"=="backend" goto backend
if "%1"=="frontend" goto frontend
if "%1"=="test" goto test
if "%1"=="install" goto install
goto help

:backend
cd /d %~dp0backend
..\.venv\Scripts\python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
goto :eof

:frontend
cd /d %~dp0frontend
npm run dev
goto :eof

:test
cd /d %~dp0backend
..\.venv\Scripts\python -m pytest tests --timeout=300
goto :eof

:install
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install numpy scipy fastapi "uvicorn[standard]" pydantic websockets aiosqlite pytest pytest-timeout httpx python-multipart
cd frontend && npm install
goto :eof

:help
echo Usage: dev.bat [backend^|frontend^|test^|install]
