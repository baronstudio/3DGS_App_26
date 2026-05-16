@echo off
cd /d %~dp0

echo "--- Starting Backend Server ---"
start "Backend" cmd /c "call .\.venv\Scripts\activate.bat && uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload"

echo "--- Starting Frontend Server ---"
start "Frontend" cmd /c "cd frontend && npm run dev"

echo "--- Opening Application in Browser ---"
timeout /t 5 > nul
start http://localhost:5173
