# vidtrans

**把长视频变成中文字幕。** 本地跑、不花识别费，2 小时 1080p 的直播也能一次跑完。

> 做这个的起因：给一场 2 小时 24 分的日服游戏前瞻直播做中文字幕，
> 全程 2,661 条字幕、术语一条没串、时间轴零重叠。踩过的坑都固化在这条流水线里了。

```
视频 → 抽音频 → 本地语音识别 → 智能切分 → 分块并行翻译 → 生成字幕 →（可选）烧录成片
```

[English](README.en.md) · [参与贡献](CONTRIBUTING.md) · MIT License

---

## 特性

- **长视频友好**：2 小时量级一次跑完（GPU 下识别约 3.5× 实时）
- **本地识别**：faster-whisper + CUDA，不按分钟付费；无显卡自动退 CPU
- **术语表**：`廻珠 → 回珠` 这种对照表注入翻译提示词，译名不会前后不一致
- **id 强对齐**：一行一条、按 id 回填，模型自由发挥也不会打乱时间轴
- **缺条自动补问**：某块少了几条，只对缺失部分再问一次
- **断点式输出**：SRT / 双语 SRT / ASS（带样式）/ 可烧录的 MP4
- **零第三方 Web 依赖**：只用标准库起服务，装起来只要 `faster-whisper`
- **网页界面**：拖入视频 → 选语言 → 看进度 → 下载字幕

---

## 快速开始

### 1. 准备

| 你需要 | 说明 |
| --- | --- |
| Python 3.10+ | 安装时勾选 **Add Python to PATH** |
| ffmpeg / ffprobe | 见下方「装 ffmpeg」 |
| 一个 LLM API Key | 任何 OpenAI 兼容接口都行（DeepSeek、OpenAI、通义、Ollama…） |

**装 ffmpeg**：从 <https://www.gyan.dev/ffmpeg/builds/> 下 `ffmpeg-release-essentials.zip`，
解压后把 `bin\` 里的 `ffmpeg.exe`、`ffprobe.exe` 放到本项目的 `bin\` 目录（没有就建一个）。
也可以装到系统 PATH，或设环境变量 `VIDTRANS_FFMPEG=<含 ffmpeg.exe 的目录>`。

### 2. 启动

**Windows**：双击 `run.bat`（首次会自动装依赖）。
**macOS / Linux**：`./run.sh` 或 `python app.py serve`。

控制台会打印地址，一般是 <http://127.0.0.1:8765/>，浏览器会自动打开。

> ⚠️ **不要直接双击 `vidtrans/web/index.html`**。那样是 `file://` 协议，页面连不上后端，
> 拖视频会变成浏览器自己播放。必须通过上面的方式启动，然后访问控制台给的地址。

### 3. 用起来

1. 拖视频进页面（或点击选择）
2. 填 API 地址 / 模型名 / Key
3. 点「开始翻译」
4. 完成后下载 `.srt` / `.ass` / 带字幕的 `.mp4`

---

## 命令行

不装也能直接用：

```bash
python app.py run 视频.mp4 --src ja --dst zh --model large-v3
python app.py run 视频.mp4 --glossary 术语表.txt --burn
python app.py run 视频.mp4 --mock          # 不调 API，只验证管线通不通
python app.py serve --port 9000 --no-browser
```

装了（`pip install -e .` 或 `pip install .`）之后：

```bash
vidtrans run 视频.mp4 --src en --dst zh
```

主要参数：`--src --dst --model --asr-prompt --glossary --chunk-size --concurrency
--burn --outdir --ffmpeg-dir --base-url --api-key --model-name`

---

## 术语表怎么用

这是决定译名一致性的东西，强烈建议填。每行一条，`→` 或 `=` 分隔：

```
廻珠 → 回珠
廻想残滓 → 回想残滓
ゾーン → ZONE（不是「领域」）
潜在解放 → 潜在解放
```

会被当成「优先级最高的强制译法」写进翻译提示词。

**识别提示词**是另一件事：那是喂给语音识别模型的词表，用来纠正专有名词的听写错误。例如：

```
廻珠、廻想残滓、共闘キャラクター、共闘スキル、黒閃、領域展開、虎杖悠仁、伏黒恵
```

---

## 配置

