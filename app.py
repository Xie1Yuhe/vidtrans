# -*- coding: utf-8 -*-
"""兼容入口：python app.py [serve|run] ...

真正的逻辑在 vidtrans/cli.py；这个文件只是让「不安装、直接 clone 下来跑」也顺手。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vidtrans.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
