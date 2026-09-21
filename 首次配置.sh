#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"

if ! command -v git >/dev/null 2>&1; then
  echo '未找到 Git。请打开“启动前检查.html”，按官方链接安装后重新运行。' >&2
  exit 1
fi
if ! git --version | awk '{split($3, v, "."); exit !(v[1] > 2 || (v[1] == 2 && v[2] >= 28))}'; then
  echo '需要 Git 2.28 或以上。请打开“启动前检查.html”查看下载链接。' >&2
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
  echo '需要 Python 3.10 或以上。请打开“启动前检查.html”查看下载链接。' >&2
  exit 1
fi

if ! "$PYTHON" -m venv .venv; then
  echo '无法创建 Python 环境。请检查是否安装了 venv 和 pip（见“启动前检查.html”）。' >&2
  exit 1
fi
.venv/bin/python -m pip install -r quanttide-asset/loops/second-brain-init/requirements.txt
.venv/bin/python -X utf8 quanttide-asset/asset-entry.py check
echo '配置完成。运行 ./启动向导.sh 启动工具。'
