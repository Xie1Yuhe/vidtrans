# -*- coding: utf-8 -*-
"""本地 Web 服务（纯标准库）。

接口：
    GET  /                       页面
    GET  /static/*               静态资源
    GET  /api/env                环境自检
    GET  /api/config             读配置
    POST /api/config             存配置
    POST /api/upload             上传视频（body 原始字节，X-Filename 传文件名）
    POST /api/start              开始任务
    GET  /api/events?job=ID      SSE 进度流
    POST /api/cancel?job=ID      取消
    GET  /api/result?job=ID&name=srt|ass|bilingual|mp4|zip  下载
    GET  /api/thumb?job=ID       视频缩略图
    GET  /api/preview?job=ID     前若干条字幕，给页面预览
    GET  /api/jobs               历史任务
    POST /api/test-provider      测试 API 连通性（一次极小请求）
    POST /api/setup/ffmpeg       一键下载安装 ffmpeg
    GET  /api/setup/ffmpeg/status 安装进度
"""
import io
import json
import mimetypes
import os
import queue
import re
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, config as cfgmod, cuda
from .pipeline import Pipeline, Cancelled
from .utils import ffmpeg_path, ffprobe_path, app_bin_dir, find_bin, run as run_cmd
from . import translate as tr_mod

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, "web")

JOBS = {}
JOBS_LOCK = threading.Lock()

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

SETUP = {
    "running": False,
    "stage": "",
    "frac": 0.0,
    "msg": "",
    "done": False,
    "error": "",
}

# 把技术错误翻成人话
FRIENDLY = [
    (r"没有音轨|has_audio|no audio stream",
     "这个视频没有音轨，识别不了语音。请换一个带声音的文件。"),
    (r"找不到 ffmpeg|ffmpeg.*not found",
     "还没装 ffmpeg。点上面的「一键安装 ffmpeg」，或手动放到 bin 目录。"),
    (r"401|Unauthorized|invalid.*key",
     "API Key 无效或过期了。到「翻译接口」里重新填一个。"),
    (r"403|Forbidden",
     "API 拒绝了请求。多半是 Key 没权限，或地址写错（注意结尾要带 /v1）。"),
    (r"429|rate.?limit|too many request",
     "请求太频繁被限流。把并发数调到 2~3，等一两分钟再试。"),
    (r"404|Not Found",
     "接口地址不对（404）。检查 API 地址，例如 https://api.deepseek.com/v1"),
    (r"cublas|cudnn|CUDA",
     "显卡加速库缺失，已自动退回 CPU 模式（照样能跑，只是慢一些）。"),
    (r"Connection|timed out|timeout|10060|11001",
     "连不上 API 服务器。检查网络、代理，或换个 API 地址。"),
    (r"没有识别到任何语音",
     "整段都没识别到人声。可能是纯音乐/无人声视频。"),
    (r"磁盘|space|No space",
     "磁盘空间不够。清理一下临时目录再试。"),
]


def friendly(msg):
    s = str(msg or "")
    for pat, tip in FRIENDLY:
        if re.search(pat, s, re.I):
            return tip
    return ""


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
        "thumb": None,
        "created": time.time(),
        "history": [],
        "duration": 0,
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


