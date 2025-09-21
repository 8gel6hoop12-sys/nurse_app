# -*- coding: utf-8 -*-
"""
launch_nurse.py — 看護アプリ起動ランチャ（URLスキーム登録つき・Windows向け）
使い方:
  初回1回だけ  : python launch_nurse.py --register
  以後いつでも : nurseapp://open をクリック / python launch_nurse.py
オプション:
  --unregister     スキームの解除
  --reinstall      再登録（上書き）
  --port 8787      ポート変更（既定 8787）
"""
from __future__ import annotations
import os, sys, time, webbrowser, subprocess, platform, argparse, shutil
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PORT    = int(os.environ.get("NURSE_PORT", "8787"))
HOST    = "127.0.0.1"
URL     = f"http://{HOST}:{PORT}"

def _ping(path="/ai/health", timeout=0.7) -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(f"{URL}{path}", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

def _spawn_server(port: int):
    """nurse_server.py をバックグラウンド起動（コンソール非表示）"""
    srv = APP_DIR / "nurse_server.py"
    if not srv.exists():
        raise RuntimeError(f"{srv.name} が見つかりません（{APP_DIR}）")

    py = sys.executable
    kwargs = {}
    if platform.system().lower().startswith("win"):
        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True

    env = os.environ.copy()
    env.update({
        "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
        # プライバシー徹底: OpenAIは空、Ollama固定
        "AI_PROVIDER": "ollama",
        "AI_LOG_DISABLE": "1",
        "OPENAI_API_KEY": "",
        "AI_MODEL": env.get("AI_MODEL", "qwen2.5:7b-instruct"),
        "OLLAMA_HOST": env.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        "NURSE_PORT": str(port),
    })

    subprocess.Popen(
        [py, "-X", "utf8", str(srv), "--host", HOST, "--port", str(port)],
        cwd=str(APP_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        **kwargs,
    )

def open_ui(port: int):
    """サーバが無ければ起動→立ち上がったらブラウザで開く"""
    global URL
    URL = f"http://{HOST}:{port}"
    if not _ping():
        _spawn_server(port)
        # 起動待ち（最大 ~20秒）
        for _ in range(100):
            if _ping():
                break
            time.sleep(0.2)
    webbrowser.open(f"{URL}/", new=2)

# ---------- URLスキーム登録（管理者権限いらない HKCU を使用） ----------
def _register_scheme():
    if not platform.system().lower().startswith("win"):
        print("Windows以外は登録不要/非対応です。"); return

    import winreg
    # HKCU\Software\Classes\nurseapp\shell\open\command
    base = r"Software\Classes\nurseapp"
    exe  = sys.executable
    target = f'"{exe}" -X utf8 "{str(Path(__file__).resolve())}"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:NurseApp")
        winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, target)

    print("URLスキームを登録しました： nurseapp://open")
    print("このリンクをクリックすると本アプリが起動します。")

def _unregister_scheme():
    if not platform.system().lower().startswith("win"):
        return
    import winreg
    try:
        base = r"Software\Classes\nurseapp\shell\open\command"
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base)
        base = r"Software\Classes\nurseapp\shell\open"
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base)
        base = r"Software\Classes\nurseapp\shell"
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base)
        base = r"Software\Classes\nurseapp"
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base)
        print("URLスキーム nurseapp:// を削除しました。")
    except Exception as e:
        print("削除に失敗:", e)

# ---------- エントリ ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--register",   action="store_true", help="URLスキーム登録")
    ap.add_argument("--unregister", action="store_true", help="URLスキーム削除")
    ap.add_argument("--reinstall",  action="store_true", help="登録し直し（削除→登録）")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()

    if args.reinstall:
        _unregister_scheme(); _register_scheme(); return
    if args.register:
        _register_scheme(); return
    if args.unregister:
        _unregister_scheme(); return

    # nurseapp://open から呼ばれた時もここに来る
    open_ui(args.port)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 失敗時でも原因がわかるように標準出力へ
        print("[launch_nurse] error:", e)
        raise
