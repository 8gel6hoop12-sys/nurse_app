@echo off
setlocal
cd /d "%~dp0"
cd ..
if not exist ".venv\Scripts\python.exe" (
  echo 初回セットアップがまだのようです。setup_win.bat を先に実行してください。
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8787/"
".venv\Scripts\python.exe" nurse_server.py --port 8787
