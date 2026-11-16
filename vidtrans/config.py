# -*- coding: utf-8 -*-
"""配置：默认值 + 用户目录持久化。"""
import os
import json
import copy

APP_DIR = os.path.join(os.path.expanduser("~"), ".vidtrans")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULTS = {
    # ---- 路径 ----
    "ffmpeg_dir": "",          # 留空则用 PATH 里的 ffmpeg
    "work_dir": "",            # 留空则用 ~/.vidtrans/jobs

    # ---- 语音识别 ----
    "asr_model": "large-v3",   # tiny/base/small/medium/large-v2/large-v3
    "asr_device": "cuda",      # cuda / cpu
    "asr_compute": "float16",  # float16 / int8_float16 / int8
    "asr_beam": 5,
    "asr_prompt": "",          # 领域提示词（专有名词、术语），提升识别准确率
    "hf_endpoint": "https://hf-mirror.com",

    # ---- 翻译 ----
    "provider": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key": "",
        "temperature": 0.3,
        "max_tokens": 8192,
        "timeout": 180,
    },
    "concurrency": 6,          # 并行翻译的分块数
    "chunk_size": 120,         # 每个分块多少条字幕
    "max_retry": 4,

    # ---- 字幕 ----
    "src_lang": "ja",
    "dst_lang": "zh",
    "max_chars_per_cue": 36,   # 切分时单条字数上限（源语言字符）
    "min_cue_duration": 1.1,
    "max_display_duration": 8.0,
    "max_line_chars": 24,      # 合成时每行中文字数
    "style_fixes": [],         # [{"pattern": "...", "replace": "..."}]
    "glossary": "",            # 术语表文本（markdown/纯文本），注入翻译提示词
    "extra_rules": "",         # 额外翻译要求

    # ---- 烧录 ----
    "burn": False,
    "burn_codec": "h264_nvenc",  # h264_nvenc / libx264
    "burn_cq": 26,
}

LANG_NAMES = {
    "ja": "日语", "en": "英语", "ko": "韩语", "zh": "中文",
    "ru": "俄语", "fr": "法语", "de": "德语", "es": "西班牙语",
    "pt": "葡萄牙语", "it": "意大利语", "th": "泰语", "vi": "越南语",
}


def _deep_merge(base, upd):
    out = copy.deepcopy(base)
    for k, v in (upd or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    cfg = copy.deepcopy(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = _deep_merge(cfg, json.load(f))
        except Exception:
            pass
    return cfg


def save(cfg):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return CONFIG_PATH


def work_root(cfg):
    d = cfg.get("work_dir") or os.path.join(APP_DIR, "jobs")
    os.makedirs(d, exist_ok=True)
    return d