存在 `~/.vidtrans/config.json`（**API Key 只在本机**）。

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `ffmpeg_dir` | 空 | ffmpeg 目录；也可用环境变量 `VIDTRANS_FFMPEG` |
| `asr_model` | `large-v3` | 识别模型，越大越准越慢 |
| `asr_device` / `asr_compute` | `cuda` / `float16` | 无 GPU 自动退回 `cpu` / `int8` |
| `asr_prompt` | 空 | 领域提示词 |
| `provider.base_url` | `https://api.deepseek.com/v1` | 任何 OpenAI 兼容接口 |
| `provider.model` | `deepseek-chat` | |
| `provider.api_key` | 空 | |
| `concurrency` | 6 | 并行翻译分块数；被限流就调小 |
| `chunk_size` | 120 | 每块字幕条数 |
| `max_chars_per_cue` | 36 | 切分时单条源文字数上限 |
| `max_display_duration` | 8.0 | 单条字幕最长显示秒数 |
| `max_line_chars` | 24 | 每行译文字数 |
| `glossary` / `extra_rules` | 空 | 术语表 / 额外翻译要求 |
| `burn` | false | 是否同时输出带字幕视频 |

---

## 实测数据

素材：2 小时 24 分日服直播，1920×1080 / 60fps。

| 环节 | 耗时 |
| --- | --- |
| 语音识别（large-v3 / CUDA / FP16） | 42 分钟 |
| 切分 + 翻译 + 出字幕 | 几分钟 |
| 烧录成片（h264_nvenc） | 约 35 分钟 |
| 结果 | 2,661 条字幕，0 重叠、0 术语违规、0 未翻译残留 |

---

## 常见问题

**拖视频进去没反应，浏览器反而自己播放了**
页面是用 `file://` 双击打开的。用 `run.bat` / `python app.py serve` 启动，
访问 <http://127.0.0.1:8765/>。新版页面检测到 `file://` 会直接弹红条提示。

**语言下拉框点了没反应**
同上，没连上后端时下拉不会被填充到最新配置。已内置兜底语言表，正常情况下一定有选项。

**找不到 ffmpeg**
放到项目 `bin\`、或设 `VIDTRANS_FFMPEG`。查找顺序：配置目录 → 环境变量 →
`bin\` → `tools\*\bin\` → PATH。

**GPU 报缺 `cublas64_12.dll`**
```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```
程序会自动把这两个包的 DLL 目录挂进 PATH。还不行就把 `asr_device` 改成 `cpu`。

**模型下载卡住**
默认走 `https://hf-mirror.com` 镜像（配置项 `hf_endpoint`）。`large-v3` 约 3GB，之后本地缓存。

**翻译 401 / 403**
Key 或 base_url 不对。base_url 通常要带 `/v1`，例如 `https://api.deepseek.com/v1`。

**被限流 429**
`concurrency` 调到 2~3，`chunk_size` 调到 60~80。

**字幕有空白段**
纯音乐 / 无人声段落会被 VAD 跳过，这是正常的。

---

## 架构

```
app.py                  薄封装（python app.py ...）
run.bat / run.sh        一键启动
vidtrans/
  cli.py                命令行解析
  config.py             配置读写
  utils.py              子进程 / 时间 / ffmpeg 查找
  cuda.py               Windows CUDA DLL 挂载
  ffmpeg.py             抽音频、烧录
  asr.py                faster-whisper 封装
  segment.py            切分（日语助词/片假名保护）+ 分块
  translate.py          OpenAI 兼容并发翻译
  subtitle.py           SRT / ASS / 双语 + 时间轴规整
  pipeline.py           串联全流程
  server.py             标准库 HTTP + SSE
  web/index.html        单页界面（无框架）
test/                   自测脚本
```

几个刻意的设计：

- **不用 faster-whisper 自带的音频解码** —— 它对 PyAV 版本敏感，统一先用 ffmpeg 出 16k wav。
- **烧录时把 cwd 切到 ASS 所在目录** —— `ass=` 过滤器按 cwd 找文件，中文路径/换盘符都不炸。
- **前端单文件、无构建** —— 将来想搬到 GitHub Pages 也不用改构建链。

---

## 测试

都不需要联网、显卡、API Key：

```bash
python -m compileall -q vidtrans app.py
node test/test_ui.js                          # 前端逻辑（DOM 桩，无需浏览器）
python app.py run 你的短视频.mp4 --mock        # 管线
python test/mock_api.py 8899 &                 # 本地假 OpenAI 接口
python app.py run 短视频.mp4 --base-url http://127.0.0.1:8899/v1 --api-key test
python app.py serve --port 8799 --no-browser &
python test/test_server.py http://127.0.0.1:8799 短视频.mp4
```

---

## 路线图

- [ ] **纯浏览器版**：WebCodecs 抽音轨 + 云端识别（Groq / OpenAI Whisper）+ 浏览器内翻译，
      可直接部署到 GitHub Pages。代价是不再免费、且不能烧录。
- [ ] OCR 翻译画面上的硬字幕（幻灯片、PV 字幕）
- [ ] 说话人分离
- [ ] 批量队列（一次拖多个视频）
- [ ] 术语表多套保存、按项目切换

---

## License

[MIT](LICENSE)
