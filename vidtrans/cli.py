# -*- coding: utf-8 -*-
"""命令行入口。

    vidtrans                      启动本地网页界面（默认）
    vidtrans serve --port 9000    指定端口
    vidtrans run input.mp4 ...    命令行直接跑（批量/服务器上用）
"""
import argparse
import os
import sys
import threading

from . import __version__, config as cfgmod


def build_parser():
    ap = argparse.ArgumentParser(prog="vidtrans",
                                 description="长视频字幕翻译流水线")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="启动本地网页界面")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")

    r = sub.add_parser("run", help="命令行直接处理一个文件")
    r.add_argument("input")
    r.add_argument("--src", default=None, help="源语言，如 ja / en")
    r.add_argument("--dst", default=None, help="目标语言，如 zh")
    r.add_argument("--model", default=None, help="识别模型，如 large-v3 / medium")
    r.add_argument("--asr-prompt", default=None, help="领域提示词")
    r.add_argument("--glossary", default=None, help="术语表 txt 路径")
    r.add_argument("--glossary-inline", default=None, help="术语表文本")
    r.add_argument("--rules", default=None, help="额外翻译要求")
    r.add_argument("--chunk-size", type=int, default=None)
    r.add_argument("--concurrency", type=int, default=None)
    r.add_argument("--burn", action="store_true", help="顺便把字幕烧进视频")
    r.add_argument("--mock", action="store_true", help="不调 API，只验证管线")
    r.add_argument("--outdir", default=None)
    r.add_argument("--ffmpeg-dir", default=None,
                   help="ffmpeg 所在目录（含有 ffmpeg.exe 的那个）")
    r.add_argument("--base-url", default=None, help="覆盖 API 地址")
    r.add_argument("--api-key", default=None, help="覆盖 API Key")
    r.add_argument("--model-name", default=None, help="覆盖翻译模型名")
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.cmd is None:
        args.cmd = "serve"

    if args.cmd == "serve":
        from .server import serve
        serve(host=args.host, port=args.port, open_browser=not args.no_browser)
        return 0

    return run_cli(args)


def run_cli(a):
    from .pipeline import Pipeline

    cfg = cfgmod.load()
    if a.src:
        cfg["src_lang"] = a.src
    if a.dst:
        cfg["dst_lang"] = a.dst
    if a.model:
        cfg["asr_model"] = a.model
    if a.asr_prompt is not None:
        cfg["asr_prompt"] = a.asr_prompt
    if a.rules:
        cfg["extra_rules"] = a.rules
    if a.chunk_size:
        cfg["chunk_size"] = a.chunk_size
    if a.concurrency:
        cfg["concurrency"] = a.concurrency
    if a.burn:
        cfg["burn"] = True
    if a.ffmpeg_dir:
        cfg["ffmpeg_dir"] = a.ffmpeg_dir
    if a.glossary:
        with open(a.glossary, encoding="utf-8") as f:
            cfg["glossary"] = f.read()
    if a.glossary_inline:
        cfg["glossary"] = a.glossary_inline

    prov = dict(cfg.get("provider") or {})
    if a.base_url:
        prov["base_url"] = a.base_url
    if a.api_key:
        prov["api_key"] = a.api_key
    if a.model_name:
        prov["model"] = a.model_name
    cfg["provider"] = prov

    src = os.path.abspath(a.input)
    if not os.path.exists(src):
        print("文件不存在：", src)
        return 2

    outdir = os.path.abspath(a.outdir or os.path.dirname(src))
    os.makedirs(outdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(src))[0] or "output"

    def emit(ev):
        t = ev.get("type")
        if t == "stage":
            print(f"\n[{ev.get('stage')}] {ev.get('msg', '')}", flush=True)
        elif t == "log":
            print("   " + str(ev.get("msg", "")), flush=True)
        elif t == "progress":
            frac = float(ev.get("frac") or 0)
            bar = "#" * int(frac * 28)
            print(f"\r   {bar:<28} {frac * 100:5.1f}%  {ev.get('msg', '')}   ",
                  end="", flush=True)
        elif t == "error":
            print("\n  !! " + str(ev.get("msg")), flush=True)

    pl = Pipeline(cfg, outdir, emit=emit, cancel=threading.Event(),
                  mock_translate=a.mock)
    res = pl.run(src, basename=base)
    print("\n\n完成：")
    for k, v in res["files"].items():
        if k != "src":
            print(f"  {k:10s} {v}")
    print(f"  字幕条数 {res['cues']}，用时 {res['elapsed']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
