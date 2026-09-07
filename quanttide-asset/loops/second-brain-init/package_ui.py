#!/usr/bin/env python3
"""Package the checked-in local UI, rules, documents and test records; no runtimes."""
import argparse
from pathlib import Path
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[3]
ROOT_FILES=['START_HERE.md','launch.py','首次配置.bat','启动向导.bat']

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    output=args.output.resolve()
    if output.exists():p.error('输出文件已存在，请使用新文件名。')
    tracked=subprocess.check_output(['git','ls-files','-z','--','quanttide-asset',*ROOT_FILES],cwd=ROOT).decode().split('\0')
    files=[name for name in tracked if name and (ROOT/name).is_file()]
    for name in ROOT_FILES:
        if name not in files:p.error('请先将入口文件保存至 Git：'+name)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for name in files:z.write(ROOT/name,'second-brain-ui/'+name)
    print(str(output))

if __name__=='__main__':main()
