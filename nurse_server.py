# -*- coding: utf-8 -*-
"""
nurse_server.py — ローカルWebサーバ（UI/API一体）
起動:  python nurse_server.py --port 8787
"""
import os, json, threading, subprocess, signal, argparse, re, datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# 実行ディレクトリ固定
APP_DIR = Path(__file__).resolve().parent
os.chdir(APP_DIR)

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

def _spawn(name, cmd, stdin_text=None, env_overrides=None):
    with LOCK:
        if TASKS.get(name,{}).get("proc"):
            try: TASKS[name]["proc"].kill()
            except Exception: pass
        TASKS[name] = {"running": True, "done": False, "rc": None, "result": "", "stdout": "", "stderr": "", "proc": None}

    env = os.environ.copy()
    env.update({
        "PYTHONIOENCODING":"utf-8","PYTHONUTF8":"1",
        "AI_PROVIDER":"ollama","AI_LOG_DISABLE":"1",
        "AI_MODEL":os.environ.get("AI_MODEL","qwen2.5:7b-instruct"),
        "OLLAMA_HOST":os.environ.get("OLLAMA_HOST","http://127.0.0.1:11434"),
        "OPENAI_API_KEY":""
    })
    if env_overrides: env.update(env_overrides)

    def run():
        try:
            p = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE if stdin_text is not None else None,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="ignore",
                cwd=str(APP_DIR), env=env
            )
            with LOCK: TASKS[name]["proc"] = p
            out,err = p.communicate(input=stdin_text)
            with LOCK:
                TASKS[name].update({"running":False,"done":True,"rc":p.returncode,
                                    "stdout":out or "","stderr":err or "","result":(out or "").strip()})
        except Exception as e:
            with LOCK:
                TASKS[name].update({"running":False,"done":True,"rc":1,"stderr":str(e)})
    threading.Thread(target=run, daemon=True).start()

def _cancel(name):
    with LOCK:
        p = TASKS.get(name,{}).get("proc")
        if p:
            try: p.send_signal(signal.SIGTERM)
            except Exception: pass
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

def _ollama_post(payload: dict, timeout=25):
    import json as _json, urllib.request
    host  = os.environ.get("OLLAMA_HOST","http://127.0.0.1:11434").rstrip("/")
    req = urllib.request.Request(f"{host}/api/generate",
                                 data=_json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return _json.loads(r.read().decode("utf-8","ignore"))

def _ai_greet() -> str:
    """看護師さんをねぎらう短い文（『AI』という語は使わない）"""
    try:
        model = os.environ.get("AI_MODEL","qwen2.5:7b-instruct")
        prompt = (
            "病棟スタッフへ一言ふわっと声をかけるつもりで、"
            "看護師さんをねぎらい、落ち着いて始められる短い日本語メッセージを1つ。"
            "60〜120文字。改行なし。絵文字なし。「AI」という語は使わない。"
            "端末内で記録が完結し安心である旨をやわらかく含める。"
        )
        js = _ollama_post({"model": model, "prompt": prompt, "stream": False})
        text = (js.get("response") or "").strip()
        text = re.sub(r"\s+", " ", text).strip(' "\'')
        return text[:180] if text else ""
    except Exception:
        return ""

def _ai_map_so(text: str):
    """Ollama に投げて S/O の各項目に割り振る。失敗しても空で返す。"""
    try:
        import json as _json, urllib.request
        host  = os.environ.get("OLLAMA_HOST","http://127.0.0.1:11434").rstrip("/")
        model = os.environ.get("AI_MODEL","qwen2.5:7b-instruct")
        prompt = f"""
以下の看護記録テキストを S（主観）と O（客観）のテンプレに割り付けてください。
出力は**厳密なJSON**のみ。キーは以下に限定。
S側: shuso, keika, bui, seishitsu, inyo, zuikan, life, back, think, etc
O側: name, T, HR, RR, SpO2, SBP, DBP, NRS, awareness, resp, circ, excrete, lab, risk, active, high, weight, etc
値は文字列。無ければ空文字。日本語のままで。数字はあれば抽出。

テキスト:
{text}
"""
        payload = _json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
        req = urllib.request.Request(f"{host}/api/generate", data=payload, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=40) as r:
            js = _json.loads(r.read().decode("utf-8",errors="ignore"))
        raw = js.get("response","").strip()
        data = _extract_json_block(raw)
        if not data: return {"S":{}, "O":{}}
        S = data.get("S") or data.get("s") or {}
        O = data.get("O") or data.get("o") or {}
        return {"S":S, "O":O}
    except Exception:
        return {"S":{}, "O":{}}

class Handler(BaseHTTPRequestHandler):
    # CORS（GitHub Pages → 127.0.0.1:8787 を許可）
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, obj, code=200):
        buf = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(buf)))
        self.end_headers()
        self.wfile.write(buf)

    def _send_bytes(self, data: bytes, ctype="application/octet-stream"):
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/","/index.html","/nurse_ui.html"):
            return self._send_bytes(Path("nurse_ui.html").read_bytes(), "text/html; charset=utf-8")
        if p == "/ai/health":
            return self._send_json({"ok": True, "message": "alive"})
        if p == "/ai/greet":
            msg = _ai_greet() or "いつもありがとうございます。記録はこの端末の中で完結します。安心して始めてください。"
            return self._send_json({"ok": True, "message": msg})
        if p == "/nanda.xlsx":
            if not Path(NANDA_XLSX).exists():
                return self._send_json({"ok":False,"error":"nanda_db.xlsx not found"},404)
            return self._send_bytes(Path(NANDA_XLSX).read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if p.startswith("/files/"):
            fn = p.replace("/files/","",1)
            q = Path(fn)
            if not q.exists(): return self._send_json({"ok":False,"error":"not found"},404)
            ctype = "text/plain; charset=utf-8"
            if fn.endswith(".json"): ctype="application/json; charset=utf-8"
            return self._send_bytes(q.read_bytes(), ctype)
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

        # ---- 追加: ログイン（PIN照合・ログのみ） ----
        if p == "/auth/login":
            staff = (js.get("staff") or "").strip()
            pin   = (js.get("pin") or "").strip()
            required = os.environ.get("LOGIN_PIN","").strip()
            ok = True if required=="" else (pin == required)
            # 監査ログ（端末内）
            try:
                rec = {
                    "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                    "staff": staff, "ok": ok
                }
                with open("login_log.jsonl","a",encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False)+"\n")
            except Exception:
                pass
            return self._send_json({"ok": ok, "message": "authorized" if ok else "invalid pin"})
        # --------------------------------------------

        if p.startswith("/save/"):
            ok, msg = _save_text(p.split("/")[-1], js.get("text",""))
            return self._send_json({"ok":ok,"message":msg}, 200 if ok else 500)

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

        if p.startswith("/cancel/"):
            _cancel(p.split("/")[-1]); return self._send_json({"ok": True})

        if p == "/review/assessment" or p == "/review/record" or p == "/review/careplan":
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
    httpd = HTTPServer((args.host, args.port), Handler)
    print(f"Serving on http://{args.host}:{args.port}")
    httpd.serve_forever()

if __name__ == "__main__":
    main()