def _make_thumb(cfg, job):
    """上传后后台抽一张缩略图，让页面能显示视频预览。"""
    try:
        ff = ffmpeg_path(cfg)
        if not ff:
            return
        from .utils import probe
        info = probe(cfg, job["path"])
        job["duration"] = info.get("duration") or 0
        ss = max(1.0, info["duration"] * 0.08) if info.get("duration") else 1.0
        out = os.path.join(job["dir"], "thumb.jpg")
        run_cmd([ff, "-hide_banner", "-loglevel", "error", "-y",
                 "-ss", f"{ss:.2f}", "-i", job["path"],
                 "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", out],
                "thumbnail")
        if os.path.exists(out) and os.path.getsize(out) > 0:
            job["thumb"] = out
    except Exception:
        pass


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

    def _err(self, msg, code=400):
        return self._json({"ok": False, "error": str(msg),
                           "hint": friendly(msg)}, code)

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
            return self._events((q.get("job") or [""])[0])
        if path == "/api/result":
            return self._download((q.get("job") or [""])[0], (q.get("name") or [""])[0])
        if path == "/api/thumb":
            return self._thumb((q.get("job") or [""])[0])
        if path == "/api/preview":
            return self._preview((q.get("job") or [""])[0],
                                 int((q.get("n") or ["30"])[0]))
        if path == "/api/setup/ffmpeg/status":
            return self._json(SETUP)
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
            job = JOBS.get((q.get("job") or [""])[0])
            if job:
                job["cancel"].set()
                return self._json({"ok": True})
            return self._err("job not found", 404)
        if path == "/api/test-provider":
            return self._test_provider()
        if path == "/api/setup/ffmpeg":
            return self._setup_ffmpeg()
        return self._send(404, "not found")

    # ---------- env ----------
    def _env(self):
        cfg = cfgmod.load()
        ff = ffmpeg_path(cfg)
        fp = ffprobe_path(cfg)
        try:
            import faster_whisper  # noqa: F401
            has_asr = True
        except Exception:
            has_asr = False
        prov = cfg.get("provider") or {}
        return {
            "version": __version__,
            "ffmpeg": ff,
            "ffprobe": fp,
            "ffmpeg_ok": bool(ff and fp),
            "bin_dir": app_bin_dir(),
            "faster_whisper": has_asr,
            "gpu": cuda.gpu_available(),
            "cuda_libs_missing": cuda.ensure_cuda_libs(),
            "config_path": cfgmod.CONFIG_PATH,
            "work_root": cfgmod.work_root(cfg),
            "langs": tr_mod.LANG_LABEL,
            "provider_ready": bool(prov.get("api_key") and prov.get("base_url")),
            "model": prov.get("model") or "",
            "asr_model": cfg.get("asr_model"),
            "setup_ffmpeg": dict(SETUP),
        }

    # ---------- static ----------
    def _serve_file(self, path):
        if not os.path.exists(path):
            return self._send(404, "not found")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        with open(path, "rb") as f:
            body = f.read()
        self._send(200, body, ctype)

    # ---------- upload ----------
    def _upload(self):
        fname = _safe_name(urllib.parse.unquote(self.headers.get("X-Filename", "video.mp4")))
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return self._err("空文件")
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
        threading.Thread(target=_make_thumb,
                         args=(cfgmod.load(), job), daemon=True).start()
        return self._json({"ok": True, "job": job["id"], "filename": fname,
                           "size": size, "dir": job["dir"]})

    def _thumb(self, jid):
        job = JOBS.get(jid)
        if not job or not job.get("thumb") or not os.path.exists(job["thumb"]):
            return self._send(404, "no thumb")
        with open(job["thumb"], "rb") as f:
            body = f.read()
        self._send(200, body, "image/jpeg",
                   {"Cache-Control": "max-age=600"})

    # ---------- start ----------
    def _start(self):
        data = self._read_json()
        job = JOBS.get(data.get("job") or "")
        if not job:
            return self._err("job not found", 404)
        if job["status"] == "running":
            return self._err("任务已经在跑了")

        cfg = cfgmod.load()
        for k, v in (data.get("options") or {}).items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
        if not ffmpeg_path(cfg):
            return self._err("找不到 ffmpeg")

        job["status"] = "running"
        job["cancel"].clear()
        while not job["events"].empty():
            try:
                job["events"].get_nowait()
            except queue.Empty:
                break
        emit = _emit_for(job)
        mock = bool(data.get("mock"))

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
                emit({"type": "error", "msg": "已取消", "hint": ""})
            except Exception as e:
                job["status"] = "error"
                job["error"] = str(e)
                emit({"type": "error", "msg": str(e), "hint": friendly(e)})

        threading.Thread(target=work, daemon=True).start()
        return self._json({"ok": True, "job": job["id"]})

    # ---------- SSE ----------
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

    # ---------- preview ----------
    def _preview(self, jid, n=30):
        job = JOBS.get(jid)
        if not job:
            return self._err("job not found", 404)
        path = os.path.join(job["dir"], "cues.json")
        trans = os.path.join(job["dir"], "translated.json")
        if not (os.path.exists(path) and os.path.exists(trans)):
            return self._json({"ok": True, "lines": []})
        with open(path, encoding="utf-8") as f:
            cues = json.load(f)
        with open(trans, encoding="utf-8") as f:
            tr = json.load(f)
        lines = []
        for c in cues[:n]:
            txt = (tr.get(str(c["id"])) or "").strip()
            if txt:
                lines.append({"start": c["start"], "text": txt, "src": c.get("src", "")})
        return self._json({"ok": True, "lines": lines, "total": len(cues)})

    # ---------- download ----------
    def _download(self, jid, name):
        job = JOBS.get(jid)
        if not job or not job.get("result"):
            return self._send(404, "结果还没准备好")
        files = job["result"].get("files") or {}
        if name == "zip":
            path = self._make_zip(job, files)
            if not path:
                return self._send(404, "没有可打包的字幕")
        else:
            path = files.get(name)
        if not path or not os.path.exists(path):
            return self._send(404, "没有这个文件")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        size = os.path.getsize(path)
        # 中文/日文文件名不能直接进 HTTP 头（只支持 latin-1），
        # 用 RFC 5987 的 filename*=UTF-8'' 形式，并带一个 ASCII 兜底名。
        fname = os.path.basename(path)
        ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", fname) or "download"
        disp = ("attachment; filename=\"%s\"; filename*=UTF-8''%s"
                % (ascii_name, urllib.parse.quote(fname, safe="")))
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", disp)
        self.end_headers()
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)
        self.close_connection = True

    def _make_zip(self, job, files):
        base = os.path.splitext(job["filename"])[0] or "subs"
        zpath = os.path.join(job["dir"], f"{base}.字幕.zip")
        targets = [(k, v) for k, v in files.items()
                   if k in ("srt", "ass", "bilingual") and v and os.path.exists(v)]
        if not targets:
            return None
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for k, v in targets:
                z.write(v, os.path.basename(v))
        return zpath

    # ---------- 测试 API ----------
    def _test_provider(self):
        data = self._read_json()
        prov = dict((cfgmod.load().get("provider") or {}))
        prov.update(data.get("provider") or {})
        if not prov.get("api_key"):
            return self._err("还没填 API Key")
        if not prov.get("base_url"):
            return self._err("还没填 API 地址")
        payload = json.dumps({
            "model": prov.get("model"),
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 8,
            "temperature": 0,
        }).encode("utf-8")
        req = urllib.request.Request(
            prov["base_url"].rstrip("/") + "/chat/completions",
            data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + prov["api_key"])
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode("utf-8", "replace"))
            model = (body.get("model") or prov.get("model") or "")
            reply = ""
            try:
                reply = ((body["choices"][0]["message"] or {}).get("content") or "")[:40]
            except Exception:
                pass
            return self._json({"ok": True, "ms": int((time.time() - t0) * 1000),
                               "model": model, "reply": reply})
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            return self._err(f"HTTP {e.code} {detail}", 200)
        except Exception as e:
            return self._err(str(e), 200)

    # ---------- 一键装 ffmpeg ----------
    def _setup_ffmpeg(self):
        if SETUP["running"]:
            return self._json({"ok": True, "already": True})
        cfg = cfgmod.load()
        if ffmpeg_path(cfg) and ffprobe_path(cfg):
            SETUP.update(running=False, done=True, frac=1.0,
                         msg="ffmpeg 已经可用", error="")
            return self._json({"ok": True, "already": True})
        SETUP.update(running=True, done=False, frac=0.0, error="",
                     stage="download", msg="正在下载 ffmpeg（约 120MB）…")
        threading.Thread(target=_install_ffmpeg, daemon=True).start()
        return self._json({"ok": True, "started": True})


