# -*- coding: utf-8 -*-
"""本地 Web 服务（纯标准库）。

接口：
    GET  /                     页面
    GET  /static/*             静态资源
    GET  /api/env              环境自检（ffmpeg / GPU / CUDA 库）
    GET  /api/config           读配置
    POST /api/config           存配置
    POST /api/upload           上传视频（body 为原始字节，X-Filename 传文件名）
    POST /api/start            开始任务
    GET  /api/events?job=ID    SSE 进度流
    POST /api/cancel?job=ID    取消
    GET  /api/result?job=ID&name=srt|ass|bilingual|mp4   下载
    GET  /api/jobs             历史任务
"""
import json
import mimetypes
import os
import queue
import re
import shutil
import threading
import time
import urllib.parse
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, config as cfgmod, cuda
from .pipeline import Pipeline, Cancelled
from .utils import ffmpeg_path, ffprobe_path
from . import translate as tr_mod

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, "web")

JOBS = {}
JOBS_LOCK = threading.Lock()


def _new_job(filename):
    jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    jdir = os.path.join(cfgmod.work_root(cfgmod.load()), jid)
    os.makedirs(jdir, exist_ok=True)
    job = {
        "id": jid,
        "dir": jdir,
        "filename": filename,
        "path": None,
        "status": "created",
        "events": queue.Queue(),
        "cancel": threading.Event(),
        "result": None,
        "error": None,
        "created": time.time(),
        "history": [],
    }
    with JOBS_LOCK:
        JOBS[jid] = job
    return job


def _emit_for(job):
    def emit(ev):
        ev = dict(ev)
        ev["t"] = round(time.time() - job["created"], 2)
        if ev.get("type") == "stage":
            job["history"].append(ev)
        job["events"].put(ev)
    return emit


def _safe_name(name):
    name = os.path.basename(name or "video.mp4")
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    return name or "video.mp4"


