"""Reviewed adoption of a legacy empty repository, into a separate execution plan."""
import copy
import json
import base64
import hashlib
from pathlib import Path
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
    # Only the interrupted repository is needed for this preview. Every other
    # repository is checked immediately before an operation can touch it.
    current=copy.deepcopy(log['checkpoint'])
    current[name]=e.snapshot(provider,[name])[name]
    info=provider.info(name);state=current[name]
    e.require(info.get('can_push') and not info.get('archived') and info.get('owner_id')==plan['github_identity']['owner_id'],'目标所属账号或写入权限不匹配。')
    e.require(state['remote'] and state['local'] is None and not provider.repo(name).exists(),'仅支持远端存在且本地尚未下载；本地残留需维护者检查。')
    # Read immutable commit/tree/blob objects; preview never needs a Git clone.
    endpoint='repos/'+plan['organization']+'/'+name+'/git/'
    def api(path):return json.loads(e.command(['gh','api',endpoint+path]).stdout)
    commit=api('commits/'+state['remote'])
    e.require(commit.get('sha')==state['remote'] and commit.get('parents')==[],'仓库已有后续提交或提交证据不一致，不能接续。')
    tree=api('trees/'+commit['tree']['sha'])
    entries=tree.get('tree',[])
    e.require(not tree.get('truncated') and len(entries)==1 and entries[0].get('path')=='README.md' and entries[0].get('mode')=='100644' and entries[0].get('type')=='blob','仓库不止标准 README 文件，停止恢复。')
    blob=api('blobs/'+entries[0]['sha'])
    e.require(blob.get('encoding')=='base64' and blob.get('sha')==entries[0]['sha'],'README 证据不一致。')
    content=base64.b64decode(blob['content']).decode('utf-8')
    e.require(content.strip()=='# '+name,'初始 README 内容不同。')
    e.require(provider.head(name,info)==state['remote'],'核对期间目标仓库变化。')
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
        e.require(old['engine_sha256']==LEGACY_ENGINE and old['provider']=='github'
                  and old['scenario']=='new-domain','仅支持已知旧版 GitHub 新领域中断任务。')
        e.require(not (folder/'partial-migration.json').exists(),'已生成恢复任务，请打开已有恢复记录。')
        proposal=e.read_json(folder/'partial-proposal.json');signature=proposal.pop('id')
        e.require(signature==accepted_id==e.digest(proposal) and proposal['engine_sha256']==hashlib.sha256(Path(e.__file__).read_bytes()).hexdigest(),'恢复方案或程序版本已变化，请重新检查。')
        plan=old;log=e.read_json(folder/'execution-log.json')
        approval=e.read_json(folder/'approval-record.json')
        e.require(log['plan_id']==plan['id'] and approval['plan_id']==plan['id']
                  and approval.get('accepted') and not approval.get('simulated'),
                  '原计划与人工确认不匹配。')
        name=proposal['repo']
        op=next((x for x in plan['operations'] if x['id'] not in log['completed']),None)
        e.require(op and op['id']==proposal['operation'] and op['repo']==name and op['kind']=='ensure-repo',
                  '原任务的下一步已经变化。')
        e.check_identity(plan);provider=e.Provider(plan['workspace'],'github',plan['organization'])
        info=provider.info(name)
        e.require(info.get('id')==proposal['repository_id'] and info.get('owner_id')==plan['github_identity']['owner_id']
                  and info.get('can_push') and not info.get('archived'),
                  '确认时仓库身份、权限或状态已经变化。')
        e.require(provider.head(name,info)==proposal['commit'] and not provider.repo(name).exists(),
                  '确认时提交版本或本地状态已经变化。')
        current=copy.deepcopy(log['checkpoint']);current[name]=copy.deepcopy(proposal['before'][name])
        e.require(reviewer.strip(),'请填写核对人姓名。')
        plan=copy.deepcopy(plan);plan.pop('id');plan.update(version=e.VERSION,engine_sha256=proposal['engine_sha256'],migrated_from=proposal['source_plan'],created_at=e.now());plan['id']=e.digest(plan)
        e.require(not destination.exists(),'恢复任务目录已存在。')
        e.save(destination/'execution-plan.json',plan)
        e.approve(destination,reviewer,plan['id'],simulated=False)
        log=copy.deepcopy(log);log.update(plan_id=plan['id'],status='paused',checkpoint=current,
                                         created_receipts={name:current[name]},
                                         phases=[{'op':proposal['operation'],'repo':name,'kind':'remote-created',
                                                  'status':'passed','at':e.now(),'recovered_from':'reviewed-legacy'}])
        log.pop('error',None)
        e.save(destination/'execution-log.json',log)
        for filename in ('survey.json',):
            if (folder/filename).exists():e.save(destination/filename,e.read_json(folder/filename))
        record={'source_plan':proposal['source_plan'],'destination':destination.name,'reviewer':reviewer,'at':e.now(),'proposal_id':signature,'note':'人工核对初始骨架后接续；不宣称已证明旧任务创建归属。'}
        e.save(destination/'migration.json',record);e.save(folder/'partial-migration.json',record)
        return plan
