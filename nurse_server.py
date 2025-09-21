# -*- coding: utf-8 -*-
import os, json, threading, subprocess, signal, ssl, argparse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

APP_DIR = Path(__file__).resolve().parent
os.chdir(APP_DIR)

# 既存ファイル名
ASSESS_RESULT_TXT="assessment_result.txt"; ASSESS_FINAL_TXT="assessment_final.txt"
DIAG_RESULT_TXT="diagnosis_result.txt";    DIAG_FINAL_TXT="diagnosis_final.txt"
DIAG_JSON="diagnosis_candidates.json"
RECORD_RESULT_TXT="record_result.txt";     RECORD_FINAL_TXT="record_final.txt"
PLAN_RESULT_TXT="careplan_result.txt";     PLAN_FINAL_TXT="careplan_final.txt"
NANDA_XLSX="nanda_db.xlsx"

TASKS={ "assessment":{}, "diagnosis":{}, "record":{}, "careplan":{} }
LOCK=threading.Lock()

def _spawn(name, cmd, stdin_text=None, env_overrides=None):
    with LOCK:
        if TASKS.get(name,{}).get("proc"):
            try: TASKS[name]["proc"].kill()
            except Exception: pass
        TASKS[name]={"running":True,"done":False,"rc":None,"result":"","stdout":"","stderr":"","proc":None}
    env=os.environ.copy()
    env.update({
        "AI_PROVIDER":"ollama",
        "AI_MODEL":os.environ.get("AI_MODEL","qwen2.5:7b-instruct"),
        "OLLAMA_HOST":os.environ.get("OLLAMA_HOST","http://127.0.0.1:11434"),
        "OPENAI_API_KEY":"", "AI_LOG_DISABLE":"1",
        "PYTHONIOENCODING":"utf-8","PYTHONUTF8":"1"
    })
    if env_overrides: env.update(env_overrides)
    def run():
        try:
            p=subprocess.Popen(cmd, stdin=subprocess.PIPE if stdin_text is not None else None,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="ignore",
                               cwd=str(APP_DIR), env=env)
            with LOCK: TASKS[name]["proc"]=p
            out,err=p.communicate(input=stdin_text)
            with LOCK:
                TASKS[name].update({"running":False,"done":True,"rc":p.returncode,
                                    "stdout":out or "","stderr":err or "",
                                    "result":(out or "").strip()})
        except Exception as e:
            with LOCK: TASKS[name].update({"running":False,"done":True,"rc":1,"stderr":str(e)})
    threading.Thread(target=run, daemon=True).start()

def _cancel(name):
    with LOCK:
        p=TASKS.get(name,{}).get("proc")
        if p:
            try: p.send_signal(signal.SIGTERM)
            except Exception: pass
        TASKS.setdefault(name,{}).update({"running":False,"done":False,"rc":None})

def _save_text(kind, text):
    mapping={
        "assessment":(ASSESS_FINAL_TXT,ASSESS_RESULT_TXT),
        "diagnosis": (DIAG_FINAL_TXT, DIAG_RESULT_TXT),
        "record":    (RECORD_FINAL_TXT,RECORD_RESULT_TXT),
        "careplan":  (PLAN_FINAL_TXT,  PLAN_RESULT_TXT),
    }
    pair=mapping.get(kind)
    if not pair: return False,"unsupported kind"
    fn_final, fn_result = pair
    try:
        Path(fn_final).write_text(text or "", encoding="utf-8", errors="ignore")
        Path(fn_result).write_text(text or "", encoding="utf-8", errors="ignore")
        return True,"ok"
    except Exception as e:
        return False,str(e)

# ===== CORS 共通ヘッダ =====
ALLOW_ORIGIN = os.environ.get("ALLOW_ORIGIN","*")
def _cors(handler):
    handler.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
    handler.send_header("Access-Control-Allow-Credentials", "false")
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")

class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.end_headers()

    def _send_json(self, obj, code=200):
        buf=json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code); _cors(self)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(buf)))
        self.end_headers(); self.wfile.write(buf)

    def _send_bytes(self, data:bytes, ctype="application/octet-stream"):
        self.send_response(200); _cors(self)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        p=urlparse(self.path).path
        # 健康チェック（GitHub Pages から叩く場所）
        if p=="/ai/health":
            return self._send_json({"ok":True,"message":"alive"})

        if p in ("/","/index.html","/nurse_ui.html"):
            return self._send_bytes(Path("nurse_ui.html").read_bytes(), "text/html; charset=utf-8")

        if p=="/nanda.xlsx":
            if not Path(NANDA_XLSX).exists():
                return self._send_json({"ok":False,"error":"nanda_db.xlsx not found"},404)
            return self._send_bytes(Path(NANDA_XLSX).read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        if p.startswith("/files/"):
            fn=p.replace("/files/","",1); q=Path(fn)
            if not q.exists(): return self._send_json({"ok":False,"error":"not found"},404)
            ctype="text/plain; charset=utf-8"
            if fn.endswith(".json"): ctype="application/json; charset=utf-8"
            return self._send_bytes(q.read_bytes(), ctype)

        if p.startswith("/status/"):
            key=p.split("/")[-1]; st=TASKS.get(key,{"running":False,"done":False})
            return self._send_json(st)

        return self._send_json({"ok":False,"error":"not found"},404)

    def do_POST(self):
        p=urlparse(self.path).path
        ln=int(self.headers.get("Content-Length") or 0)
        body=self.rfile.read(ln).decode("utf-8") if ln>0 else ""
        try: js=json.loads(body) if body else {}
        except Exception: js={}

        if p.startswith("/save/"):
            ok,msg=_save_text(p.split("/")[-1], js.get("text",""))
            return self._send_json({"ok":ok,"message":msg}, 200 if ok else 500)

        if p=="/run/assessment":
            S=js.get("S",""); O=js.get("O","")
            _spawn("assessment",[os.sys.executable,"-X","utf8","assessment.py"],
                   stdin_text=f"{S}\n<<<SEP>>>\n{O}")
            return self._send_json({"ok":True})

        if p=="/run/diagnosis":
            _spawn("diagnosis",[os.sys.executable,"-X","utf8","diagnosis.py"]); return self._send_json({"ok":True})

        if p=="/run/record":
            _spawn("record",[os.sys.executable,"-X","utf8","record.py"]); return self._send_json({"ok":True})

        if p=="/run/careplan":
            _spawn("careplan",[os.sys.executable,"-X","utf8","careplan.py"]); return self._send_json({"ok":True})

        if p.startswith("/cancel/"):
            _cancel(p.split("/")[-1]); return self._send_json({"ok":True})

        if p=="/ai/map_so":
            # 実運用ではローカルAIへ委譲。ここは疎通用のダミー。
            return self._send_json({"ok":True,"mapped":{"S":{},"O":{}}})

        if p.startswith("/review/"):
            text=js.get("text","").strip()
            return self._send_json({"ok":True,"review":text})

        return self._send_json({"ok":False,"error":"not found"},404)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--https", action="store_true")
    ap.add_argument("--cert", default="cert.pem")
    ap.add_argument("--key",  default="key.pem")
    args=ap.parse_args()

    httpd=HTTPServer((args.host,args.port), Handler)
    proto="http"
    if args.https:
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=args.cert, keyfile=args.key)
        httpd.socket=ctx.wrap_socket(httpd.socket, server_side=True)
        proto="https"
    print(f"Serving on {proto}://{args.host}:{args.port}")
    httpd.serve_forever()

if __name__=="__main__":
    main()