class Handler(BaseHTTPRequestHandler):
    server_version = "vidtrans/" + __version__
    protocol_version = "HTTP/1.1"

    # ---------- helpers ----------
    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False),
                   "application/json; charset=utf-8")

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8", "replace"))

    def log_message(self, fmt, *args):
        pass

    # ---------- routing ----------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        path = u.path

        if path in ("/", "/index.html"):
            return self._serve_file(os.path.join(WEB_DIR, "index.html"))
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            return self._serve_file(os.path.join(WEB_DIR, rel))
        if path == "/api/env":
            return self._json(self._env())
        if path == "/api/config":
            return self._json(cfgmod.load())
        if path == "/api/jobs":
            with JOBS_LOCK:
                items = [{"id": j["id"], "filename": j["filename"],
                          "status": j["status"], "created": j["created"],
                          "result": j["result"]} for j in
                         sorted(JOBS.values(), key=lambda x: -x["created"])]
            return self._json(items)
        if path == "/api/events":
            jid = (q.get("job") or [""])[0]
            return self._events(jid)
        if path == "/api/result":
            jid = (q.get("job") or [""])[0]
            name = (q.get("name") or [""])[0]
            return self._download(jid, name)
        return self._send(404, "not found")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        path = u.path

        if path == "/api/config":
            data = self._read_json()
            cur = cfgmod.load()
            for k, v in data.items():
                if isinstance(v, dict) and isinstance(cur.get(k), dict):
                    cur[k].update(v)
                else:
                    cur[k] = v
            cfgmod.save(cur)
            return self._json({"ok": True, "path": cfgmod.CONFIG_PATH})
        if path == "/api/upload":
            return self._upload()
        if path == "/api/start":
            return self._start()
        if path == "/api/cancel":
            jid = (q.get("job") or [""])[0]
            job = JOBS.get(jid)
            if job:
                job["cancel"].set()
                return self._json({"ok": True})
            return self._json({"ok": False, "error": "job not found"}, 404)
        return self._send(404, "not found")

    # ---------- endpoints ----------
    def _env(self):
        cfg = cfgmod.load()
        missing = []
        ff = ffmpeg_path(cfg)
        fp = ffprobe_path(cfg)
        if not ff:
            missing.append("ffmpeg")
        if not fp:
            missing.append("ffprobe")
        try:
            import faster_whisper  # noqa: F401
            has_asr = True
        except Exception:
            has_asr = False
        return {
            "version": __version__,
            "ffmpeg": ff,
            "ffprobe": fp,
            "ffmpeg_ok": bool(ff and fp),
            "faster_whisper": has_asr,
            "gpu": cuda.gpu_available(),
            "cuda_libs_missing": cuda.ensure_cuda_libs(),
            "config_path": cfgmod.CONFIG_PATH,
            "work_root": cfgmod.work_root(cfg),
            "langs": tr_mod.LANG_LABEL,
        }

    def _serve_file(self, path):
        if not os.path.exists(path):
            return self._send(404, "not found")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        with open(path, "rb") as f:
            body = f.read()
        self._send(200, body, ctype)

    def _upload(self):
        fname = _safe_name(urllib.parse.unquote(self.headers.get("X-Filename", "video.mp4")))
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return self._json({"ok": False, "error": "空文件"}, 400)
        job = _new_job(fname)
        dst = os.path.join(job["dir"], fname)
        left = n
        with open(dst, "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(1024 * 1024, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        job["path"] = dst
        job["status"] = "uploaded"
        size = os.path.getsize(dst)
        return self._json({"ok": True, "job": job["id"], "filename": fname,
                           "size": size, "dir": job["dir"]})

    def _start(self):
        data = self._read_json()
        jid = data.get("job") or ""
        job = JOBS.get(jid)
        if not job:
            return self._json({"ok": False, "error": "job not found"}, 404)
        if job["status"] == "running":
            return self._json({"ok": False, "error": "任务已在运行"}, 400)

        cfg = cfgmod.load()
        over = data.get("options") or {}
        for k, v in over.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v

        mock = bool(data.get("mock"))
        job["status"] = "running"
        job["cancel"].clear()
        # 清掉上一轮事件的积压
        while not job["events"].empty():
            try:
                job["events"].get_nowait()
            except queue.Empty:
                break
        emit = _emit_for(job)

        def on_result(res):
            job["result"] = res
            job["status"] = "done"

        def work():
            try:
                pl = Pipeline(cfg, job["dir"], emit=emit, cancel=job["cancel"],
                              mock_translate=mock, on_result=on_result)
                base = os.path.splitext(job["filename"])[0]
                pl.run(job["path"], basename=base or "output")
            except Cancelled:
                job["status"] = "cancelled"
                emit({"type": "error", "msg": "已取消"})
            except Exception as e:
                job["status"] = "error"
                job["error"] = str(e)
                emit({"type": "error", "msg": str(e)})

        threading.Thread(target=work, daemon=True).start()
        return self._json({"ok": True, "job": jid})

    def _events(self, jid):
        job = JOBS.get(jid)
        if not job:
            return self._send(404, "job not found")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        q = job["events"]
        try:
            while True:
                try:
                    ev = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                self.wfile.write(("data: " + json.dumps(ev, ensure_ascii=False) +
                                  "\n\n").encode("utf-8"))
                self.wfile.flush()
                if ev.get("type") in ("done", "error"):
                    break
        except (BrokenPipeError, ConnectionResetError):
            pass
        self.close_connection = True

    def _download(self, jid, name):
        job = JOBS.get(jid)
        if not job or not job.get("result"):
            return self._send(404, "结果还没准备好")
        files = job["result"].get("files") or {}
        path = files.get(name)
        if not path or not os.path.exists(path):
            return self._send(404, "没有这个文件")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition",
                         'attachment; filename="%s"' % os.path.basename(path))
        self.end_headers()
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)
        self.close_connection = True


def serve(host="127.0.0.1", port=8765, open_browser=True):
    httpd = None
    last_err = None
    for p in range(port, port + 12):
        try:
            httpd = ThreadingHTTPServer((host, p), Handler)
            port = p
            break
        except OSError as e:
            last_err = e
            continue
    if httpd is None:
        print(f"\n  端口 {port}~{port+11} 都被占用，无法启动：{last_err}")
        return
    url = f"http://{host}:{port}/"
    print(f"\n  vidtrans v{__version__}")
    print(f"  已启动：{url}")
    print("  按 Ctrl+C 停止\n")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")
    finally:
        httpd.server_close()
