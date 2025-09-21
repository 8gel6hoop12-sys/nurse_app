# -*- coding: utf-8 -*-
"""
nurse_server.py — Webフロント用の簡易サーバ
※ 既存の run/*・status/*・files/*・review/*・ai/map_so・/nanda.xlsx 等は前のまま
   ここでは「内部保存」API（/save/*）だけ追加しています
"""
import os, io, json, threading, subprocess, signal
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

APP_DIR = Path(__file__).resolve().parent
os.chdir(APP_DIR)

# 既存のファイル名（nurse_app.pyと同じ）
ASSESS_RESULT_TXT = "assessment_result.txt"
ASSESS_FINAL_TXT  = "assessment_final.txt"
DIAG_RESULT_TXT   = "diagnosis_result.txt"
DIAG_FINAL_TXT    = "diagnosis_final.txt"
DIAG_JSON         = "diagnosis_candidates.json"
RECORD_RESULT_TXT = "record_result.txt"
RECORD_FINAL_TXT  = "record_final.txt"
PLAN_RESULT_TXT   = "careplan_result.txt"
PLAN_FINAL_TXT    = "careplan_final.txt"
NANDA_XLSX        = "nanda_db.xlsx"

# === 既存の実行・ポーリング用の最小実装（省略可：前のまま使ってOK） ===
TASKS = { "assessment": {}, "diagnosis": {}, "record": {}, "careplan": {} }
LOCK = threading.Lock()

def _spawn(name, cmd, stdin_text=None, env_overrides=None):
    with LOCK:
        if TASKS.get(name,{}).get("proc"):
            try:
                TASKS[name]["proc"].kill()
            except Exception:
                pass
        TASKS[name] = {"running": True, "done": False, "rc": None, "result": "", "stdout": "", "stderr": "", "proc": None}

    env = os.environ.copy()
    env.update({
        "AI_PROVIDER": "ollama",
        "OLLAMA_HOST": "http://127.0.0.1:11434",
        "OPENAI_API_KEY": "",
        "AI_LOG_DISABLE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
    })
    if env_overrides:
        env.update(env_overrides)

    def run():
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE if stdin_text is not None else None,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="ignore", cwd=str(APP_DIR), env=env
            )
            with LOCK: TASKS[name]["proc"] = proc
            out, err = proc.communicate(input=stdin_text)
            rc = proc.returncode
            with LOCK:
                TASKS[name].update({"running": False, "done": True, "rc": rc, "stdout": out or "", "stderr": err or ""})
                # 既存ツールがファイルへ出力する前提なので、resultは補助的に返す
                TASKS[name]["result"] = (out or "").strip()
        except Exception as e:
            with LOCK:
                TASKS[name].update({"running": False, "done": True, "rc": 1, "stderr": str(e)})

    th = threading.Thread(target=run, daemon=True)
    th.start()

def _cancel(name):
    with LOCK:
        proc = TASKS.get(name,{}).get("proc")
        if proc:
            try:
                proc.send_signal(signal.SIGTERM)
            except Exception:
                pass
        TASKS.setdefault(name,{}).update({"running": False, "done": False, "rc": None})

# === ここから 追加：内部保存 API ===
def _save_text(kind: str, text: str):
    kind = kind.lower().strip()
    mapping = {
        "assessment": ASSESS_FINAL_TXT,
        "diagnosis":  DIAG_FINAL_TXT,
        "record":     RECORD_FINAL_TXT,
        "careplan":   PLAN_FINAL_TXT,
    }
    fn = mapping.get(kind)
    if not fn:
        return False, f"unsupported kind: {kind}"
    try:
        Path(fn).write_text(text or "", encoding="utf-8", errors="ignore")
        # 次工程がファイルを読む想定なので、連携のために result 側にも複写しておくと安全
        # （assessmentは result と final が分かれていることがあるため）
        if kind == "assessment" and text:
            Path(ASSESS_RESULT_TXT).write_text(text, encoding="utf-8", errors="ignore")
        if kind == "diagnosis" and text:
            Path(DIAG_RESULT_TXT).write_text(text, encoding="utf-8", errors="ignore")
        if kind == "record" and text:
            Path(RECORD_RESULT_TXT).write_text(text, encoding="utf-8", errors="ignore")
        if kind == "careplan" and text:
            Path(PLAN_RESULT_TXT).write_text(text, encoding="utf-8", errors="ignore")
        return True, "ok"
    except Exception as e:
        return False, str(e)

