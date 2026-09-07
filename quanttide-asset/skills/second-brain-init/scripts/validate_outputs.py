#!/usr/bin/env python3
"""Validate a portable skill and optionally a real completed run."""
import argparse
import json
from pathlib import Path
import re
import sys

import yaml
import engine

ROOT=Path(__file__).resolve().parents[1]

def validate_package():
    failures=[]
    required=['SKILL.md','scripts/engine.py','assets/specification.yaml','references/request-schema.md','references/contract-rules.md','references/scenarios.md']
    for name in required:
        if not (ROOT/name).is_file():failures.append('缺少 '+name)
    if failures:return failures
    text=(ROOT/'SKILL.md').read_text(encoding='utf-8')
    front=yaml.safe_load(text.split('---',2)[1]) if text.startswith('---\n') else {}
    if front.get('name')!='second-brain-init' or not front.get('description'):failures.append('Skill frontmatter 无效')
    for link in re.findall(r'\]\(([^)]+)\)',text):
        if '://' not in link and not (ROOT/link).is_file():failures.append('断开的引用：'+link)
    spec=yaml.safe_load((ROOT/'assets/specification.yaml').read_text(encoding='utf-8'))
    if len(spec.get('asset_types',{}))!=20:failures.append('资产类型必须为二十类')
    if len(spec.get('scenarios',{}))!=7:failures.append('缺少场景')
    for source in spec.get('sources',{}).values():
        if not re.fullmatch('[a-f0-9]{40}',source.get('commit','')):failures.append('来源未锁定 Git 提交')
    return failures

def main():
    parser=argparse.ArgumentParser(description='检查插件完整性和实际执行结果')
    parser.add_argument('--run-dir',type=Path)
    args=parser.parse_args()
    try:
        failures=validate_package()
        if args.run_dir:
            report=engine.verify(engine.load_plan(args.run_dir))
            if report['status']!='passed':failures.append('执行结果未通过验证：'+json.dumps(report,ensure_ascii=False))
        print(json.dumps({'status':'failed' if failures else 'passed','failures':failures},ensure_ascii=False,indent=2))
        return 1 if failures else 0
    except (OSError, ValueError, engine.WorkflowError) as exc:
        print(str(exc),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
