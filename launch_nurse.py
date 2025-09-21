# -*- coding: utf-8 -*-
"""
launch_nurse.py — URLスキーム登録 & 起動ランチャ（Windows向け）
使い方:
  (管理側/初回のみ)  python launch_nurse.py --register
  (ユーザー操作)      GitHub Pages の「▶ スタート」→ nurseapp://start → 本体起動
"""
from __future__ import annotations
import os, sys, subprocess, platform, argparse, time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
NURSE_MAIN = APP_DIR / "nurse_app.py"   # 本体（PyQt）

def _spawn_main():
    if not NURSE_MAIN.exists():
        raise FileNotFoundError(f"{NURSE_MAIN.name} が見つかりません")
    kwargs={}
    if platform.system().lower().startswith("win"):
        DETACHED=0x00000008  # DETACHED_PROCESS
        NOWIN=0x08000000     # CREATE_NO_WINDOW
        kwargs["creationflags"]=DETACHED|NOWIN
    env=os.environ.copy()
    # 本体側で既にプライバシー徹底(OLLAMA固定/OpenAI無効)をしているため、
    # 念のため同じ環境も渡しておく（無くても本体で上書きされる）
    env.update({
        "PYTHONUTF8":"1","PYTHONIOENCODING":"utf-8",
        "AI_PROVIDER":"ollama","AI_LOG_DISABLE":"1","OPENAI_API_KEY":"",
        "AI_MODEL":env.get("AI_MODEL","qwen2.5:7b-instruct"),
        "OLLAMA_HOST":env.get("OLLAMA_HOST","http://127.0.0.1:11434"),
    })
    subprocess.Popen([sys.executable,"-X","utf8",str(NURSE_MAIN)],
                     cwd=str(APP_DIR), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, **kwargs)

# ---- Windows: nurseapp:// スキーム登録（HKCU）
def _register_scheme():
    if platform.system().lower()!="windows":
        print("Windows以外の自動登録は対象外です（手動でアプリ化が必要）")
        return
    import winreg
    base=r"Software\Classes\nurseapp"
    # URLを受け取ったとき、このスクリプトを実行
    target=f'"{sys.executable}" -X utf8 "{str(Path(__file__).resolve())}" "%1"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:NurseApp")
        winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base+r"\shell\open\command") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, target)
    print("登録完了: nurseapp://start で起動できます。")

def _unregister_scheme():
    if platform.system().lower()!="windows": return
    import winreg
    try:
        for sub in [r"shell\open\command", r"shell\open", r"shell", ""]:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\nurseapp\\"+sub if sub else r"Software\Classes\nurseapp")
        print("スキーム削除完了")
    except Exception:
        pass

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--register",action="store_true", help="nurseapp:// スキーム登録（Windows）")
    ap.add_argument("--unregister",action="store_true")
    ap.add_argument("--reinstall",action="store_true")
    a=ap.parse_args()

    if a.reinstall:
        _unregister_scheme(); _register_scheme(); return
    if a.register:
        _register_scheme(); return
    if a.unregister:
        _unregister_scheme(); return

    # nurseapp://start などで渡ってくるURLは argv[1] に入ることが多い
    # ここでは単に受けて本体を起動するだけでOK（引数は使わない）
    try:
        _spawn_main()
    except Exception as e:
        # コンソールを出さない設計なので、失敗時だけ簡単なフォールバック
        # （必要ならログに書き出すなど拡張可）
        sys.stderr.write(f"起動に失敗しました: {e}\n")
        raise

if __name__=="__main__":
    main()
