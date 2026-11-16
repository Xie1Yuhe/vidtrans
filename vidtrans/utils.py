# -*- coding: utf-8 -*-
"""通用工具：子进程、时间格式化、文本处理。"""
import os
import re
import sys
import json
import shutil
import subprocess
import threading

FFMPEG_NAMES = ("ffmpeg.exe", "ffmpeg")


class ToolError(RuntimeError):
    pass


def _app_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _candidate_dirs(cfg_dir=""):
    """ffmpeg 可能待的地方，按优先级。"""
    dirs = []
    if cfg_dir:
        dirs += [cfg_dir, os.path.join(cfg_dir, "bin")]
    env = os.environ.get("VIDTRANS_FFMPEG", "")
    if env:
        dirs += [env, os.path.join(env, "bin")]
    root = _app_root()
    dirs += [os.path.join(root, "bin"), os.path.join(root, "ffmpeg"),
             os.path.join(root, "tools")]
    # tools/*/bin（兼容把解压目录直接丢进来的情况）
    tools = os.path.join(root, "tools")
    if os.path.isdir(tools):
        for name in sorted(os.listdir(tools)):
            dirs.append(os.path.join(tools, name, "bin"))
            dirs.append(os.path.join(tools, name))
    for base in (r"C:\ffmpeg\bin", os.path.expanduser("~/ffmpeg/bin")):
        dirs.append(base)
    return [d for d in dirs if d and os.path.isdir(d)]


def find_bin(name, cfg_dir=""):
    """Locate ffmpeg/ffprobe: 配置目录 > 环境变量 > 程序目录 > PATH。"""
    for d in _candidate_dirs(cfg_dir):
        cand = os.path.join(d, name)
        if os.path.exists(cand):
            return cand
    found = shutil.which(name)
    return found or None


def ffmpeg_path(cfg):
    return find_bin("ffmpeg.exe", cfg.get("ffmpeg_dir", "")) or find_bin("ffmpeg", cfg.get("ffmpeg_dir", ""))


def ffprobe_path(cfg):
    return find_bin("ffprobe.exe", cfg.get("ffmpeg_dir", "")) or find_bin("ffprobe", cfg.get("ffmpeg_dir", ""))


def run(cmd, desc="", cwd=None, timeout=None):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       cwd=cwd, timeout=timeout)
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace")[-3000:]
        raise ToolError(f"{desc or 'command'} failed (exit {p.returncode}):\n{err}")
    return p


def probe(cfg, path):
    """Return dict(duration, has_video, has_audio, width, height, fps)."""
    fp = ffprobe_path(cfg)
    if not fp:
        raise ToolError("找不到 ffprobe，请设置 ffmpeg 目录")
    p = run([fp, "-v", "error", "-show_entries", "format=duration",
             "-show_entries", "stream=codec_type,width,height,r_frame_rate",
             "-of", "json", path], "ffprobe")
    data = json.loads(p.stdout.decode("utf-8", "replace") or "{}")
    info = {"duration": 0.0, "has_video": False, "has_audio": False,
            "width": 0, "height": 0, "fps": 0.0}
    try:
        info["duration"] = float(data.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        pass
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            info["has_video"] = True
            info["width"] = s.get("width") or 0
            info["height"] = s.get("height") or 0
            num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
            try:
                info["fps"] = round(float(num) / float(den or 1), 3)
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        elif s.get("codec_type") == "audio":
            info["has_audio"] = True
    return info


def srt_time(t):
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def ass_time(t):
    t = max(0.0, float(t))
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def human_dur(sec):
    sec = int(sec or 0)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


class Progress:
    """简单进度上报：stage 名 + 0~1 + 文本。"""

    def __init__(self, emit=None):
        self.emit = emit or (lambda ev: None)

    def stage(self, name, msg="", **extra):
        self.emit({"type": "stage", "stage": name, "msg": msg, **extra})

    def log(self, msg, level="info"):
        self.emit({"type": "log", "level": level, "msg": msg})

    def fraction(self, stage, frac, msg=""):
        self.emit({"type": "progress", "stage": stage,
                   "frac": max(0.0, min(1.0, float(frac))), "msg": msg})
