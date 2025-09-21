# -*- coding: utf-8 -*-
"""
launch_nurse.py — URLスキーム(Windows)対応のランチャ
使い方:
  1) 一度だけ登録:  python launch_nurse.py --register
     → nurseapp://open をOSに登録
  2) 以後は nurseapp://open をクリックするだけでOK
     （または python launch_nurse.py でも可）
"""
import sys, os, time, webbrowser, subprocess, platform, argparse
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

PORT = int(os.environ.get("NURSE_PORT", "8787"))
HOST = "127.0.0.1"
URL  = f"http://{HOST}:{PORT}"

def _ping(path="/ai/health", timeout=0.9):
    try:
        with urlopen(f"{URL}{path}", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

def _spawn_server():
    py = sys.executable
    here = Path(__file__).resolve().parent
    srv = here / "nurse_server.py"
    if not srv.exists():
        raise RuntimeError("nurse_server.py が見つかりません")
    kwargs = {}
    if platform.system().lower().startswith("win"):
        CREATE_NO_WINDOW = 0x08000000
        DETACHED_PROCESS = 0x00000008
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([py, "-X", "utf8", str(srv), "--port", str(PORT)],
                     cwd=str(here), stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, **kwargs)

def open_ui():
    # サーバがいなければ起動
    if not _ping():
        _spawn_server()
        # 起動待ち
        for _ in range(60):
            if _ping():
                break
            time.sleep(0.3)
    # ブラウザで開く
    webbrowser.open(f"{URL}/", new=2)

def _reg_add():
    # Windows 専用: nurseapp:// を登録
    if not platform.system().lower().startswith("win"):
        print("Windows以外では --register は不要です。"); return
    import winreg
    exe = sys.executable.replace("\\", "\\\\")
    this = str(Path(__file__).resolve()).replace("\\", "\\\\")
    cmd = f'"{exe}" -X utf8 "{this}"'
    # HKEY_CLASSES_ROOT\nurseapp\shell\open\command
    with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, r"nurseapp") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:NurseApp")
        winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, r"nurseapp\shell\open\command") as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, cmd)
    print("URLスキーム nurseapp:// を登録しました。")
    print("ブラウザやREADME内で nurseapp://open を押すと起動します。")

def _reg_del():
    if not platform.system().lower().startswith("win"):
        return
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, r"nurseapp\shell\open\command")
        winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, r"nurseapp\shell\open")
        winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, r"nurseapp\shell")
        winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, r"nurseapp")
        print("URLスキーム nurseapp:// を削除しました。")
    except Exception as e:
        print("削除に失敗:", e)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--unregister", action="store_true")
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()

    if args.register:
        _reg_add(); return
    if args.unregister:
        _reg_del(); return
    # nurseapp://open から来たときに --open を付ける必要はありません
    open_ui()

if __name__ == "__main__":
    main()
