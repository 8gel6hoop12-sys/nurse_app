@echo off
setlocal
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
  echo [.venv がありません。先に scripts\setup_win.bat を実行してください]
  pause
  exit /b 1
)

set "AI_PROVIDER=ollama"
set "AI_MODEL=qwen2.5:7b-instruct"
set "OLLAMA_HOST=http://127.0.0.1:11434"
set "AI_LOG_DISABLE=1"

start "" "%CD%\.venv\Scripts\python.exe" nurse_server.py --port 8787
timeout /t 1 >nul
start "" http://127.0.0.1:8787/
