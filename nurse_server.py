# -*- coding: utf-8 -*-
"""
nurse_server.py — ローカルWebサーバ（UI/API一体・高速版）
起動:  python nurse_server.py --port 8787
"""
import os, json, threading, signal, argparse, re, sys, runpy, gzip, io, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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

# --------- in-process 実行（高速・安定） -----------------------------------
def _run_inproc(pyfile: Path, stdin_text: str | None):
    """
    スレッドで in-process 実行。print を捕捉して返す。
    """
    import io, contextlib
    g = {"__name__":"__main__", "__file__": str(pyfile)}
    buf_out, buf_err = io.StringIO(), io.StringIO()
    rc = 0
    try:
        fake_in = io.StringIO(stdin_text or "")
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            old_stdin = sys.stdin
            sys.stdin = fake_in
            try:
                runpy.run_path(str(pyfile), init_globals=g)
            finally:
                sys.stdin = old_stdin
    except SystemExit as e:
        rc = int(getattr(e, "code", 1) or 0)
    except Exception as e:
        rc = 1
        buf_err.write(str(e))
    out = buf_out.getvalue()
    err = buf_err.getvalue()
    if err and not out:
        out = err
    return rc, out

def _spawn(name, script_filename, stdin_text=None):
    with LOCK:
        # 前回があれば停止印
        TASKS[name] = {"running": True, "done": False, "rc": None,
                       "result": "", "stdout": "", "stderr": "", "proc": None}

    def run():
        try:
            rc, out = _run_inproc(APP_DIR / script_filename, stdin_text)
            # stdout を既定の結果ファイルへ書き戻し（UIフォールバック用）
            try:
                back_map = {
                    "assessment": (ASSESS_RESULT_TXT, ASSESS_FINAL_TXT),
                    "diagnosis":  (DIAG_RESULT_TXT,  DIAG_FINAL_TXT),
                    "record":     (RECORD_RESULT_TXT,RECORD_FINAL_TXT),
                    "careplan":   (PLAN_RESULT_TXT,  PLAN_FINAL_TXT),
                }
                if name in back_map and out.strip():
                    Path(back_map[name][0]).write_text(out, encoding="utf-8", errors="ignore")
            except Exception as _e:
                print("[warn] write-back failed:", _e)

            with LOCK:
                TASKS[name].update({"running":False,"done":True,"rc":rc,
                                    "stdout":out or "","stderr":"",
                                    "result":(out or "").strip()})
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
    """Ollama → S/O 自動割付（失敗しても空で返す）"""
    try:
        import json as _json, urllib.request
        host  = os.environ.get("OLLAMA_HOST","http://127.0.0.1:11434").rstrip("/")
        model = os.environ.get("AI_MODEL","qwen2.5:7b-instruct")
        prompt = f"""
以下の看護記録テキストを S（主観）と O（客観）のテンプレに割り付けてください。
出力は**厳密なJSON**。キーは以下のみ。
S: shuso, keika, bui, seishitsu, inyo, zuikan, life, back, think, etc
O: name, T, HR, RR, SpO2, SBP, DBP, NRS, awareness, resp, circ, excrete, lab, risk, active, high, weight, etc
値は文字列。無ければ空文字。数字はあれば抽出。日本語のまま。

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

# --------- ユーティリティ（Gzip + Cache） ----------------------------------
def _maybe_gzip(data: bytes, ctype: str, accept_encoding: str | None):
    if not accept_encoding or "gzip" not in accept_encoding.lower():
        return data, False
    # HTML/JSON/テキストのみ圧縮
    if not (ctype.startswith("text/") or "json" in ctype or "javascript" in ctype):
        return data, False
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", compresslevel=6) as f:
        f.write(data)
    return out.getvalue(), True

# --------- HTTP -------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "NurseApp/2"

    def _send_bytes(self, data: bytes, ctype="application/octet-stream", cache_ok=False):
        accept = self.headers.get("Accept-Encoding")
        gz, used = _maybe_gzip(data, ctype, accept)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(gz)))
        self.send_header("Connection","keep-alive")
        if used: self.send_header("Content-Encoding","gzip")
        if cache_ok: self.send_header("Cache-Control","public, max-age=86400")
        self.end_headers()
        self.wfile.write(gz)

    def _send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection","keep-alive")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/","/index.html","/nurse_ui.html"):
            return self._send_bytes(Path("nurse_ui.html").read_bytes(), "text/html; charset=utf-8", cache_ok=False)
        if p == "/ai/health":
            return self._send_json({"ok": True, "message": "alive"})
        if p == "/nanda.xlsx":
            if not Path(NANDA_XLSX).exists():
                return self._send_json({"ok":False,"error":"nanda_db.xlsx not found"},404)
            return self._send_bytes(Path(NANDA_XLSX).read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", cache_ok=True)
        if p.startswith("/files/"):
            fn = p.replace("/files/","",1)
            q = Path(fn)
            if not q.exists(): return self._send_json({"ok":False,"error":"not found"},404)
            ctype = "text/plain; charset=utf-8"
            if fn.endswith(".json"): ctype="application/json; charset=utf-8"
            return self._send_bytes(q.read_bytes(), ctype, cache_ok=False)
        if p.startswith("/status/"):
            key = p.split("/")[-1]
            st = TASKS.get(key, {"running": False, "done": False})
            return self._send_json(st)
        if p == "/warmup":
            # 軽いウォームアップ（初回だけ高速化）
            start = time.time()
            try:
                _ = _ai_map_so("テスト: 体温は36.8℃、脈拍80、SpO2 98% です。")
                ok=True
            except Exception:
                ok=False
            return self._send_json({"ok": ok, "elapsed": round(time.time()-start,3)})
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
            _spawn("diagnosis", "diagnosis.py")
            return self._send_json({"ok": True})

        if p == "/run/record":
            _spawn("record", "record.py")
            return self._send_json({"ok": True})

        if p == "/run/careplan":
            _spawn("careplan", "careplan.py")
            return self._send_json({"ok": True})

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
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving on http://{args.host}:{args.port}")
    httpd.serve_forever()

if __name__ == "__main__":
    main()
