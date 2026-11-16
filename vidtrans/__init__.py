# -*- coding: utf-8 -*-
"""vidtrans —— 长视频字幕翻译流水线。

模块划分：
    config      配置读写（JSON，落在用户目录）
    utils       子进程 / 时间 / 文本工具
    cuda        Windows 下加载 pip 安装的 CUDA 运行库
    ffmpeg      抽音频、探测、烧录字幕
    asr         faster-whisper 语音识别
    segment     长句切分 + 分块
    translate   OpenAI 兼容接口的分块并行翻译
    subtitle    合成 SRT / ASS / 双语
    pipeline    串联全流程，发出进度事件
    server      纯标准库的本地 Web 服务
"""

__version__ = "1.0.0"
APP_NAME = "vidtrans"
