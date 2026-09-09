"""Reviewed adoption of a legacy empty repository, into a separate execution plan."""
import copy
import hashlib
from pathlib import Path
import tempfile
import engine as e

LEGACY_ENGINE = 'a3f8b7e435ffc531d7d974365ea0aa3722c210cd60a10d49ff16d13cd3342cb5'

def inspect(folder):
    folder=Path(folder);plan=e.load_plan(folder,readonly=True)
    e.require(plan['engine_sha256']==LEGACY_ENGINE and plan['provider']=='github' and plan['scenario']=='new-domain','仅支持已知旧版 GitHub 新领域中断任务。')
    log=e.read_json(folder/'execution-log.json');approval=e.read_json(folder/'approval-record.json')
    e.require(log['plan_id']==plan['id'] and approval['plan_id']==plan['id'] and approval.get('accepted') and not approval.get('simulated'),'原计划与人工确认不匹配。')
    op=next((x for x in plan['operations'] if x['id'] not in log['completed']),None)
    e.require(op and op['kind']=='ensure-repo' and log.get('current',{}).get('op')==op['id'],'仅支持建立仓库步骤中断。')
    name=op['repo'];before=log['checkpoint'][name]
    e.require(not before['remote_exists'] and before['local'] is None,'中断前目标必须不存在。')
    e.check_identity(plan);provider=e.Provider(plan['workspace'],'github',plan['organization'])
    current=e.snapshot(provider,plan['names'])
    e.require(all(current[n]==state for n,state in log['checkpoint'].items() if n!=name),'其他仓库已有变化，停止恢复。')
    info=provider.info(name);state=current[name]
    e.require(info.get('can_push') and not info.get('archived') and info.get('owner_id')==plan['github_identity']['owner_id'],'目标所属账号或写入权限不匹配。')
    e.require(state['remote'] and state['local'] is None and not provider.repo(name).exists(),'仅支持远端存在且本地尚未下载；本地残留需维护者检查。')
    # Inspect an isolated clone; no writes to the target workspace or remote.
    with tempfile.TemporaryDirectory(prefix='second-brain-legacy-check-') as tmp:
        repo=Path(tmp)/'repository'
        e.command(['git','clone',provider.remote(name),repo])
        e.require(e.git(repo,'rev-parse','HEAD').stdout.strip()==state['remote'],'核对期间远端变化。')
        e.require(e.git(repo,'rev-list','--count','HEAD').stdout.strip()=='1','仓库已有后续提交，不能当作初始骨架接续。')
        e.require(e.git(repo,'ls-tree','--name-only','HEAD').stdout.strip()=='README.md','仓库不止初始 README，停止恢复。')
        content=e.text_at(repo,'README.md')
        e.require(content.strip()=='# '+name,'初始 README 内容不同。')
    e.require(e.snapshot(provider,plan['names'])==current,'核对期间仓库变化。')
    proposal={'source_plan':plan['id'],'repo':name,'operation':op['id'],'organization':plan['organization'],'repository_id':info['id'],'commit':state['remote'],'content':content,'before':current,'checked_at':e.now(),'engine_sha256':hashlib.sha256(Path(e.__file__).read_bytes()).hexdigest()}
    return plan,log,proposal

def preview(folder):
    folder=Path(folder);plan=e.load_plan(folder,readonly=True)
    with e.execution_locks(folder,plan['workspace']):
        _,_,proposal=inspect(folder)
        proposal['id']=e.digest(proposal);e.save(folder/'partial-proposal.json',proposal)
    return proposal

def migrate(folder,destination,accepted_id,reviewer):
    folder=Path(folder);destination=Path(destination)
    old=e.load_plan(folder,readonly=True)
    with e.execution_locks(folder,old['workspace']):
        e.require(not (folder/'partial-migration.json').exists(),'已生成恢复任务，请打开已有恢复记录。')
        proposal=e.read_json(folder/'partial-proposal.json');signature=proposal.pop('id')
        e.require(signature==accepted_id==e.digest(proposal) and proposal['engine_sha256']==hashlib.sha256(Path(e.__file__).read_bytes()).hexdigest(),'恢复方案或程序版本已变化，请重新检查。')
        plan,log,current=inspect(folder)
        e.require(current['before']==proposal['before'] and current['commit']==proposal['commit'],'确认后仓库发生变化，停止。')
        e.require(reviewer.strip(),'请填写核对人姓名。')
        plan=copy.deepcopy(plan);plan.pop('id');plan.update(version=e.VERSION,engine_sha256=proposal['engine_sha256'],migrated_from=proposal['source_plan'],created_at=e.now());plan['id']=e.digest(plan)
        e.require(not destination.exists(),'恢复任务目录已存在。')
        e.save(destination/'execution-plan.json',plan)
        e.approve(destination,reviewer,plan['id'],simulated=False)
        log=copy.deepcopy(log);log.update(plan_id=plan['id'],status='paused',checkpoint=current['before'],created_receipts={proposal['repo']:current['before'][proposal['repo']]},phases=[{'op':proposal['operation'],'repo':proposal['repo'],'kind':'remote-created','status':'passed','at':e.now()}]);log.pop('error',None)
        e.save(destination/'execution-log.json',log)
        for filename in ('survey.json',):
            if (folder/filename).exists():e.save(destination/filename,e.read_json(folder/filename))
        record={'source_plan':proposal['source_plan'],'destination':destination.name,'reviewer':reviewer,'at':e.now(),'proposal_id':signature,'note':'人工核对初始骨架后接续；不宣称已证明旧任务创建归属。'}
        e.save(destination/'migration.json',record);e.save(folder/'partial-migration.json',record)
        return plan
