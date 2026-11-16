# 自测脚本

这些测试都不需要联网、显卡、API Key。

| 文件 | 作用 |
| --- | --- |
| `test_ui.js` | 用最小 DOM 桩执行 `vidtrans/web/index.html` 里的脚本，验证拖拽监听已绑定、语言下拉有选项、后端不可用时给提示。**不需要浏览器。** |
| `test_server.py` | 后端端到端：启动服务 → 上传 → 运行（mock 翻译）→ 轮询 → 下载三种字幕 |
| `mock_api.py` | 本地假 OpenAI 接口，用来验证真实 HTTP 翻译路径而不花钱 |

## 需要一个样例视频

仓库里不放视频文件（`.gitignore` 忽略了 `*.mp4`）。自己准备一个 1~2 分钟的片段即可：

```bash
# 从任意视频里切 100 秒
ffmpeg -ss 60 -t 100 -i 原视频.mp4 -c copy test/sample.mp4
```

然后：

```bash
# 前端逻辑
node test/test_ui.js

# 管线（mock 翻译）
python app.py run test/sample.mp4 --mock --model tiny

# 真实 HTTP 翻译路径
python test/mock_api.py 8899 &
python app.py run test/sample.mp4 --base-url http://127.0.0.1:8899/v1 --api-key test

# 网页端到端
python app.py serve --port 8799 --no-browser &
python test/test_server.py http://127.0.0.1:8799 test/sample.mp4
```

首次跑 `large-v3` 会下载约 3GB 模型；只想验证管线的话用 `--model tiny` 快得多。