class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj, code=200):
        buf = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(buf)))
        self.end_headers()
        self.wfile.write(buf)

    def _send_bytes(self, data: bytes, ctype="application/octet-stream"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- 簡易ルーティング（既存ルート＋/save/*だけ追加） ----
    def do_GET(self):
        p = urlparse(self.path).path

        # UI
        if p in ("/","/index.html","/nurse_ui.html"):
            html = Path("nurse_ui.html").read_bytes()
            return self._send_bytes(html, "text/html; charset=utf-8")

        # 静的（NANDA）
        if p == "/nanda.xlsx":
            if not Path(NANDA_XLSX).exists():
                return self._send_json({"ok": False, "error": "nanda_db.xlsx not found"}, 404)
            return self._send_bytes(Path(NANDA_XLSX).read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # 既存のファイル公開（結果確認）
        if p.startswith("/files/"):
            fn = p.replace("/files/","",1)
            q = Path(fn)
            if not q.exists():
                return self._send_json({"ok":False,"error":"not found"},404)
            return self._send_bytes(q.read_bytes(), "text/plain; charset=utf-8")

        # 既存：status/*
        if p.startswith("/status/"):
            key = p.split("/")[-1]
            st = TASKS.get(key, {"running": False, "done": False})
            return self._send_json(st)

        # ライブラリ（CDNはHTML内で読み込み済み）
        return self._send_json({"ok":False,"error":"not found"},404)

    def do_POST(self):
        p = urlparse(self.path).path
        ln = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(ln).decode("utf-8") if ln>0 else ""
        try:
            js = json.loads(body) if body else {}
        except Exception:
            js = {}

        # === 新規：/save/<kind> ===
        if p.startswith("/save/"):
            kind = p.split("/")[-1]
            ok, msg = _save_text(kind, js.get("text",""))
            return self._send_json({"ok": ok, "message": msg}, 200 if ok else 500)

        # === 既存：run/* （assessment / diagnosis / record / careplan） ===
        if p == "/run/assessment":
            S = js.get("S",""); O = js.get("O","")
            payload = f"{S}\n<<<SEP>>>\n{O}"
            _spawn("assessment", [os.sys.executable, "-X", "utf8", "assessment.py"], stdin_text=payload)
            return self._send_json({"ok": True})

        if p == "/run/diagnosis":
            _spawn("diagnosis", [os.sys.executable, "-X", "utf8", "diagnosis.py"])
            return self._send_json({"ok": True})

        if p == "/run/record":
            _spawn("record", [os.sys.executable, "-X", "utf8", "record.py"])
            return self._send_json({"ok": True})

        if p == "/run/careplan":
            _spawn("careplan", [os.sys.executable, "-X", "utf8", "careplan.py"])
            return self._send_json({"ok": True})

        # 既存：cancel/*
        if p.startswith("/cancel/"):
            key = p.split("/")[-1]
            _cancel(key)
            return self._send_json({"ok": True})

        # 既存：review/* （任意）
        if p.startswith("/review/"):
            # ここは既存ロジックでOK。単純に record_review.py 等に流すなら自前でどうぞ。
            # 便宜上ここでは渡されたテキストを軽く整形した体で返す
            text = js.get("text","").strip()
            review = text.strip()
            return self._send_json({"ok": True, "review": review})

        # 既存：AI S/Oマッピング
        if p == "/ai/map_so":
            # ここは既存（ローカルAIに委譲）でOK。サンプルとして単純パース。
            t = (js.get("text") or "").strip()
            mapped = {"S":{}, "O":{}}
            # 簡易サンプル：数字パターンなど
            # 実運用では assessment.py 側と同条件のプロンプトでOllamaを叩く実装を置く
            return self._send_json({"ok": True, "mapped": mapped})

        return self._send_json({"ok": False, "error": "not found"}, 404)

def main(host="127.0.0.1", port=8000):
    httpd = HTTPServer((host, port), Handler)
    print(f"Serving on http://{host}:{port}")
    httpd.serve_forever()

if __name__ == "__main__":
    main()
