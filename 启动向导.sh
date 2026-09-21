#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
if [ ! -x .venv/bin/python ]; then
  echo '请先运行 ./首次配置.sh 完成环境准备。' >&2
  exit 1
fi
exec .venv/bin/python -X utf8 launch.py "$@"
