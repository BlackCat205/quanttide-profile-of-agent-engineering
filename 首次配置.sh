#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"

if ! command -v git >/dev/null 2>&1; then
  echo '未找到 Git。请先安装 Git，再重新运行。' >&2
  exit 1
fi

PYTHON=''
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo '需要 Python 3.10 或以上及 venv 模块。' >&2
  exit 1
fi

"$PYTHON" -m venv .venv
.venv/bin/python -m pip install -r quanttide-asset/loops/second-brain-init/requirements.txt
.venv/bin/python -X utf8 quanttide-asset/asset-entry.py check
echo '配置完成。运行 ./启动向导.sh 启动工具。'
