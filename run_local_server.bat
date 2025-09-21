@echo off
setlocal
REM --- この bat と同じフォルダにある nurse_server.py を起動します ---
cd /d "%~dp0"

REM venv があれば優先使用
set PY=python
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

REM ログ保存先
if not exist logs mkdir logs

REM 既存の同ポートプロセスを念のため終了（Windowsのみ）
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8787') do taskkill /PID %%p /F >nul 2>&1

REM サーバ起動（UTF-8で）
%PY% -X utf8 nurse_server.py --port 8787 >> "logs\nurse_server.log" 2>&1
