#!/usr/bin/env python3
"""Scoped bridge for the Asset Cloud contract; never calls its archive runner."""
from pathlib import Path
import argparse
import json
import sys
import yaml

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / '.quanttide/asset/contract.yaml'
ENTRY = 'skills/second-brain-init/scripts/engine.py'

def load_contract():
    config = yaml.safe_load(CONTRACT.read_text(encoding='utf-8'))
    for name, asset in config['assets'].items():
        relative = asset['metadata']['path']
        path = (ROOT/relative).resolve()
        if not path.is_relative_to(ROOT) or not path.exists():
            raise ValueError('资产路径不存在或超出作用域：'+name)
        if asset.get('path') != relative:
            raise ValueError('兼容字段 path 与 metadata.path 不一致：'+name)
    skill = config['skills']['second-brain-init']
    if skill['entrypoint'] != ENTRY or skill['params']['default_mode'] != 'plan':
        raise ValueError('只允许已登记的 second-brain-init 入口和 plan 默认模式。')
    return config

def main():
    parser=argparse.ArgumentParser(description='资产云第二大脑配置入口')
    parser.add_argument('action',choices=['list','check','run'])
    parser.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    try:
        contract=load_contract()
        if args.action in ('list','check'):
            print(json.dumps({'status':'passed','assets':contract['assets'],'skill':contract['skills']['second-brain-init']},ensure_ascii=False,indent=2))
            return 0
        sys.path.insert(0,str(ROOT/Path(ENTRY).parent))
        from engine import cli
        rest=args.arguments
        if rest and rest[0]=='--': rest=rest[1:]
        return cli(rest)
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        print('配置不可用：'+str(exc),file=sys.stderr); return 1

if __name__=='__main__':
    raise SystemExit(main())
