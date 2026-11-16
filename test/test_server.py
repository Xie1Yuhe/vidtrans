# -*- coding: utf-8 -*-
"""端到端测试 Web 服务：上传 → 启动（mock 翻译）→ 轮询 → 预览/下载/打包。

用法：
    python test/test_server.py [base] [video] [ffmpeg_dir] [mock_api_base]

默认 base=http://127.0.0.1:8799，video=test/excerpt.mp4
"""
import json
import os
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799"
VIDEO = sys.argv[2] if len(sys.argv) > 2 else "test/excerpt.mp4"
FFMPEG_DIR = sys.argv[3] if len(sys.argv) > 3 else ""
MOCK_API = sys.argv[4] if len(sys.argv) > 4 else ""

FAILED = []


def ok(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("  " + str(extra)) if extra else ""))
    if not cond:
        FAILED.append(name)


def jget(path, timeout=60):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def jpost(path, obj, timeout=120):
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 参数校验失败时服务端会返回 4xx，body 里仍是 JSON
        body = e.read().decode("utf-8", "replace")
        try:
            return json.loads(body)
        except Exception:
            return {"ok": False, "error": body[:200]}


def fetch(path, timeout=120):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.read()


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
    env = jget("/api/env")
    print("env:", {k: env.get(k) for k in ("version", "ffmpeg_ok", "faster_whisper", "gpu")})
    ok("env 有 bin_dir", bool(env.get("bin_dir")))
    ok("env 有 langs", len(env.get("langs") or {}) > 5)
    ok("识别引擎可用", env.get("faster_whisper") is True)

    html = fetch("/").decode("utf-8", "replace")
    ok("首页可访问", len(html) > 5000, len(html))
    ok("首页含新界面标记", "btnInstallFf" in html and "autoStart" in html)

    cfg = jget("/api/config")
    ok("配置可读", isinstance(cfg, dict) and "provider" in cfg)

    setup = jget("/api/setup/ffmpeg/status")
    ok("ffmpeg 安装状态接口", "running" in setup and "frac" in setup)

    if MOCK_API:
        r = jpost("/api/test-provider", {"provider": {
            "base_url": MOCK_API, "model": "mock-gpt", "api_key": "test-key"}})
        ok("测试连接（正常 Key）", r.get("ok") is True, r.get("error", ""))
        r2 = jpost("/api/test-provider", {"provider": {
            "base_url": MOCK_API, "model": "mock-gpt", "api_key": ""}})
        ok("测试连接（空 Key 应失败）", r2.get("ok") is False)

    up = upload(VIDEO)
    jid = up.get("job")
    ok("上传成功", up.get("ok") is True, up.get("filename"))

    # 缩略图后台生成，最多等 15 秒
    thumb_ok = False
    for _ in range(15):
        try:
            b = fetch("/api/thumb?job=" + jid, timeout=20)
            if len(b) > 1000:
                thumb_ok = True
                break
        except Exception:
            pass
        time.sleep(1)
    ok("缩略图生成", thumb_ok)

    opts = {"src_lang": "ja", "dst_lang": "zh", "asr_model": "tiny",
            "concurrency": 2, "chunk_size": 40, "burn": True,
            "asr_prompt": "廻珠、廻想残滓、共闘キャラクター、虎杖悠仁、伏黒恵"}
    if FFMPEG_DIR:
        opts["ffmpeg_dir"] = FFMPEG_DIR
    st = jpost("/api/start", {"job": jid, "mock": True, "options": opts})
    ok("启动任务", st.get("ok") is True, st.get("error", ""))
    if not st.get("ok"):
        return finish()

    t0 = time.time()
    status = None
    while time.time() - t0 < 900:
        jobs = jget("/api/jobs")
        me = [j for j in jobs if j["id"] == jid]
        status = me[0]["status"] if me else "?"
        if status in ("done", "error", "cancelled"):
            break
        time.sleep(3)
    ok("任务完成", status == "done", "status=" + str(status) + f" {time.time()-t0:.0f}s")
    if status != "done":
        return finish()

    pv = jget("/api/preview?job=" + jid + "&n=10")
    ok("预览接口有内容", pv.get("ok") and len(pv.get("lines") or []) > 0,
       len(pv.get("lines") or []))

    for name in ("srt", "ass", "bilingual"):
        try:
            body = fetch(f"/api/result?job={jid}&name={name}")
            ok("下载 " + name, len(body) > 50, len(body))
        except Exception as e:
            ok("下载 " + name, False, e)

    try:
        z = fetch(f"/api/result?job={jid}&name=zip")
        ok("打包下载 zip", len(z) > 200 and z[:2] == b"PK", len(z))
    except Exception as e:
        ok("打包下载 zip", False, e)

    # 烧录：输出名必须与输入不同（否则 ffmpeg 报 same as Input）
    try:
        mp4 = fetch(f"/api/result?job={jid}&name=mp4", timeout=300)
        ok("烧录输出 mp4", len(mp4) > 100000, len(mp4))
    except Exception as e:
        ok("烧录输出 mp4", False, e)

    return finish()


def finish():
    print("\nRESULT:", "PASS" if not FAILED else "FAIL(" + ", ".join(FAILED) + ")")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
