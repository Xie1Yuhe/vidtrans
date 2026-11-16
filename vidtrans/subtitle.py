# -*- coding: utf-8 -*-
"""合成字幕文件：SRT / 双语 SRT / ASS。"""
import os
import re

from .utils import srt_time, ass_time

ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: MAIN,{font},{size},&H00F5F5F5,&H00FFFFFF,&H7A000000,&H7A000000,{bold},0,0,0,100,100,1.2,0,3,7,0,2,{ml},{mr},{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

DEFAULT_FONT = "Microsoft YaHei"


def _strip_ws(x):
    x = (x or "").replace("\u3000", " ").strip()
    if re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", x):
        x = re.sub(r"\s+", "", x)
    else:
        x = re.sub(r"\s+", " ", x)
    return x


def apply_style_fixes(text, fixes):
    for f in fixes or []:
        pat = f.get("pattern") or ""
        rep = f.get("replace") or ""
        if not pat:
            continue
        try:
            text = re.sub(pat, rep, text)
        except re.error:
            text = text.replace(pat, rep)
    return text


def wrap(text, maxlen):
    """按标点软换行，最多两行。"""
    text = text.strip()
    if len(text) <= maxlen:
        return text
    mid = len(text) // 2
    best, bestd = None, 99
    for m in re.finditer(r"[，。！？、；…—」）]", text):
        p = m.end()
        if p >= len(text):
            continue
        d = abs(p - mid)
        if d < bestd:
            best, bestd = p, d
    if best and abs(best - mid) <= maxlen * 0.8:
        a, b = text[:best], text[best:]
    else:
        a, b = text[:mid], text[mid:]
    return a.rstrip("，、；") + "\n" + b.lstrip("，、；")


def normalize(cues, translated, cfg):
    """把译文并回 cue，做时长上限与去重叠。"""
    max_disp = float(cfg.get("max_display_duration") or 8.0)
    min_disp = 1.4
    fixes = cfg.get("style_fixes") or []
    rows = []
    for c in cues:
        txt = translated.get(c["id"], "")
        if not txt:
            continue
        txt = apply_style_fixes(_strip_ws(txt), fixes)
        rows.append({"start": float(c["start"]), "end": float(c["end"]),
                     "text": txt, "src": c.get("src", "")})
    for r in rows:
        if r["end"] - r["start"] > max_disp:
            r["end"] = r["start"] + max_disp
        if r["end"] - r["start"] < min_disp:
            r["end"] = r["start"] + min_disp
    for i in range(len(rows) - 1):
        if rows[i]["end"] > rows[i + 1]["start"] - 0.02:
            rows[i]["end"] = max(rows[i]["start"] + 0.45, rows[i + 1]["start"] - 0.02)
    last = -1.0
    for r in rows:
        if r["start"] < last + 0.02:
            r["start"] = last + 0.02
        if r["end"] <= r["start"]:
            r["end"] = r["start"] + 0.6
        if r["end"] < r["start"] + 0.45:
            r["end"] = r["start"] + 0.45
        last = r["end"]
    return rows


def write_srt(rows, path, bilingual=False, maxlen=24):
    with open(path, "w", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            f.write(f"{i}\n{srt_time(r['start'])} --> {srt_time(r['end'])}\n")
            if bilingual and r.get("src"):
                f.write(r["src"].strip() + "\n")
            f.write(wrap(r["text"], maxlen) + "\n\n")
    return path


def write_ass(rows, path, maxlen=24, font=DEFAULT_FONT, size=52,
              margin_v=64, bold=-1):
    head = ASS_HEAD.format(font=font, size=size, bold=bold,
                           ml=120, mr=120, mv=margin_v)
    with open(path, "w", encoding="utf-8") as f:
        f.write(head)
        for r in rows:
            txt = wrap(r["text"], maxlen)
            txt = txt.replace("{", "(").replace("}", ")").replace("\n", "\\N")
            f.write(f"Dialogue: 0,{ass_time(r['start'])},{ass_time(r['end'])},"
                    f"MAIN,,0,0,0,,{txt}\n")
    return path


def write_all(rows, outdir, basename, cfg, bilingual=True):
    maxlen = int(cfg.get("max_line_chars") or 24)
    os.makedirs(outdir, exist_ok=True)
    paths = {
        "srt": write_srt(rows, os.path.join(outdir, f"{basename}.srt"), False, maxlen),
        "ass": write_ass(rows, os.path.join(outdir, f"{basename}.ass"), maxlen),
    }
    if bilingual:
        paths["bilingual"] = write_srt(
            rows, os.path.join(outdir, f"{basename}.bilingual.srt"), True, maxlen)
    return paths
