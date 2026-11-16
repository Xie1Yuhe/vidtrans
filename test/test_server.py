# -*- coding: utf-8 -*-
"""端到端测试 Web 服务：上传 → 启动（mock 翻译）→ 轮询 → 下载。"""
import json
import os
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799"
VIDEO = sys.argv[2] if len(sys.argv) > 2 else "test/excerpt.mp4"
FFMPEG_DIR = sys.argv[3] if len(sys.argv) > 3 else ""


def jget(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def jpost(path, obj):
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def upload(path):
    size = os.path.getsize(path)
    req = urllib.request.Request(BASE + "/api/upload", method="POST")
    req.add_header("X-Filename", os.path.basename(path))
    req.add_header("Content-Type", "application/octet-stream")
    req.add_header("Content-Length", str(size))
    with open(path, "rb") as f:
        with urllib.request.urlopen(req, data=f.read(), timeout=600) as r:
            return json.loads(r.read().decode("utf-8"))


def main():
    ok = True

    env = jget("/api/env")
    print("env:", {k: env[k] for k in ("version", "ffmpeg_ok", "faster_whisper", "gpu")})
    if not env.get("faster_whisper"):
        print("!! faster_whisper 不可用")
        ok = False

    cfg = jget("/api/config")
    print("config.json:", bool(cfg.get("provider") is not None))

    with urllib.request.urlopen(BASE + "/", timeout=20) as r:
        html = r.read().decode("utf-8", "replace")
    print("index.html:", len(html), "bytes,", "vidtrans" in html)
    if "vidtrans" not in html:
        ok = False

    up = upload(VIDEO)
    print("upload:", up.get("filename"), up.get("size"), "->", up.get("job"))
    jid = up["job"]

    opts = {
        "src_lang": "ja", "dst_lang": "zh", "asr_model": "large-v3",
        "concurrency": 2, "chunk_size": 40, "burn": False,
        "asr_prompt": "廻珠、廻想残滓、共闘キャラクター、虎杖悠仁、伏黒恵",
    }
    if FFMPEG_DIR:
        opts["ffmpeg_dir"] = FFMPEG_DIR
    st = jpost("/api/start", {"job": jid, "mock": True, "options": opts})
    print("start:", st)
    if not st.get("ok"):
        ok = False
        print("!! 启动失败")
        return 1 if not ok else 0

    t0 = time.time()
    status = None
    while time.time() - t0 < 900:
        jobs = jget("/api/jobs")
        me = [j for j in jobs if j["id"] == jid]
        status = me[0]["status"] if me else "?"
        if status in ("done", "error", "cancelled"):
            break
        time.sleep(3)
    print(f"status: {status}  ({time.time() - t0:.0f}s)")
    if status != "done":
        ok = False

    for name in ("srt", "ass", "bilingual"):
        url = BASE + f"/api/result?job={jid}&name={name}"
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                body = r.read()
            print(f"download {name}: {len(body)} bytes")
            if len(body) < 50:
                ok = False
        except Exception as e:
            print(f"download {name}: FAIL {e}")
            ok = False

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
