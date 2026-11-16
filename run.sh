#!/usr/bin/env bash
# macOS / Linux 一键启动
set -e
cd "$(dirname "$0")"

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  echo
  echo "  没有找到 python3。请先安装 Python 3.10+。"
  echo
  exit 1
fi

if ! "$PY" -c "import faster_whisper" >/dev/null 2>&1; then
  echo
  echo "  第一次运行，正在安装依赖 faster-whisper / numpy ..."
  echo
  "$PY" -m pip install -r requirements.txt
fi

echo
echo "  正在启动 vidtrans ... 浏览器会自动打开 http://127.0.0.1:8765/"
echo
exec "$PY" app.py serve
