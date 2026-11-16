# -*- coding: utf-8 -*-
"""实测「一键安装 ffmpeg」：清掉配置里的 ffmpeg_dir，走一遍真实下载/解压。"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vidtrans import config as cfgmod  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799"


def jget(p):
    with urllib.request.urlopen(BASE + p, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def jpost(p, obj):
    req = urllib.request.Request(BASE + p, data=json.dumps(obj).encode(),
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    # 先把配置里的 ffmpeg_dir 清掉，让服务端认为「没装」
    cfg = cfgmod.load()
    old = cfg.get("ffmpeg_dir")
    cfg["ffmpeg_dir"] = ""
    cfgmod.save(cfg)
    print("已清空 ffmpeg_dir（原值 %r），等待服务重新读取…" % old)

    env = jget("/api/env")
    print("清空后 ffmpeg_ok =", env.get("ffmpeg_ok"))
    if env.get("ffmpeg_ok"):
        print("！！仍然能找到 ffmpeg（可能装在 PATH / bin 里），这个测试不成立")
        return 2

    r = jpost("/api/setup/ffmpeg", {})
    print("启动安装:", r)
    if r.get("already"):
        print("服务端认为已经装了，跳过")
        return 0

    t0 = time.time()
    last = ""
    while time.time() - t0 < 900:
        s = jget("/api/setup/ffmpeg/status")
        msg = "%s %.0f%% %s" % (s.get("stage", ""), (s.get("frac") or 0) * 100,
                                s.get("msg", ""))
        if msg != last:
            print("  " + msg, flush=True)
            last = msg
        if s.get("error"):
            print("安装失败:", s["error"])
            return 1
        if s.get("done"):
            break
        time.sleep(2)
    else:
        print("超时")
        return 1

    print("安装耗时 %.0f 秒" % (time.time() - t0))
    env2 = jget("/api/env")
    print("安装后 ffmpeg_ok =", env2.get("ffmpeg_ok"), "|", env2.get("ffmpeg"))
    ok = bool(env2.get("ffmpeg_ok"))
    print("ffmpeg 路径存在:", os.path.exists(env2.get("ffmpeg") or ""))
    print("ffprobe 路径存在:", os.path.exists(env2.get("ffprobe") or ""))
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
