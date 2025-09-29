@echo off
setlocal
cd /d "%~dp0"
REM フォルダ: nurse_app\files から 1つ上へ（プロジェクトルート）
cd ..

echo [1/4] venv 準備…
if not exist ".venv" (
  py -3 -m venv .venv || (echo venv作成失敗 & pause & exit /b 1)
)

echo [2/4] pip アップグレード…
".venv\Scripts\python.exe" -m pip install -U pip

echo [3/4] 依存インストール…
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo [4/4] 動作確認…
".venv\Scripts\python.exe" nurse_server.py --port 8787
pause
