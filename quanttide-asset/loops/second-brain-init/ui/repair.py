"""Narrow recovery for the 0.3.0 new-domain root LICENSE omission.
Never changes the original execution plan, approval, or checkpoint.
"""
import hashlib
from pathlib import Path
import engine as e


def context(folder):
    folder=Path(folder);plan=e.load_plan(folder,readonly=True)
    approval=e.read_json(folder/'approval-record.json');log=e.read_json(folder/'execution-log.json')
    e.require(approval.get('accepted') and approval['plan_id']==plan['id'] and log['plan_id']==plan['id'],'原计划和确认记录不匹配。')
    e.require(not approval.get('simulated') or plan['provider']=='local','真实 GitHub 不能使用模拟确认。')
    root=plan['config']['root_repo']
    e.require(plan['scenario']=='new-domain' and not plan['before'][root]['remote_exists'],'专用修复仅支持新建领域时的全新总入口。')
    e.require(set(log['completed'])=={op['id'] for op in plan['operations']},'尚有创建步骤未完成，不能使用补交修复。')
    provider=e.Provider(plan['workspace'],plan['provider'],plan['organization'])
    e.check_identity(plan)
    return plan,log,provider,root


def preview(folder):
    folder=Path(folder);plan,log,provider,root=context(folder)
    e.require(not (folder/'repair-record.json').exists(),'修复已开始，请继续已确认的修复或重新检查结果。')
    with e.execution_locks(folder,plan['workspace']):
        current=e.snapshot(provider,plan['names'])
        e.require(current==log['checkpoint'],'当前状态与原任务检查点不同，停止补交，请导出诊断包。')
        for name,state in current.items():
            e.require(state['local']==state['remote'] and state['remote_exists'],'本地与远端不一致，停止补交。')
            e.require(state['status']==('?? LICENSE\n' if name==root else ''),'仅支持总入口唯一残留 LICENSE 的情况。')
        repo=provider.repo(root)
        e.require(e.text_at(repo,'LICENSE')==e.CC,'许可文件不是原工作流模板，停止自动补交。')
        if provider.kind=='github':
            info=provider.info(root)
            e.require(info.get('can_push') and not info.get('archived') and info.get('owner_id')==plan['github_identity']['owner_id'],'账号无权补交到此仓库。')
        proposal={'plan_id':plan['id'],'created_at':e.now(),'root':root,'before':current,'files':['LICENSE'],'content':e.CC,'file_sha256':hashlib.sha256((repo/'LICENSE').read_bytes()).hexdigest(),'engine_sha256':hashlib.sha256(Path(e.__file__).read_bytes()).hexdigest()}
        proposal['id']=e.digest(proposal);e.save(folder/'repair-plan.json',proposal)
        return proposal


def apply(folder,accepted_id):
    folder=Path(folder);plan,log,provider,root=context(folder)
    proposal=e.read_json(folder/'repair-plan.json');signature=proposal.pop('id')
    e.require(signature==e.digest(proposal) and accepted_id==signature and proposal['plan_id']==plan['id'],'补交方案已变化，请重新检查。')
    e.require(proposal['engine_sha256']==hashlib.sha256(Path(e.__file__).read_bytes()).hexdigest(),'修复程序版本已变化，请维护者检查。')
    repo=provider.repo(root);before=proposal['before'];old=before[root]['local']
    record_path=folder/'repair-record.json'
    with e.execution_locks(folder,plan['workspace']):
        record=e.read_json(record_path) if record_path.exists() else {'repair_id':signature,'confirmed_at':e.now(),'status':'confirmed','events':[]}
        e.require(record['repair_id']==signature,'修复记录不匹配。')
        e.save(record_path,record)
        current=e.snapshot(provider,plan['names'])
        for name,state in current.items():
            if name!=root:e.require(state==before[name],'其他仓库已变化，停止补交。')
        state=current[root]
        for key in state:
            if key not in ('local','remote','status'):e.require(state[key]==before[root][key],'目标仓库身份或规则已变化。')
        e.require(e.text_at(repo,'LICENSE')==e.CC and hashlib.sha256((repo/'LICENSE').read_bytes()).hexdigest()==proposal['file_sha256'],'许可文件内容已变化。')
        branch=state['branch'];message='fix(asset): recover LICENSE '+signature[:12]
        try:
            if state['local']==old:
                e.require(state['remote']==old and state['status'] in ('?? LICENSE\n','A  LICENSE\n'),'提交前状态已变化，停止。')
                e.git(repo,'add','--','LICENSE')
                e.git(repo,'commit','-m',message)
            head=e.git(repo,'rev-parse','HEAD').stdout.strip()
            e.require(e.git(repo,'rev-parse','HEAD^').stdout.strip()==old,'修复提交父版本不匹配。')
            e.require(e.git(repo,'log','-1','--format=%s').stdout.strip()==message,'修复提交身份不匹配。')
            e.require(e.git(repo,'diff','--name-status',old,head).stdout.strip()=='A\tLICENSE','修复提交包含额外文件，停止推送。')
            e.require(not e.git(repo,'status','--porcelain').stdout,'修复后有额外改动，停止推送。')
            record.update(status='committed',commit=head);e.save(record_path,record)
            remote=provider.head(root)
            e.require(remote in (old,head),'远端已变化，不会覆盖或强制推送。')
            if remote!=head:e.git(repo,'push','origin','HEAD:refs/heads/'+branch)
            e.require(provider.head(root)==head,'推送结果暂时无法确认，请继续核对。')
            record.update(status='pushed',finished_at=e.now());record['events'].append({'at':e.now(),'status':'pushed','commit':head});e.save(record_path,record)
        except Exception as exc:
            record['events'].append({'at':e.now(),'status':'paused','reason':str(exc)});e.save(record_path,record)
            raise
    return record
