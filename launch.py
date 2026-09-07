#!/usr/bin/env python3
"""Portable launcher for the repository-backed local UI."""
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent

def main():
    if sys.version_info<(3,10):
        print('需要 Python 3.10 或以上，请先更新 Python。');return 1
    if not shutil.which('git'):
        print('没有找到 Git。请先安装 Git for Windows，再重新打开启动器。');return 1
    raw=subprocess.run(['git','--version'],capture_output=True,text=True).stdout
    match=re.search(r'(\d+)\.(\d+)',raw)
    if not match or tuple(map(int,match.groups()))<(2,28):
        print('需要 Git 2.28 或以上，请先更新 Git。');return 1
    if not importlib.util.find_spec('yaml'):
        print('缺少运行依赖，请先双击“首次配置.bat”。');return 1
    os.environ['PYTHONUTF8']='1'
    # Git for Windows handles long generated submodule paths more reliably with this
    # process-scoped setting. No user's global Git configuration is edited.
    if os.name=='nt':
        count=int(os.environ.get('GIT_CONFIG_COUNT','0'))
        os.environ['GIT_CONFIG_COUNT']=str(count+1)
        os.environ['GIT_CONFIG_KEY_'+str(count)]='core.longpaths'
        os.environ['GIT_CONFIG_VALUE_'+str(count)]='true'
    command=[sys.executable,'-X','utf8',str(ROOT/'quanttide-asset/loops/second-brain-init/ui/app.py'),*sys.argv[1:]]
    return subprocess.call(command,cwd=ROOT)

if __name__=='__main__':raise SystemExit(main())
