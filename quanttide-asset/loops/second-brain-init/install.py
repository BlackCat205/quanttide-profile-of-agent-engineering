#!/usr/bin/env python3
"""Copy the self-contained skill to a chosen host directory; no global install."""
import argparse
from pathlib import Path
import shutil

SOURCE=Path(__file__).resolve().parents[2]/'skills/second-brain-init'

def install(destination):
    destination=Path(destination).resolve()
    if destination.exists():
        raise ValueError('目标已存在；请选新目录，或由维护者审阅更新。')
    shutil.copytree(SOURCE,destination,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    required=['SKILL.md','scripts/engine.py','assets/specification.yaml']
    if not all((destination/p).is_file() for p in required):
        raise ValueError('安装副本缺少运行文件。')
    return destination

if __name__=='__main__':
    p=argparse.ArgumentParser(description='安装第二大脑技能到指定目录')
    p.add_argument('--destination',required=True)
    args=p.parse_args()
    print(install(args.destination))
