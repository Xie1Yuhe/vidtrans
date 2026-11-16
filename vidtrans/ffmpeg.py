# -*- coding: utf-8 -*-
"""ffmpeg 相关：抽音频、烧录字幕。"""
import os
import subprocess

from .utils import ffmpeg_path, run, ToolError


def extract_audio(cfg, src, dst_wav, sample_rate=16000):
    """抽成单声道 16k PCM wav（识别用）。"""
    ff = ffmpeg_path(cfg)
    if not ff:
        raise ToolError("找不到 ffmpeg，请在设置里指定 ffmpeg 目录")
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y",
           "-i", src, "-vn", "-ac", "1", "-ar", str(sample_rate),
           "-c:a", "pcm_s16le", dst_wav]
    run(cmd, "extract audio")
    if not os.path.exists(dst_wav) or os.path.getsize(dst_wav) == 0:
        raise ToolError("抽音频失败：没有音轨？")
    return dst_wav


def burn(cfg, src, ass_path, out_path, on_progress=None, cancel=None,
         codec=None, cq=None):
    """把 ASS 烧进视频。codec 支持 h264_nvenc / libx264。

    注意：ass 过滤器按「当前工作目录」找文件，所以我们会切到 ass 所在目录，
    因此 src / out_path / ass_path 必须先转成绝对路径，否则相对路径会失效。
    """
    ff = ffmpeg_path(cfg)
    if not ff:
        raise ToolError("找不到 ffmpeg")
    src = os.path.abspath(src)
    ass_path = os.path.abspath(ass_path)
    out_path = os.path.abspath(out_path)
    if not os.path.exists(src):
        raise ToolError("找不到视频文件：" + src)
    if not os.path.exists(ass_path):
        raise ToolError("找不到字幕文件：" + ass_path)
    codec = codec or cfg.get("burn_codec", "h264_nvenc")
    cq = cq or cfg.get("burn_cq", 26)

    workdir = os.path.dirname(ass_path)
    ass_name = os.path.basename(ass_path)

    vf = f"ass={ass_name}"
    if codec == "h264_nvenc":
        enc = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr",
               "-cq", str(cq), "-maxrate", "6M", "-bufsize", "12M"]
    else:
        enc = ["-c:v", "libx264", "-preset", "fast", "-crf", str(cq)]

    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y",
           "-i", src, "-vf", vf, *enc,
           "-pix_fmt", "yuv420p", "-c:a", "copy",
           "-movflags", "+faststart", out_path]

    p = subprocess.Popen(cmd, cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    while True:
        try:
            p.wait(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                p.kill()
                raise ToolError("已取消")
    err = p.stderr.read().decode("utf-8", "replace")
    if p.returncode != 0:
        if "nvenc" in (err or "") or p.returncode == 1:
            # 显卡不支持时回退到 libx264
            if codec == "h264_nvenc":
                return burn(cfg, src, ass_path, out_path, on_progress, cancel,
                            codec="libx264", cq=cq)
        raise ToolError("烧录失败：\n" + err[-2000:])
    return out_path
