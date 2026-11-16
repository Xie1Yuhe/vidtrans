# 发布到 GitHub 的清单

仓库已经准备好，只差填上你的用户名。按顺序做即可。

---

## 一、填上仓库地址（1 分钟）

仓库里目前有几处 `github.com/USER/vidtrans` 占位符（README 徽章、pyproject 的
Homepage/Issues、CONTRIBUTING 的 clone 地址、CHANGELOG 的版本链接）。

跑一次脚本就能全部替换：

```bash
python tools/finalize.py 你的GitHub用户名

# 先看看会改什么（不写文件）
python tools/finalize.py 你的GitHub用户名 --dry-run

# 仓库名不叫 vidtrans
python tools/finalize.py 你的GitHub用户名 --repo 你想要的仓库名
```

脚本最后会复查还有没有残留，并打印下一步的 git 命令。

> 不想跑脚本也行，手动把 `USER` 改成你的用户名即可（一共 5 个文件）。

---

## 二、建仓库并推送（3 分钟）

在 GitHub 上新建一个**空仓库**（名字建议 `vidtrans`）。

> ⚠️ **不要**勾选 "Add a README file" / ".gitignore" / "license"，
> 否则会和本地已有内容冲突，推不上去。

然后（把路径换成你自己的项目目录）：

```bash
cd /d "<你 clone 或存放本项目的目录>"

git add -A
git commit -m "chore: 填写仓库地址"

git remote add origin https://github.com/你的用户名/vidtrans.git
git branch -M main
git push -u origin main
```

第一次推会要求登录。建议用 **HTTPS + Personal Access Token**（GitHub 密码不能用），
或者装 GitHub CLI 后 `gh auth login` 走浏览器授权。

---

## 三、推送后检查（2 分钟）

> **关于 CI 工作流**：GitHub 不允许**没有 `workflow` 权限**的 Personal Access Token
> 推送 `.github/workflows/` 下的文件，会报
> `refusing to allow a Personal Access Token to create or update workflow ... without workflow scope`。
>
> 两种补法，任选其一：
>
> 1. **网页上传（最省事）**：仓库页 → `Add file` → `Create new file` →
>    路径填 `.github/workflows/ci.yml`，把本地同名文件的内容粘进去，提交。
> 2. **换 token**：生成 token 时除了 `repo` 再勾上 **`workflow`**，然后
>    `git push` 即可。
>
> 补上之后，把 README 顶部这行徽章加回去（中英两份都要加）：
>
> ```markdown
> [![ci](https://github.com/你的用户名/vidtrans/actions/workflows/ci.yml/badge.svg)](https://github.com/你的用户名/vidtrans/actions/workflows/ci.yml)
> ```
>
> 目前徽章被摘掉了，因为工作流还没推上去时它会显示成破图。

1. **CI 是否绿**：仓库页 → Actions，应该看到 `ci` 工作流跑起来。
   跑的是语法检查 + 导入检查 + 前端 DOM 桩测试，**不需要 GPU / 模型 / API Key**，
   正常 1 分钟内完成。
2. **README 徽章是否显示**：刷新仓库首页，顶部的 ci / python / license / platform 徽章应该都能渲染。
   如果 ci 徽章是灰的，说明第一次 Actions 还没跑完，等一两分钟。
3. **截图是否显示**：README 里的界面图来自 `docs/screenshot.png`。
4. **About 区**：右侧齿轮 → 填 Description、Website，勾上 Topics，建议：
   `subtitle` `subtitles` `whisper` `asr` `translation` `ffmpeg` `video` `srt` `chinese`

---

## 四、发版（可选，但推荐）

打一个 tag，让 "Releases" 页面有东西：

```bash
git tag -a v1.0.0 -m "vidtrans v1.0.0"
git push origin v1.0.0
```

然后在 GitHub 上 **Releases → Draft a new release**，选 `v1.0.0`，
把 `CHANGELOG.md` 里 1.0.0 那段贴进去，发布。

> 注意：仓库里**没有**打包好的二进制。用户是 clone / 下载 ZIP 源码后双击 `run.bat`。
> 要不要出免安装 exe 见文末。

---

## 五、发布前最后确认

这几件事我已经做完了，你只要知道它们成立：

| 检查 | 状态 |
| --- | --- |
| 没有提交 `bin/`（200MB ffmpeg）、`.hf/`（3GB 模型）、`.python/` | ✅ |
| 没有 API Key / 个人路径泄漏（已全仓 grep） | ✅ |
| 仓库里最大的文件是 `docs/screenshot.png`（322KB） | ✅ |
| `run.bat` 是 ASCII + CRLF，`.gitattributes` 已锁定 | ✅ |
| 有 LICENSE（MIT）、CONTRIBUTING、SECURITY、CHANGELOG | ✅ |
| 有 Issue / PR 模板 | ✅ |
| CI 不需要 GPU / 模型 / Key 就能跑 | ✅ |
| 有示例术语表 `examples/glossary.txt` | ✅ |

---

## 六、之后可以考虑

- **免安装 exe**：用 PyInstaller 打包成双击即用（体积会到 300MB+，因为要带
  faster-whisper 和 CUDA 库）。想要的话我可以加一个 `build_exe.py` + GitHub Actions 自动出包。
- **纯浏览器版**：WebCodecs 抽音轨 + 云端识别（Groq / OpenAI Whisper）+ 浏览器内翻译，
  可以部署成 GitHub Pages，粉丝打开网页就能用。代价是不再免费、且不能烧录。
- **术语表仓库**：单独开一个 repo 收集各作品的术语表，让社区贡献。
