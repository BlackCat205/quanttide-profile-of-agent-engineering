#!/usr/bin/env python3
"""Reproduce real local Git acceptance and save raw evidence; never writes GitHub."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import yaml

ROOT=Path(__file__).resolve().parents[3]
LOOP=ROOT/'loops/second-brain-init'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--native-cli',type=Path)
    args=parser.parse_args()
    out=args.output.resolve()
    if out.exists():parser.error('输出目录已存在，请使用新的目录。')
    out.mkdir(parents=True)
    summary={'started_at':datetime.now(timezone.utc).isoformat(),'status':'running','provider':'local','human_feedback':'simulated','human_acceptance':'not-tested','real_github':'not-tested','commands':[]}
    def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def capture(name,argv,cwd=ROOT,expect_success=True):
        result=subprocess.run([str(x) for x in argv],cwd=cwd,capture_output=True,text=True,encoding='utf-8',timeout=180)
        (out/(name+'.stdout.txt')).write_text(result.stdout,encoding='utf-8')
        (out/(name+'.stderr.txt')).write_text(result.stderr,encoding='utf-8')
        summary['commands'].append({'name':name,'argv':[str(x) for x in argv],'cwd':str(cwd),'returncode':result.returncode})
        save(out/'summary.json',summary)
        if expect_success and result.returncode:raise RuntimeError(name+' failed; see raw output')
        return result
    try:
        env={'system':platform.system(),'release':platform.release(),'machine':platform.machine(),'python':sys.version,'pyyaml':yaml.__version__,'git':subprocess.check_output(['git','--version'],text=True).strip()}
        save(out/'environment.json',env)
        sources=[ROOT/'asset-entry.py',ROOT/'.quanttide/asset/contract.yaml',LOOP/'install.py',LOOP/'requirements.txt',LOOP/'tests/test_implementation.py',Path(__file__)]
        sources += [p for p in (ROOT/'skills/second-brain-init').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        save(out/'source-sha256.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources)})
        capture('unit-tests',[sys.executable,'-m','unittest','discover','-s',LOOP/'tests','-p','test_implementation.py','-v'])
        capture('asset-contract',[sys.executable,ROOT/'asset-entry.py','check'])
        with tempfile.TemporaryDirectory(prefix='second-brain-acceptance-') as temp:
            temp=Path(temp);work=temp/'workspace';run=out/'demo'
            entry=[sys.executable,ROOT/'asset-entry.py','run']
            capture('demo-plan',entry+['plan','--config',LOOP/'configs/new-domain.yaml','--workspace',work,'--run-dir',run])
            plan=json.loads((run/'execution-plan.json').read_text())
            capture('demo-approve',entry+['approve','--run-dir',run,'--reviewer','automated-local-trial','--accept',plan['id'],'--simulated'])
            capture('demo-apply',entry+['apply','--run-dir',run])
            capture('demo-verify',entry+['verify','--run-dir',run])
            capture('package-and-run',[sys.executable,ROOT/'skills/second-brain-init/scripts/validate_outputs.py','--run-dir',run])
            inventory={}
            for repo in sorted((work/'repositories').iterdir()):
                def git(*argv):return subprocess.check_output(['git','-C',str(repo),*argv],text=True).strip()
                inventory[repo.name]={'head':git('rev-parse','HEAD'),'status':git('status','--porcelain'),'remote_head':git('ls-remote','origin','refs/heads/main').split()[0],'files':{p: (repo/p).read_text(encoding='utf-8') for p in ['README.md','LICENSE','CHANGELOG.md','.gitmodules','domains/README.md'] if (repo/p).is_file()}}
            save(out/'final-inventory.json',inventory)
            assert len(inventory)==8
            assert all(v['head']==v['remote_head'] and not v['status'] for v in inventory.values())
            report=json.loads((run/'verification-report.json').read_text())
            summary['demo']={'repositories':len(inventory),'operations':len(plan['operations']),'checks':len(report['details']),'status':report['status'],'approval_kind':report['approval_kind'],'workspace_retained':False}
            assert report['approval_kind']=='simulated' and not report['real_github_execution']
            if args.native_cli:
                cli=args.native_cli.resolve()
                capture('native-version',[cli,'version'])
                capture('native-config',[cli,'config'])
                capture('native-scan',[cli,'scan','--json'])
                valid=json.loads(capture('native-validate',[cli,'validate','--json']).stdout)
                assert valid['failed_assets']==0 and valid['total_assets']>0
                fixture=temp/'native-negative'
                (fixture/'.quanttide/asset').mkdir(parents=True)
                shutil.copy2(ROOT/'.quanttide/asset/contract.yaml',fixture/'.quanttide/asset/contract.yaml')
                (fixture/'skills/placeholder').mkdir(parents=True)
                (fixture/'loops/second-brain-init').mkdir(parents=True)
                invalid=json.loads(capture('native-negative',[cli,'validate','--json'],cwd=fixture,expect_success=False).stdout)
                assert invalid['failed_assets']>0
                summary['native']={'status':'passed','positive':valid,'negative':invalid,'binary_sha256':hashlib.sha256(cli.read_bytes()).hexdigest()}
            else:summary['native']={'status':'not-tested','reason':'No --native-cli supplied'}
        summary['status']='passed'
    except Exception as exc:
        summary['status']='failed';summary['error']=str(exc)
    finally:
        summary['finished_at']=datetime.now(timezone.utc).isoformat()
        save(out/'summary.json',summary)
    print(json.dumps({'status':summary['status'],'evidence':str(out)},ensure_ascii=False))
    return 0 if summary['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
