# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] — 2026-11-16

首个可发布版本。所有能力来自一次真实任务：给一场 **2 小时 24 分**的日服游戏前瞻直播
做中文字幕（2,661 条，术语零违规、时间轴零重叠、零未翻译残留）。

### 新增

**流水线**
- `ffmpeg` 抽 16k 单声道音轨 → `faster-whisper` 本地识别 → 智能切分 → 分块并行翻译 → 生成字幕 → 可选烧录
- 识别支持 GPU（CUDA/FP16），无显卡自动退回 CPU(int8)
- 领域提示词：把专有名词喂给识别模型，提升人名/术语听写准确率
- 切分按标点优先、日文助词兜底，并避开片假名内部，避免把词切成两半

**翻译**
- 兼容任意 OpenAI 风格接口（DeepSeek / OpenAI / 硅基流动 / Kimi / 本地 Ollama）
- 术语表注入提示词，保证译名前后一致
- 一行一条、id 强对齐，模型不会打乱时间轴
- 缺条自动补问：只对缺失 id 再发一次小请求
- 失败重试（指数退避）、错误归类（401/429/网络/无音轨…）并翻译成人话

**输出**
- 纯中文字幕 `.srt`、中日双语 `.srt`、带样式 `.ass`、打包 `.zip`
- 可选把字幕烤进画面，输出 `原文件名.subtitled.mp4`

**界面**
- 纯标准库本地 Web 服务（无第三方 Web 框架）
- 向导式三步：选视频 → 设置 → 开始
- 环境自检：ffmpeg / 识别引擎 / GPU / 翻译接口，缺什么就在最上面提示并给修复入口
- 一键安装 ffmpeg（下载 + 解压到项目 `bin/`，自动改配置）
- 服务商预设 + 真实连通性测试
- 上传后显示缩略图；跑完先预览前 40 条字幕再下载
- 上传后自动开始、字幕烧录开关、SSE 实时进度、toast 提示

**命令行**
- `vidtrans serve` / `vidtrans run`，支持 `--mock` 离线验证管线

### 修复（开发过程中踩到并解决的）

- `run.bat` 曾被存成 UTF-8 + LF，Windows cmd 按 GBK 解析会把命令行从中间截断，
  报一堆「'xxx' 不是内部或外部命令」。改为 **纯 ASCII + CRLF**，并在 `.gitattributes` 锁定
- 烧录时切了工作目录却没把源路径转绝对，导致相对路径失效（`No such file or directory`）
- 烧录输出名与输入同名（上传文件本身是 `.mp4`），ffmpeg 直接报 `same as Input` 退出
- 中文文件名下载崩溃：`Content-Disposition` 只支持 latin-1，改用 RFC 5987 的
  `filename*=UTF-8''` 编码
- faster-whisper 自带的音频解码对 PyAV 版本敏感（`metadata_errors` 报错），
  改为统一先用 ffmpeg 出 wav
- Windows 上 ctranslate2 缺少 `cublas64_12.dll`，新增 `win_cuda` 自动挂载 pip 装的 CUDA 库
- HuggingFace 直连超时，默认走 `hf-mirror.com` 镜像
- 页面用 `file://` 打开时拖拽被浏览器抢走、语言下拉空白：改为先绑交互再联网，
  内置语言兜底表，并检测 `file://` 给出明确提示

### 已知限制

- 只翻「说的话」，画面上的文字（幻灯片、PV 字幕）没有 OCR
- 未做说话人分离
- 纯音乐 / 无人声段落会被 VAD 跳过，不会有字幕
- 识别是 ASR，口语、抢话、专有名词仍可能出错，重要内容建议抽检

[1.0.0]: https://github.com/Xie1Yuhe/vidtrans/releases/tag/v1.0.0
