# -*- coding: utf-8 -*-
"""切分与分块：把识别结果切成字幕条，再打包成翻译任务。"""
import math
import re

# 各语言可用的断句标点
PUNCT = "、。！？!?…；;，,．."
CJK_LANGS = ("ja", "zh", "ko")

# 日语常见助词（仅用于日文兜底断点，尽量不在片假名中间切）
JA_PARTICLES = ["から", "けど", "けれど", "ので", "のに", "って", "です", "ます",
                "ました", "ません", "でしょう", "ですね", "ですが",
                "は", "が", "を", "に", "で", "と", "も", "や", "へ", "ね", "よ", "し", "て"]
KATAKANA_RE = re.compile(r"[\u30a0-\u30ff\u30fc]")


def _is_kata(ch):
    return bool(KATAKANA_RE.match(ch))


def _ja_fallback_cut(text, mid):
    best, bestd = None, 10 ** 6
    for part in JA_PARTICLES:
        for m in re.finditer(re.escape(part), text):
            p = m.end()
            if p < 6 or p > len(text) - 5:
                continue
            if p < len(text) and _is_kata(text[p - 1]) and _is_kata(text[p]):
                continue
            d = abs(p - mid)
            if d < bestd:
                best, bestd = p, d
    if best:
        return best
    p = mid
    while 0 < p < len(text) and _is_kata(text[p - 1]) and _is_kata(text[p]):
        p += 1
    return p if p < len(text) - 2 else mid


def split_text(text, maxlen, lang="ja"):
    """把一段文本切成 <= maxlen 的若干段。"""
    text = (text or "").strip()
    if len(text) <= maxlen:
        return [text] if text else []
    out = []
    while len(text) > maxlen:
        cut = None
        for m in re.finditer("[" + re.escape(PUNCT) + "]", text):
            p = m.end()
            if 6 <= p <= maxlen:
                cut = p
        if cut is None:
            mid = len(text) // 2
            if lang in ("ja",):
                cut = _ja_fallback_cut(text, mid)
            elif lang in CJK_LANGS:
                cut = mid
            else:
                # 空格分词语言：在空格处断
                sp = [m.start() for m in re.finditer(r"\s", text[:maxlen])]
                cut = sp[-1] if sp else mid
        if not cut or cut <= 0 or cut >= len(text):
            cut = maxlen
        out.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        out.append(text)
    return [x for x in out if x]


def build_cues(segments, cfg, lang="ja"):
    """识别段 -> 字幕条（带 id / 起止时间）。"""
    maxlen = int(cfg.get("max_chars_per_cue") or 36)
    min_dur = float(cfg.get("min_cue_duration") or 1.1)
    cues = []
    for seg in segments:
        txt = (seg.get("text") or "").strip()
        if not txt:
            continue
        a, b = float(seg["start"]), float(seg["end"])
        dur = max(0.2, b - a)
        pieces = split_text(txt, maxlen, lang)
        if not pieces:
            continue
        total_chars = sum(len(p) for p in pieces) or 1
        t = a
        for i, p in enumerate(pieces):
            if i == len(pieces) - 1:
                end = b
            else:
                end = min(b, t + dur * len(p) / total_chars)
            cues.append({"start": round(t, 3), "end": round(end, 3), "src": p})
            t = end
    # 最短显示时长（不侵占下一条的开始时间）
    for i, c in enumerate(cues):
        if c["end"] - c["start"] < min_dur:
            limit = cues[i + 1]["start"] - 0.02 if i + 1 < len(cues) else c["start"] + min_dur
            c["end"] = round(min(c["start"] + min_dur, max(limit, c["start"] + 0.35)), 3)
    for i, c in enumerate(cues):
        c["id"] = i
    return cues


def make_chunks(cues, chunk_size=120):
    """打包成翻译分块，附带上一块的末尾作为上下文。"""
    chunks = []
    size = max(10, int(chunk_size or 120))
    for k in range(0, len(cues), size):
        part = cues[k:k + size]
        ctx = cues[max(0, k - 3):k]
        chunks.append({
            "index": len(chunks),
            "cues": [{"id": c["id"], "src": c["src"]} for c in part],
            "ctx": [{"src": c["src"]} for c in ctx],
        })
    return chunks
