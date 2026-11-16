# 参与贡献

先谢谢你有兴趣。这个项目很小，改动不必很重。

## 开发环境

```bash
git clone https://github.com/Xie1Yuhe/vidtrans.git
cd vidtrans
python -m pip install -r requirements.txt
python app.py serve          # 本地起服务
```

自测（都不需要联网、不需要显卡、不需要 API Key）：

```bash
python -m compileall -q vidtrans app.py     # 语法
node test/test_ui.js                        # 前端逻辑（DOM 桩）
python app.py run test/sample.mp4 --mock    # 管线（需自备一个短视频）
```

## 提交前请确认

1. `python -m compileall -q vidtrans app.py` 通过
2. `node test/test_ui.js` 输出 `RESULT: PASS`
3. 如果改了 `vidtrans/web/index.html`，务必同时更新 `test/test_ui.js` 里的断言
4. 新加的配置项要有默认值，写在 `vidtrans/config.py` 的 `DEFAULTS` 里

## 代码风格

- Python：4 空格缩进，尽量用标准库，不引入非必要依赖
- 前端：单文件、原生 JS、无构建步骤（这样 GitHub Pages 也能直接用）
- 注释写「为什么」而不是「做了什么」

## 两个容易踩的坑

**`run.bat` 必须是 ASCII + CRLF。**
Windows 的 cmd 只认 CRLF 换行，并按系统码页（中文是 GBK）解析文件；
用 UTF-8 或 LF 保存会把命令行从中间截断，报一堆「'xxx' 不是内部或外部命令」。
所以这个文件里**不要写中文**（中文引导交给网页和 README），
`.gitattributes` 已经锁了 `run.bat text eol=crlf`。

**HTTP 头不能直接放中文文件名。**
`Content-Disposition` 只支持 latin-1，中文/日文文件名要按 RFC 5987
编码成 `filename*=UTF-8''<percent-encoded>`，见 `server.py` 的 `_download()`。

## 想加新能力？

欢迎开 issue 先聊。几个方向：

- 云端识别后端（Groq / OpenAI Whisper），让用户没有显卡也能用
- OCR 翻译画面上的硬字幕
- 说话人分离
- 纯浏览器版（WebCodecs + 云端 API，能直接放 GitHub Pages）

## License

提交的代码按 MIT 协议发布。
