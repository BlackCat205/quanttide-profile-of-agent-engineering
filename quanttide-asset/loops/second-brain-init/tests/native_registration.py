"""Read-only native CLI acceptance with isolated negative fixtures; no GitHub writes."""
import argparse,hashlib,json,shutil,subprocess,tempfile
from pathlib import Path
from datetime import datetime,timezone
import yaml

ROOT=Path(__file__).resolve().parents[4]
def main():
    p=argparse.ArgumentParser();p.add_argument('--cli',type=Path,required=True);p.add_argument('--source-commit',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    cli=a.cli.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    records=[]
    with tempfile.TemporaryDirectory(prefix='asset-native-registration-') as temp:
        root=Path(temp)/'plugin';root.mkdir()
        files=filter(None,subprocess.check_output(['git','ls-files','-z','--','quanttide-asset'],cwd=ROOT).decode().split('\0'))
        for name in files:
            src=ROOT/name;dest=root/Path(name).relative_to('quanttide-asset');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
        def run(name,args,cwd=root):
            r=subprocess.run([str(cli),*args],cwd=cwd,capture_output=True,text=True,timeout=60)
            (out/(name+'.stdout.txt')).write_text(r.stdout);(out/(name+'.stderr.txt')).write_text(r.stderr)
            records.append({'name':name,'arguments':args,'cwd_role':'plugin' if cwd==root else 'negative-fixture','returncode':r.returncode,'at':datetime.now(timezone.utc).isoformat()});return r
        contract=root/'.quanttide/asset/contract.yaml';cfg=yaml.safe_load(contract.read_text())
        for asset in cfg['assets'].values():assert (root/asset['metadata']['path']).exists()
        for skill in cfg['skills'].values():assert (root/skill['entrypoint']).is_file()
        version=run('version',['version']);assert version.returncode==0
        config=run('config',['config']);assert config.returncode==0
        assert '资产数: 6' in config.stdout and '技能数: 1' in config.stdout and 'second-brain-init: v'+cfg['skills']['second-brain-init']['version'] in config.stdout
        scan=run('scan',['scan','--json']);assert scan.returncode==0;scan_data=json.loads(scan.stdout)
        valid=run('validate',['validate','--json']);data=json.loads(valid.stdout);assert valid.returncode==0 and data['failed_assets']==0 and data['total_assets']>0
        negative=Path(temp)/'missing-category';shutil.copytree(root,negative);shutil.rmtree(negative/'skills/second-brain-init')
        fail=run('negative-missing-category',['validate','--json'],negative);failure=json.loads(fail.stdout);assert failure['failed_assets']>0
        plain=run('negative-plain-exit',['validate'],negative);assert plain.returncode!=0
        bad=Path(temp)/'malformed';(bad/'.quanttide/asset').mkdir(parents=True);(bad/'.quanttide/asset/contract.yaml').write_text('assets: [')
        malformed=run('negative-malformed',['config'],bad);assert malformed.returncode!=0
        summary={'status':'passed','source_commit':a.source_commit,'binary_sha256':hashlib.sha256(cli.read_bytes()).hexdigest(),'contract_sha256':hashlib.sha256(contract.read_bytes()).hexdigest(),'platform':'Linux','registered_assets':len(cfg['assets']),'registered_skills':len(cfg['skills']),'scanned_directories':len(scan_data['assets']),'positive_validation':data,'negative_validation':failure,'negative_json_exit_code':fail.returncode,'records':records,'limits':['config proves deserialization and listing, not skill execution','validate checks configured directory policies, not complete business conformity','negative JSON report can return zero; failure count is checked explicitly','no Windows execution or real GitHub creation in this test']}
        (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print('Native registration checks passed; evidence: '+str(out))
if __name__=='__main__':main()