def _install_ffmpeg():
    """下载官方 essentials 构建，解出 ffmpeg.exe / ffprobe.exe 到项目 bin 目录。"""
    tmpdir = None
    try:
        bin_dir = app_bin_dir()
        os.makedirs(bin_dir, exist_ok=True)
        tmpdir = tempfile.mkdtemp(prefix="vidtrans_ff_")
        zpath = os.path.join(tmpdir, "ffmpeg.zip")

        req = urllib.request.Request(FFMPEG_URL, headers={"User-Agent": "vidtrans"})
        with urllib.request.urlopen(req, timeout=60) as r, open(zpath, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if total:
                    SETUP["frac"] = round(got / total * 0.85, 3)
                    SETUP["msg"] = f"正在下载 ffmpeg… {got/1048576:.1f}/{total/1048576:.0f} MB"

        SETUP.update(stage="extract", frac=0.88, msg="正在解压…")
        with zipfile.ZipFile(zpath) as z:
            names = z.namelist()
            wanted = {}
            for n in names:
                low = n.lower()
                if low.endswith("/bin/ffmpeg.exe") or low.endswith("/bin/ffprobe.exe"):
                    wanted[n] = os.path.basename(n)
                elif low.endswith("/bin/ffmpeg") or low.endswith("/bin/ffprobe"):
                    wanted[n] = os.path.basename(n)
            if not wanted:
                raise RuntimeError("压缩包里没找到 ffmpeg 可执行文件")
            for n, base in wanted.items():
                with z.open(n) as src, open(os.path.join(bin_dir, base), "wb") as dst:
                    shutil.copyfileobj(src, dst)
                try:
                    os.chmod(os.path.join(bin_dir, base), 0o755)
                except OSError:
                    pass

        # Windows 上还可能需要 DLL 目录（gyan 构建是静态的，一般不需要）
        cfg = cfgmod.load()
        cfg["ffmpeg_dir"] = bin_dir
        cfgmod.save(cfg)

        SETUP.update(running=False, done=True, frac=1.0, error="",
                     stage="done", msg="ffmpeg 安装完成")
    except Exception as e:
        SETUP.update(running=False, done=False, error=str(e),
                     msg="安装失败：" + str(e))
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def serve(host="127.0.0.1", port=8765, open_browser=True):
    httpd = None
    last_err = None
    start_port = port
    for p in range(port, port + 12):
        try:
            httpd = ThreadingHTTPServer((host, p), Handler)
            port = p
            break
        except OSError as e:
            last_err = e
            continue
    if httpd is None:
        print(f"\n  端口 {start_port}~{start_port + 11} 都被占用，无法启动：{last_err}")
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
