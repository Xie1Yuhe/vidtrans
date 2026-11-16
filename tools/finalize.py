# -*- coding: utf-8 -*-
"""发布前的一键替换：把仓库里的 USER 占位符换成真实的 GitHub 用户名。

用法：
    python tools/finalize.py <你的用户名>            # 写死
    python tools/finalize.py <你的用户名> --repo 名字  # 改仓库名（默认 vidtrans）
    python tools/finalize.py <你的用户名> --dry-run    # 只看会改什么

会处理这些文件里的 `github.com/USER/vidtrans`：
    pyproject.toml / CONTRIBUTING.md / README.md / README.en.md / CHANGELOG.md
"""
import argparse
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = ["pyproject.toml", "CONTRIBUTING.md", "README.md",
           "README.en.md", "CHANGELOG.md"]

USER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def main():
    ap = argparse.ArgumentParser(description="把 USER 占位符替换成真实 GitHub 用户名")
    ap.add_argument("username", help="GitHub 用户名")
    ap.add_argument("--repo", default="vidtrans", help="仓库名，默认 vidtrans")
    ap.add_argument("--dry-run", action="store_true", help="只显示改动，不写文件")
    a = ap.parse_args()

    if not USER_RE.match(a.username):
        print(f"用户名格式不对：{a.username!r}（只允许字母、数字、连字符）")
        return 2
    if not REPO_RE.match(a.repo):
        print(f"仓库名格式不对：{a.repo!r}")
        return 2

    old = "github.com/USER/vidtrans"
    new = f"github.com/{a.username}/{a.repo}"
    if a.repo != "vidtrans":
        # 包名/命令名仍然是 vidtrans，只改 URL 里的仓库段
        old_pat = re.compile(r"github\.com/USER/vidtrans")
    else:
        old_pat = re.compile(re.escape(old))

    changed, skipped = [], []
    for name in TARGETS:
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            skipped.append((name, "文件不存在"))
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        n = len(old_pat.findall(text))
        if n == 0:
            skipped.append((name, "没有占位符"))
            continue
        text2 = old_pat.sub(new, text)
        if a.dry_run:
            changed.append((name, n, "（dry-run，未写入）"))
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text2)
        changed.append((name, n, "已写入"))

    print(f"\n目标：{new}\n")
    for name, n, note in changed:
        print(f"  改 {name:18s} {n} 处   {note}")
    for name, why in skipped:
        print(f"  跳过 {name:16s} {why}")

    # 复查还有没有残留
    left = []
    for name in TARGETS:
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            if "USER/vidtrans" in f.read():
                left.append(name)

    print()
    if left:
        print("仍有占位符残留：", ", ".join(left))
        return 1
    print("没有残留占位符了。")
    print("\n下一步：")
    print(f'  git add -A && git commit -m "chore: 填写仓库地址"')
    print(f"  git remote add origin https://github.com/{a.username}/{a.repo}.git")
    print("  git push -u origin main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
