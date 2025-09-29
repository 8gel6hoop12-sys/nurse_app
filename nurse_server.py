# -*- coding: utf-8 -*-
"""
nurse_server.py — ローカルWebサーバ（UI/API/静的配信）
起動:  python nurse_server.py --port 8787
"""
import os, json, threading, argparse, re, runpy, io, sys, time, mimetypes
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# 実行ディレクトリ固定
APP_DIR = Path(__file__).resolve().parent
os.chdir(APP_DIR)

# 静的配信ルート
FILES_DIR = (APP_DIR / "files").resolve()

# プライバシー徹底（OpenAI遮断・Ollamaローカル固定）
os.environ["AI_PROVIDER"]    = "ollama"
os.environ["AI_MODEL"]       = os.environ.get("AI_MODEL", "qwen2.5:7b-instruct")
os.environ["OLLAMA_HOST"]    = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
os.environ["AI_LOG_DISABLE"] = "1"
os.environ.pop("OPENAI_API_KEY", None)

# 主要ファイル
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

TASKS = { "assessment": {}, "diagnosis": {}, "record": {}, "careplan": {} }
LOCK = threading.Lock()

# ---------- 速度対策 1: Ollama を事前ウォーム ----------
def _warm_ollama():
    try:
        import json as _json, urllib.request
        host  = os.environ.get("OLLAMA_HOST","http://127.0.0.1:11434").rstrip("/")
        model = os.environ.get("AI_MODEL","qwen2.5:7b-instruct")
        payload = _json.dumps({
            "model": model, "prompt": "ok",
            "stream": False, "keep_alive": "24h",
            "options": {"temperature": 0}
        }).encode("utf-8")
        req = urllib.request.Request(f"{host}/api/generate", data=payload,
                                     headers={"Content-Type":"application/json"})
        urllib.request.urlopen(req, timeout=15).read()
        print(f"[warm] model loaded: {model}")
    except Exception as e:
        print(f"[warm] skip ({e})")

# ---------- 速度対策 2: assessment.py 等を同一プロセス実行 ----------
def _run_inproc(script_path: Path, stdin_text: str|None = None):
    t0 = time.time()
    old_in, old_out = sys.stdin, sys.stdout
    buf_in  = io.StringIO(stdin_text or "")
    buf_out = io.StringIO()
    sys.stdin, sys.stdout = buf_in, buf_out
    rc = 0
    try:
        runpy.run_path(str(script_path), run_name="__main__")
    except SystemExit as e:
        rc = int(getattr(e, "code", 0) or 0)
    except Exception as e:
        rc = 1
        buf_out.write(f"\n[ERROR] {type(e).__name__}: {e}\n")
    finally:
        sys.stdin, sys.stdout = old_in, old_out
    out = buf_out.getvalue()
    dt  = time.time() - t0
    print(f"[inproc] {script_path.name} done rc={rc} {dt:.2f}s, out={len(out)}B")
    return rc, out

def _spawn(name, script_filename, stdin_text=None):
    with LOCK:
        TASKS[name] = {"running": True, "done": False, "rc": None,
                       "result": "", "stdout": "", "stderr": "", "proc": "inproc"}
    def run():
        try:
            rc, out = _run_inproc(APP_DIR / script_filename, stdin_text)
            with LOCK:
                TASKS[name].update({"running":False,"done":True,"rc":rc,
                                    "stdout":out or "","stderr":"", "result":(out or "").strip()})
        except Exception as e:
            with LOCK:
                TASKS[name].update({"running":False,"done":True,"rc":1,"stderr":str(e)})
    threading.Thread(target=run, daemon=True).start()

def _cancel(name):
    with LOCK:
        TASKS.setdefault(name,{}).update({"running":False,"done":False,"rc":None})

def _save_text(kind: str, text: str):
    mapping = {
        "assessment": (ASSESS_FINAL_TXT, ASSESS_RESULT_TXT),
        "diagnosis":  (DIAG_FINAL_TXT,   DIAG_RESULT_TXT),
        "record":     (RECORD_FINAL_TXT, RECORD_RESULT_TXT),
        "careplan":   (PLAN_FINAL_TXT,   PLAN_RESULT_TXT),
    }
    pair = mapping.get(kind)
    if not pair: return False, "unsupported kind"
    fn_final, fn_result = pair
    try:
        Path(fn_final).write_text(text or "", encoding="utf-8", errors="ignore")
        Path(fn_result).write_text(text or "", encoding="utf-8", errors="ignore")
        return True, "ok"
    except Exception as e:
        return False, str(e)

