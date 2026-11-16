# -*- coding: utf-8 -*-
"""Windows：让 pip 安装的 cuBLAS / cuDNN DLL 可被 ctranslate2 找到。

必须在 import faster_whisper / ctranslate2 之前调用 enable()。
"""
import os
import sys


def enable(verbose=False):
    if not sys.platform.startswith("win"):
        return []
    try:
        import site
    except Exception:
        return []
    roots = []
    try:
        roots += [os.path.join(sp, "nvidia") for sp in site.getsitepackages()]
    except Exception:
        pass
    try:
        usp = site.getusersitepackages()
        if usp:
            roots.append(os.path.join(usp, "nvidia"))
    except Exception:
        pass

    dirs = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for pkg in sorted(os.listdir(root)):
            b = os.path.join(root, pkg, "bin")
            if os.path.isdir(b):
                dirs.append(b)
    for d in dirs:
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(d)
        except (AttributeError, OSError):
            pass
    if verbose and dirs:
        print("cuda dll dirs:", *dirs, sep="\n  ", file=sys.stderr)
    return dirs


def gpu_available():
    """ctranslate2 能否看到 CUDA 设备。"""
    enable()
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def ensure_cuda_libs():
    """若缺失，给出安装提示（不自动装，避免联网副作用）。"""
    try:
        import importlib.util
        missing = [m for m in ("nvidia.cublas", "nvidia.cudnn")
                   if importlib.util.find_spec(m) is None]
        return missing
    except Exception:
        return ["nvidia.cublas", "nvidia.cudnn"]
