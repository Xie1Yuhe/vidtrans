# -*- coding: utf-8 -*-
"""语音识别：faster-whisper 封装。

刻意不用 faster_whisper 自带的音频解码（它对 PyAV 版本敏感），
统一先用 ffmpeg 抽成 16k 单声道 wav，再用 wave 读成 numpy。
"""
import os
import sys
import wave
import time

import numpy as np

from . import cuda

SAMPLE_RATE = 16000


def _load_wav(path):
    with wave.open(path, "rb") as w:
        if w.getnchannels() != 1 or w.getframerate() != SAMPLE_RATE:
            raise RuntimeError(
                f"wav 格式不对：{w.getnchannels()}ch {w.getframerate()}Hz，"
                f"需要 mono {SAMPLE_RATE}Hz")
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def pick_device(cfg, log=print):
    """按配置挑设备，cuda 不可用时自动退回 cpu。"""
    device = (cfg.get("asr_device") or "cuda").lower()
    compute = cfg.get("asr_compute") or "float16"
    if device == "cuda":
        if not cuda.gpu_available():
            log("未检测到可用的 CUDA（或缺少 cuBLAS/cuDNN），自动改用 CPU")
            device, compute = "cpu", "int8"
        else:
            missing = cuda.ensure_cuda_libs()
            if missing:
                log("缺少 CUDA 运行库 %s，可执行：pip install nvidia-cublas-cu12 "
                    "nvidia-cudnn-cu12" % ", ".join(missing))
    if device == "cpu" and compute not in ("int8", "int8_float32", "float32"):
        compute = "int8"
    return device, compute


class Recognizer:
    def __init__(self, cfg, log=print, progress=None):
        self.model_size = cfg.get("asr_model", "large-v3")
        self.beam = int(cfg.get("asr_beam", 5) or 5)
        self.prompt = (cfg.get("asr_prompt") or "").strip()
        if cfg.get("hf_endpoint"):
            os.environ.setdefault("HF_ENDPOINT", cfg["hf_endpoint"])
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        self.log = log
        self.progress = progress
        self.device, self.compute = pick_device(cfg, log)
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        cuda.enable()
        from faster_whisper import WhisperModel
        t0 = time.time()
        self.log(f"加载识别模型 {self.model_size}（{self.device}/{self.compute}），"
                 f"首次会下载，请稍候…")
        self._model = WhisperModel(self.model_size, device=self.device,
                                   compute_type=self.compute)
        self.log(f"模型加载完成，用时 {time.time() - t0:.1f}s")
        return self._model

    def transcribe(self, wav_path, language=None, cancel=None):
        model = self._ensure_model()
        audio = _load_wav(wav_path)
        total = len(audio) / SAMPLE_RATE
        segs, _info = model.transcribe(
            audio,
            language=language or None,
            beam_size=self.beam,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400, "speech_pad_ms": 200},
            condition_on_previous_text=False,
            initial_prompt=self.prompt or None,
            word_timestamps=False,
        )

        rows = []
        last = 0.0
        for s in segs:
            if cancel is not None and cancel.is_set():
                raise RuntimeError("已取消")
            txt = (s.text or "").strip()
            if txt:
                rows.append({"start": round(s.start, 3), "end": round(s.end, 3),
                             "text": txt, "no_speech": round(getattr(s, "no_speech_prob", 0.0), 3)})
            now = time.time()
            if self.progress and s.end > last and now - last >= 3:
                last = now
                self.progress.fraction("asr", s.end / max(total, 1),
                                       f"识别中 {s.end/60:.1f}/{total/60:.1f} 分钟")
        return rows, total