def _extract_json_block(s: str):
    m = re.search(r"\{.*\}", s, re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None

def _ai_map_so(text: str):
    try:
        import json as _json, urllib.request
        host  = os.environ.get("OLLAMA_HOST","http://127.0.0.1:11434").rstrip("/")
        model = os.environ.get("AI_MODEL","qwen2.5:7b-instruct")
        prompt = f"""
以下の看護記録テキストを S（主観）と O（客観）のテンプレに割り付けてください。
出力は**厳密なJSON**のみ。キーは以下に限定。
S側: shuso, keika, bui, seishitsu, inyo, zuikan, life, back, think, etc
O側: name, T, HR, RR, SpO2, SBP, DBP, NRS, awareness, resp, circ, excrete, lab, risk, active, high, weight, etc
値は文字列。無ければ空文字。日本語のままで。
テキスト:
{text}
"""
        payload = _json.dumps({
            "model": model, "prompt": prompt,
            "stream": False, "keep_alive": "24h",
            "options": {"temperature": 0}
        }).encode("utf-8")
        req = urllib.request.Request(f"{host}/api/generate", data=payload,
                                     headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=40) as r:
            js = _json.loads(r.read().decode("utf-8","ignore"))
        raw = js.get("response","").strip()
        data = _extract_json_block(raw)
        if not data: return {"S":{}, "O":{}}
        return {"S": data.get("S") or data.get("s") or {},
                "O": data.get("O") or data.get("o") or {}}
    except Exception:
        return {"S":{}, "O":{}}

# ----------- 静的配信（/files/* と index / nurse_ui） -----------
def _safe_join_files(subpath: str) -> Path|None:
    # 先頭の /files/ をはずして正規化、ディレクトリトラバーサル対策
    p = (FILES_DIR / Path(subpath).name) if "/" not in subpath else (FILES_DIR / subpath.split("/")[-1])
    try:
        rp = p.resolve()
        if str(rp).startswith(str(FILES_DIR)):
            return rp if rp.exists() else None
        return None
    except Exception:
        return None

def _mime_guess(fn: str) -> str:
    m, _ = mimetypes.guess_type(fn)
    if m: return m
    # .bat/.sh など手当
    if fn.endswith(".bat"): return "application/octet-stream"
    if fn.endswith(".sh"):  return "application/x-sh"
    if fn.endswith(".txt"): return "text/plain; charset=utf-8"
    if fn.endswith(".json"):return "application/json; charset=utf-8"
    return "application/octet-stream"

class Handler(BaseHTTPRequestHandler):
    def _send(self, data: bytes, ctype="application/octet-stream", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj, code=200): self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", code)

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/","/index.html"):
            return self._send(Path("index.html").read_bytes(), "text/html; charset=utf-8")
        if p in ("/nurse_ui.html","/app"):
            return self._send(Path("nurse_ui.html").read_bytes(), "text/html; charset=utf-8")
        if p == "/ai/health":
            return self._send_json({"ok": True, "message": "alive"})
        if p == "/nanda.xlsx":
            q = Path(NANDA_XLSX)
            if not q.exists(): return self._send_json({"ok":False,"error":"nanda_db.xlsx not found"},404)
            return self._send(q.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        if p.startswith("/files/"):
            sub = p.replace("/files/","",1)
            q = _safe_join_files(sub)
            if not q: return self._send_json({"ok":False,"error":"not found"},404)
            return self._send(q.read_bytes(), _mime_guess(q.name))

        if p.startswith("/status/"):
            key = p.split("/")[-1]
            st = TASKS.get(key, {"running": False, "done": False})
            return self._send_json(st)

        return self._send_json({"ok":False,"error":"not found"},404)

    def do_POST(self):
        p = urlparse(self.path).path
        ln = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(ln).decode("utf-8") if ln>0 else ""
        try: js = json.loads(body) if body else {}
        except Exception: js = {}

        if p.startswith("/save/"):
            ok, msg = _save_text(p.split("/")[-1], js.get("text",""))
            return self._send_json({"ok":ok,"message":msg}, 200 if ok else 500)

        if p == "/run/assessment":
            S = js.get("S",""); O = js.get("O","")
            payload = f"{S}\n<<<SEP>>>\n{O}"
            _spawn("assessment", "assessment.py", stdin_text=payload)
            return self._send_json({"ok": True})

        if p == "/run/diagnosis":
            _spawn("diagnosis", "diagnosis.py");  return self._send_json({"ok": True})
        if p == "/run/record":
            _spawn("record", "record.py");        return self._send_json({"ok": True})
        if p == "/run/careplan":
            _spawn("careplan", "careplan.py");    return self._send_json({"ok": True})

        if p.startswith("/cancel/"):
            _cancel(p.split("/")[-1]); return self._send_json({"ok": True})

        if p in ("/review/assessment","/review/record","/review/careplan"):
            text = (js.get("text") or "").strip()
            return self._send_json({"ok": True, "review": text})

        if p == "/ai/map_so":
            t = (js.get("text") or "").strip()
            mapped = _ai_map_so(t) if t else {"S":{}, "O":{}}
            return self._send_json({"ok": True, "mapped": mapped})

        return self._send_json({"ok":False,"error":"not found"},404)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("NURSE_PORT","8787")))
    args = ap.parse_args()
    _warm_ollama()
    httpd = HTTPServer((args.host, args.port), Handler)
    print(f"Serving on http://{args.host}:{args.port}")
    httpd.serve_forever()

if __name__ == "__main__":
    main()
