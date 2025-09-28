@echo off
setlocal

REM 仮想環境があれば優先（任意）
if exist "%~dp0venv\Scripts\python.exe" (
  "%~dp0venv\Scripts\python.exe" -X utf8 "%~dp0nurse_app.py"
  goto :eof
)

REM 通常のpythonで起動
python -X utf8 "%~dp0nurse_app.py"
if %ERRORLEVEL% NEQ 0 (
  echo.
  echo 起動に失敗しました。PyQt5 が未導入の可能性があります。
  echo 例:  pip install PyQt5 pandas openpyxl
  pause
)
