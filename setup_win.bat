@echo off
setlocal
cd /d "%~dp0\.."

:: 1) Python
where python >nul 2>nul
if errorlevel 1 (
  echo [INFO] Installing Python via winget...
  winget install -e --id Python.Python.3 --accept-package-agreements --accept-source-agreements
)

:: 2) venv
if not exist ".venv" (
  echo [INFO] Creating venv...
  python -m venv .venv
)

:: 3) pip & requirements（任意：無ければスキップ）
call .venv\Scripts\python -m pip install -U pip
if exist requirements.txt (
  call .venv\Scripts\python -m pip install -r requirements.txt
)

:: 4) Ollama
where ollama >nul 2>nul
if errorlevel 1 (
  echo [INFO] Installing Ollama...
  winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
)

:: 5) モデル
set "AI_MODEL=qwen2.5:7b-instruct"
set FOUND=
for /f "tokens=* delims=" %%A in ('ollama list ^| findstr /i "%AI_MODEL%"') do set FOUND=1
if not defined FOUND (
  echo [INFO] Pulling %AI_MODEL% ...
  ollama pull %AI_MODEL%
)

:: 6) 起動
set "AI_PROVIDER=ollama"
set "AI_MODEL=qwen2.5:7b-instruct"
set "OLLAMA_HOST=http://127.0.0.1:11434"
set "AI_LOG_DISABLE=1"

start "" "%CD%\.venv\Scripts\python.exe" nurse_server.py --port 8787
timeout /t 1 >nul
start "" http://127.0.0.1:8787/
echo 起動しました。ブラウザが開かない場合は http://127.0.0.1:8787/ を開いてください。
pause

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
