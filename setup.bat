@echo off
setlocal
cd /d "%~dp0"

echo [INFO] 初回セットアップを開始します...

:: nurse_app.zip を解凍
powershell -command "Expand-Archive -Force 'nurse_app.zip' '%CD%\nurse_app'"

:: venv 作成
python -m venv .venv
call .venv\Scripts\activate

:: 依存関係インストール
pip install -r nurse_app\requirements.txt

echo [INFO] セットアップ完了。アプリを起動します...
start Start.bat
exit
