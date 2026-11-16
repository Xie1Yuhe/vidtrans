# 安全说明

## 你的数据在哪

- **API Key**：只保存在本机 `~/.vidtrans/config.json`，不会上传到任何服务器
- **视频与字幕**：只在你本机处理，`~/.vidtrans/jobs/` 下；不会上传
- **翻译请求**：只把「字幕文本」发给你自己配置的那个 API 服务商（DeepSeek / OpenAI / 本地 Ollama 等）。
  视频画面和音轨**不会**被发送
- **本地服务**：只监听 `127.0.0.1`，不对外开放

如果你把 `asr_device` 配成本地 GPU/CPU（默认就是本地），语音识别也完全离线。

## 报告漏洞

如果发现安全问题（例如本地服务可被外部访问、配置被意外外泄），
**请不要开公开 issue**，改用 GitHub 的
[私密漏洞报告](https://docs.github.com/zh/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
功能，或直接发给仓库维护者。

## 已知的非安全问题

- 本地 Web 服务没有鉴权，因为它只绑 `127.0.0.1`。**不要把 `--host` 改成 `0.0.0.0`**，
  除非你清楚同一局域网内任何人都能操作它。
- 上传的文件名会被清洗（去掉路径分隔符与非法字符），但请只上传你自己信任的文件。
