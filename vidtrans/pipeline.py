# -*- coding: utf-8 -*-
"""流水线：把一个视频跑成字幕（以及可选的成片）。"""
import json
import os
import time
import traceback

from . import asr as asr_mod
from . import ffmpeg as ff
from . import segment, subtitle
from .utils import Progress, probe, human_dur, ToolError
from .translate import Translator, MockTranslator, TranslateError


class Cancelled(RuntimeError):
    pass


class Pipeline:
    def __init__(self, cfg, job_dir, emit=None, cancel=None, mock_translate=False,
                 on_result=None):
        self.cfg = cfg
        self.job_dir = job_dir
        self.progress = Progress(emit)
        self.cancel = cancel
        self.mock = mock_translate
        self.on_result = on_result

    def _check(self):
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled()

    def run(self, src_path, basename="output"):
        cfg = self.cfg
        t0 = time.time()
        os.makedirs(self.job_dir, exist_ok=True)
        info = {}

        # 1) 探测
        self.progress.stage("probe", "读取视频信息")
        meta = probe(cfg, src_path)
        if not meta["has_audio"]:
            raise ToolError("这个文件没有音轨，无法识别语音")
        info["duration"] = meta["duration"]
        self.progress.log(
            f"时长 {human_dur(meta['duration'])}，"
            f"{meta['width']}x{meta['height']} @ {meta['fps']}fps")
        self._check()

        # 2) 抽音频
        self.progress.stage("audio", "提取音轨")
        wav = os.path.join(self.job_dir, "audio16k.wav")
        ff.extract_audio(cfg, src_path, wav)
        self._check()

        # 3) 识别
        self.progress.stage("asr", "语音识别")
        rec = asr_mod.Recognizer(cfg, log=self.progress.log, progress=self.progress)
        segments, total = rec.transcribe(wav, language=cfg.get("src_lang"),
                                         cancel=self.cancel)
        if not segments:
            raise ToolError("没有识别到任何语音（可能是纯音乐/无人声视频）")
        self.progress.fraction("asr", 1.0, f"识别到 {len(segments)} 段")
        with open(os.path.join(self.job_dir, "asr.jsonl"), "w", encoding="utf-8") as f:
            for s in segments:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        self._check()

        # 4) 切分
        self.progress.stage("split", "切分字幕条")
        lang = (cfg.get("src_lang") or "ja").lower()
        cues = segment.build_cues(segments, cfg, lang)
        self.progress.log(f"切成 {len(cues)} 条字幕")
        with open(os.path.join(self.job_dir, "cues.json"), "w", encoding="utf-8") as f:
            json.dump(cues, f, ensure_ascii=False)
        self._check()

        # 5) 翻译
        self.progress.stage("translate", "翻译")
        chunks = segment.make_chunks(cues, cfg.get("chunk_size") or 120)
        cls = MockTranslator if self.mock else Translator
        tr = cls(cfg, src_lang=lang, dst_lang=cfg.get("dst_lang") or "zh",
                 glossary=cfg.get("glossary") or "",
                 extra_rules=cfg.get("extra_rules") or "",
                 log=self.progress.log, progress=self.progress, cancel=self.cancel)
        translated = tr.translate_all(chunks)
        with open(os.path.join(self.job_dir, "translated.json"), "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in translated.items()}, f, ensure_ascii=False)
        self._check()

        # 6) 合成字幕文件
        self.progress.stage("subtitle", "生成字幕文件")
        rows = subtitle.normalize(cues, translated, cfg)
        paths = subtitle.write_all(rows, self.job_dir, basename, cfg)
        self.progress.log(f"生成 {len(rows)} 条字幕")

        # 7) 可选烧录
        if cfg.get("burn") and meta["has_video"]:
            self.progress.stage("burn", "烧录字幕到视频")
            out_mp4 = os.path.join(self.job_dir, f"{basename}.mp4")
            ff.burn(cfg, src_path, paths["ass"], out_mp4, cancel=self.cancel)
            paths["mp4"] = out_mp4
            self.progress.log("烧录完成")

        paths["src"] = src_path
        result = {
            "files": paths,
            "cues": len(rows),
            "duration": meta["duration"],
            "elapsed": round(time.time() - t0, 1),
            "usage": tr.usage,
        }
        with open(os.path.join(self.job_dir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        if self.on_result:
            self.on_result(result)
        self.progress.emit({"type": "done", "result": result,
                            "elapsed": result["elapsed"]})
        self.progress.log(f"全部完成，用时 {human_dur(result['elapsed'])}")
        return result
