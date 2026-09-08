#!/usr/bin/env python3
"""Loopback-only UI for the registered Asset Cloud executor. No extra web framework."""
from __future__ import annotations
import argparse
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import webbrowser
import yaml

HERE=Path(__file__).resolve().parent
ASSET=HERE.parents[2]
spec=importlib.util.spec_from_file_location('asset_bridge',ASSET/'asset-entry.py')
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
bridge.load_contract()
sys.path.insert(0,str(ASSET/'skills/second-brain-init/scripts'))
import engine as e
sys.path.insert(0,str(HERE))
import survey
from github_login import Login
VERSION='0.5.0'
ROLES={'platform':('应用云','以后放应用项目；本次仅建立骨架。'),'toolkit':('工具箱','放可重复使用的程序工具。'),'example':('实验室','放实验与示例程序。'),'context':('工作背景','放开展工作前应了解的背景和约定。'),'journal':('工作日志','记录工作过程和讨论。'),'intention':('工作意图','记录为什么做、目标和产品设想。')}
A='资产章程第五至七条'
B='原始流程：标准流程'

def read(path, default=None):
    return e.read_json(path) if path.is_file() else default

def cleaned_error(exc):
    return str(exc)[:1500] or '操作中断，请保留记录后检查。'

def naming_rules():
    specification=e.read_yaml(e.SPEC)
    return {'pattern':e.SLUG.pattern,'reserved':specification['reserved_names'],
            'limits':{'chinese_name':80,'short_name':60,'english_name':99-max(len(v['repo'].replace('{english_name}','')) for v in specification['asset_types'].values() if '{english_name}' in v['repo']),'overview':4000,'boundary':4000,'neighbors':4000},
            'source':specification['sources']['bylaw']}

def validate_request(payload):
    rules=naming_rules();errors={};domain={}
    labels={'chinese_name':'领域中文名','short_name':'领域简称','english_name':'领域英文全名','overview':'领域用途','boundary':'收录范围','neighbors':'相邻领域分工'}
    for key,limit in rules['limits'].items():
        value=payload.get(key,'')
        if not isinstance(value,str):
            errors[key]='请填写文字。';domain[key]='';continue
        domain[key]=value.strip();value=domain[key]
        if not value:errors[key]='请填写'+labels[key]+'。'
        elif len(value)>limit:errors[key]=f'本工具此项最多填写 {limit} 个字符。'
        elif '\x00' in value or '\r' in value:errors[key]='请删除不可识别的控制字符。'
        elif key=='chinese_name' and '\n' in value:errors[key]='名称请写在同一行。'
        elif key in ('short_name','english_name'):
            if not e.SLUG.fullmatch(value):errors[key]='只用小写英文字母、数字和单个连字符；不能有空格、中文或下划线，也不能以连字符开头或结尾。例如：sample-engineering。'
            elif key=='short_name' and value in rules['reserved']:errors[key]='这个简称已用于资产类别，会与总目录重名；请换成领域简称，例如 sample。'
    return {'valid':not errors,'errors':errors,'domain':domain}

class Studio:
    def __init__(self,storage,enable_github=False,test_mode=False):
        self.storage=Path(storage).resolve();self.storage.mkdir(parents=True,exist_ok=True)
        self.enable_github=enable_github;self.test_mode=test_mode
        self.guard=threading.RLock();self.active=set();self.login=Login()
        # Surviving records do not imply that a worker is still running after a restart.
        for folder in self.storage.glob('runs/*'):
            meta=read(folder/'ui.json',{})
            if meta.get('status') in ('planning','running','verifying'):
                meta.update(status='paused',error='上次窗口服务已结束。请查看已完成步骤，再尝试继续；有残留锁时请维护者检查。')
                e.save(folder/'ui.json',meta)
        for folder in self.storage.glob('surveys/*'):
            meta=read(folder/'ui.json',{})
            if meta.get('status')=='surveying':self.set_meta(folder,status='paused',error='上次调查中断，请重新查询。')

    def start_survey(self,payload):
        validation=validate_request(payload);e.require(validation['valid'],'请先填写有效需求，再查询本次目标。')
        org=e.github_owner(payload.get('survey_organization','quanttide').strip())
        root=e.slug(payload.get('survey_root','quanttide').strip())
        domain=validation['domain'];specification=e.read_yaml(e.SPEC)
        mapping=e.asset_map(domain,specification)
        names=[root,'quanttide-'+domain['short_name']]+[mapping[k]['repo'] for k in specification['initial_assets']]
        key=secrets.token_hex(8);folder=self.storage/'surveys'/key;folder.mkdir(parents=True)
        self.set_meta(folder,id=key,status='surveying',organization=org,domain=domain)
        def task():
            report=survey.inspect(org,names,specification['sources']['bylaw'],root=root)
            e.save(folder/'report.json',report);self.set_meta(folder,status='completed')
        self.spawn(folder,task)
        return {'id':key}

    def survey_view(self,key):
        e.require(bool(re.fullmatch('[a-f0-9]{16}',key)),'调查编号无效。')
        folder=self.storage/'surveys'/key
        e.require(folder.is_dir() and not folder.is_symlink(),'找不到调查记录。')
        return dict(read(folder/'ui.json'),report=read(folder/'report.json'))

    def folder(self,key):
        e.require(bool(re.fullmatch('[a-f0-9]{16}',key)), '运行编号无效。')
        folder=self.storage/'runs'/key
        e.require(folder.is_dir() and not folder.is_symlink(),'找不到这份运行记录。')
        return folder

    def set_meta(self,folder,**values):
        with self.guard:
            meta=read(folder/'ui.json',{});meta.update(values);e.save(folder/'ui.json',meta)

    def spawn(self,folder,fn):
        key=folder.name
        with self.guard:
            e.require(key not in self.active,'这份任务正在处理中，请等待。')
            self.active.add(key)
        def worker():
            try:fn()
            except Exception as exc:self.set_meta(folder,status='paused',error=cleaned_error(exc))
            finally:
                with self.guard:self.active.discard(key)
        threading.Thread(target=worker,daemon=True).start()

    def create(self,payload):
        provider=payload.get('provider','local')
        e.require(provider in ('local','github'),'请选择本地或 GitHub。')
        e.require(provider=='local' or self.enable_github,'真实 GitHub 入口尚未由维护者启用。')
        validation=validate_request(payload)
        e.require(validation['valid'],'；'.join(validation['errors'].values()))
        domain=validation['domain']
        root=e.slug(payload.get('root_repo','quanttide').strip())
        mode=payload.get('root_mode','existing')
        e.require(mode in ('new','existing'),'请选择新建或使用已有总入口。')
        cfg={'schema_version':1,'scenario':'new-domain','domain':domain,'register_root':True,'root_repo':root,'new_repositories_only':True,'new_root':mode=='new'}
        e.validate_config(cfg,e.read_yaml(e.SPEC))
        org=e.github_owner(payload.get('organization','quanttide').strip() or 'quanttide')
        if provider=='github':
            e.require(self.login.status()['status']!='waiting','请先完成或取消正在进行的 GitHub 登录。')
            identity=e.github_identity(org)
            e.require(identity['owner_type']=='User' and identity['owner_id']==identity['id'], '此网页版本只开放当前登录者的个人测试仓库；组织写入另行联调。')
            org=identity['owner']
        key=secrets.token_hex(8);folder=self.storage/'runs'/key;folder.mkdir(parents=True)
        # Fresh checkout per run avoids stale local clones; GitHub runs reuse the selected remote root.
        work=self.storage/'workspaces'/key
        (folder/'request.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding='utf-8')
        self.set_meta(folder,id=key,title=domain['chinese_name'],provider=provider,organization=org,root_repo=root,root_mode=mode,status='planning',created_at=e.now(),error=None)
        def task():
            if provider=='github':
                specification=e.read_yaml(e.SPEC);mapping=e.asset_map(domain,specification)
                self.set_meta(folder,phase='正在读取目标仓库与章程，尚未写入 GitHub。')
                observation=survey.inspect(org,[root,'quanttide-'+domain['short_name']]+[mapping[k]['repo'] for k in specification['initial_assets']],specification['sources']['bylaw'],root=root)
                e.save(folder/'survey.json',observation)
                e.require(observation['rules']['status']=='same','在线章程变化或无法核对；请维护者核对规则，不能继续。')
                for row in observation['repositories']:
                    if row['name']==root and mode=='existing':e.require(bool(row.get('commit')),'未找到可读取的总入口；第一次请选“新建测试入口”，已有入口请检查名称与权限。')
                    elif row['status']=='exists':raise e.WorkflowError('新建目标 '+row['name']+' 已存在；请改名或单独调查维护。')
                    else:e.require(row.get('http_status')==404,'目标查询失败，不能当作可新建：'+row['name'])
            self.set_meta(folder,phase='正在核对账号、已有规则和仓库版本，生成待确认清单。')
            e.make_plan(folder/'request.yaml',work,folder,provider,org)
            planned=e.load_plan(folder)
            if provider=='github':
                root_row=next(r for r in observation['repositories'] if r['name']==root)
                e.require(root_row.get('commit')==planned['before'][root]['remote'],'调查期间总入口已变化，请重新规划。')
            self.set_meta(folder,status='review')
        self.spawn(folder,task)
        return {'id':key}

    def execute(self,key,payload,resume=False):
        folder=self.folder(key)
        with self.guard:
            meta=read(folder/'ui.json');e.require(key not in self.active,'正在执行，请勿重复点击。')
            e.require(meta['status'] in (('paused',) if resume else ('review',)),'当前状态不允许此操作。')
            plan=e.load_plan(folder)
            e.require(payload.get('plan_id')==plan['id'],'页面中的计划已过时，请重新打开。')
            if plan['provider']=='github':
                e.check_identity(plan)
                e.require(not any(read(p/'ui.json',{}).get('provider')=='github' and p.name in self.active for p in (self.storage/'runs').glob('*')), '已有 GitHub 任务执行中，请完成后再提交其他任务。')
            if not resume:
                e.require(payload.get('confirmed') is True,'请先勾选已阅读本次创建范围。')
                reviewer=payload.get('reviewer','').strip();e.require(0<len(reviewer)<=80,'请填写审阅者姓名（最多 80 字）。')
                if plan['provider']=='github':
                    e.require(payload.get('github_confirmation')==plan['organization'],'请输入目标个人账号名以确认公开 GitHub 写入范围。')
                e.approve(folder,reviewer,plan['id'],simulated=self.test_mode)
            else:e.require((folder/'approval-record.json').is_file(),'未确认的计划不能恢复，请重新创建计划。')
            self.set_meta(folder,status='running',error=None)
            def task():
                try:
                    check={'started_at':e.now(),'plan_id':plan['id'],'provider':plan['provider'],'scope':plan['names'],'status':'checking'}
                    try:
                        e.check_identity(plan)
                        current=e.snapshot(e.Provider(plan['workspace'],plan['provider'],plan['organization']),plan['names'])
                        expected=read(folder/'execution-log.json',{}).get('checkpoint',plan['before'])
                        check.update(current=current,changed=[name for name in plan['names'] if current[name]!=expected.get(name)])
                        e.require(not check['changed'],'仓库状态已变化：'+', '.join(check['changed'])+'；请重新调查并生成方案。')
                        if plan['provider']=='github':
                            adopted=plan['sources']['bylaw'];owner,repo=adopted['repository'].split('/')
                            latest=survey.text_file(owner,repo,adopted['path'])
                            baseline=read(folder/'survey.json',{}).get('rules',{}).get('adopted_file',{})
                            e.require(latest['status']=='ok' and latest.get('sha')==baseline.get('sha'),'执行前章程变化或无法核对，停止。')
                        check['status']='passed'
                    except Exception as exc:
                        check.update(status='blocked',reason=cleaned_error(exc));raise
                    finally:
                        check['finished_at']=e.now();e.save(folder/'pre-execution-check.json',check)
                    e.apply(folder)
                except e.WorkflowError:
                    if (folder/'verification-report.json').is_file():self.build_report(folder)
                    raise
                self.build_report(folder)
                self.set_meta(folder,status='completed',error=None)
            self.spawn(folder,task)
        return {'id':key}

    def verify(self,key):
        folder=self.folder(key)
        with self.guard:
            meta=read(folder/'ui.json');e.require(meta['status'] in ('completed','paused'),'当前不能重新检查。')
            e.require(key not in self.active,'正在处理中。')
            self.set_meta(folder,status='verifying',error=None)
            def task():
                plan=e.load_plan(folder);r=e.verify(plan,read(folder/'approval-record.json'))
                e.save(folder/'verification-report.json',r);self.build_report(folder)
                self.set_meta(folder,status='completed' if r['status']=='passed' else 'paused',error=None if r['status']=='passed' else '有检查未通过，请查看报告中的实际结果。')
            self.spawn(folder,task)
        return {'id':key}

    def build_report(self,folder):
        plan=e.load_plan(folder);raw=read(folder/'verification-report.json',{});provider=e.Provider(plan['workspace'],plan['provider'],plan['organization'])
        root_name=plan['config']['root_repo']
        d=plan['config']['domain'];target='quanttide-'+d['short_name'];repo=provider.repo(target)
        specification=e.read_yaml(e.SPEC);mapping=e.asset_map(d,specification)
        items=[]
        def item(key,title,standard,actual,passed,source,documents=None):
            items.append(dict(key=key,title=title,standard=standard,actual=actual,status='passed' if passed else 'failed',source=source,documents=documents or []))
        exists=[name for name in plan['names'] if provider.repo(name).is_dir()]
        item('repositories','仓库是否齐全',f'本计划涉及 {len(plan["names"])} 个仓库，包括总入口。',f'实际找到 {len(exists)} 个：'+ '、'.join(exists),len(exists)==len(plan['names']),B)
        sections=e.text_at(repo,'README.md')
        checks=['概述','领域边界','相邻领域分工','资产目录','许可']
        present=[x for x in checks if '## '+x in sections]
        item('readme','领域首页是否完整','说明用途、边界、相邻分工、资料入口和许可。','找到章节：'+'、'.join(present),len(present)==len(checks),B,[f'{target}/README.md'])
        paths=specification['domain_directories'];missing=[p for p in paths if not e.safe_path(repo,p).is_dir()]
        item('directories','资料是否有统一位置','平台、工具、示例，加上 11 类事实资料和 6 类方法资料，共 20 类坐标。','全部 20 类坐标存在。' if not missing else '缺少：'+'、'.join(missing),not missing,'资产章程第七条',[f'{target}/README.md'])
        details=raw.get('details',[]);mounts=[x for x in details if isinstance(x.get('check'),dict) and x['check'].get('kind')=='mount']
        item('mounts','仓库连接是否正确','6 个配套仓库连接到领域，领域连接到总入口；地址和版本指针均正确。',f'{sum(bool(x["passed"]) for x in mounts)}/{len(mounts)} 项连接检查通过。',len(mounts)==7 and all(x['passed'] for x in mounts),B,[f'{target}/.gitmodules',root_name+'/.gitmodules'])
        root=provider.repo(root_name);root_text=e.text_at(root,'README.md');index=e.text_at(root,'domains/README.md')
        registered='domains/'+target in e.modules(root)
        idx_ok=all('## '+x in index for x in ['目录结构','领域清单','领域项目']) and target in index and target in root_text
        item('root','从总入口能否找到新领域','总首页与领域索引列出本领域，根仓库存在领域连接。','已找到 '+target if registered and idx_ok else '总入口登记或索引缺失。',registered and idx_ok,B,[root_name+'/README.md',root_name+'/domains/README.md'])
        lic=e.text_at(repo,'LICENSE');log=e.text_at(repo,'CHANGELOG.md')
        created=not plan['before'][target]['remote']
        lic_ok=bool(lic) and ('CC BY 4.0' in lic if created else True)
        item('documents','许可和初始化记录是否存在','全新领域采用 CC BY 4.0，并记录 0.1.0 初始化与待发布变更；已有仓库保留原许可。','许可：'+('已找到' if lic else '缺失')+'；初始化：'+('已找到' if '[0.1.0]' in log else '缺失'),lic_ok and '[0.1.0]' in log and '[Unreleased]' in log,'原始流程：文档与许可证',[f'{target}/LICENSE',f'{target}/CHANGELOG.md'])
        repos=[x for x in details if x.get('check')=='repository']
        item('synchronized','是否还有未保存或不同步的修改','工作仓库干净，本地与对应远端的提交一致。',f'{sum(bool(x["passed"]) for x in repos)}/{len(repos)} 个仓库通过检查。',len(repos)==len(plan['names']) and all(x['passed'] for x in repos),B)
        failed=[x for x in details if not x.get('passed')]
        signature=e.digest({'plan_id':plan['id'],'rows':items,'files':{x: e.text_at(repo,x) for x in ['README.md','LICENSE','CHANGELOG.md','.gitmodules']},'heads':{name:e.git(provider.repo(name),'rev-parse','HEAD',check=False).stdout for name in exists}})
        result={'checked_at':raw.get('at',e.now()),'signature':signature,'provider':plan['provider'],'rows':items,'technical_passed':all(x['status']=='passed' for x in items) and raw.get('status')=='passed','failures':failed,'repositories':[{'name':x['repo'],'commit':x.get('commit'),'checked_at':x.get('checked_at'),'url':x.get('url'),'passed':x['passed']} for x in repos],'account':plan.get('github_identity'),'source_versions':plan['sources'],'simulated':self.test_mode or bool(read(folder/'approval-record.json',{}).get('simulated')),'scope':'本地 Git 流程；未操作真实 GitHub。' if plan['provider']=='local' else '已使用真实 GitHub；逐项结果以执行日志为准。'}
        e.save(folder/'ui-report.json',result)
        return result

    def acceptance(self,key,payload):
        folder=self.folder(key)
        with self.guard:
            e.require(key not in self.active,'正在处理中，请完成后再记录验收。')
            e.require(read(folder/'ui.json',{}).get('status')=='completed','任务已暂停或尚未完成，请先重新检查后再记录验收。')
            report=read(folder/'ui-report.json');e.require(report,'尚未生成检查报告。')
            e.require(payload.get('signature')==report['signature'],'报告已更新，请重新检查。')
            reviewer=payload.get('reviewer','').strip();e.require(0<len(reviewer)<=80,'请填写验收人姓名。')
            choices={k:payload.get(k) for k in ['meaning','navigation','usability']}
            e.require(all(x in ('passed','improve') for x in choices.values()),'请逐项选择内容、导航和使用体验的意见。')
            notes=payload.get('notes','').strip();e.require(len(notes)<=4000,'意见最多 4000 字。')
            e.require(all(x=='passed' for x in choices.values()) or notes,'选择需要改进时，请说明遇到的问题。')
            record=dict(reviewer=reviewer,at=e.now(),signature=report['signature'],simulated=self.test_mode,choices=choices,notes=notes,overall='passed' if report['technical_passed'] and all(x=='passed' for x in choices.values()) else 'needs-improvement')
            e.save(folder/'human-acceptance.json',record)
            return record

    def view(self,key):
        folder=self.folder(key);meta=read(folder/'ui.json',{});plan=read(folder/'execution-plan.json');log=read(folder/'execution-log.json',{})
        result=dict(meta,completed=len(log.get('completed',[])),total=len(plan['operations']) if plan else 0,can_resume=bool(plan and (folder/'approval-record.json').is_file()),storage=str(folder),pre_execution=read(folder/'pre-execution-check.json'),survey=read(folder/'survey.json'),current_operation=log.get('current'),events=log.get('events',[]))
        if plan:
            root_name=plan['config']['root_repo']
            d=plan['config']['domain'];m=e.asset_map(d,e.read_yaml(e.SPEC))
            expected={'quanttide-'+d['short_name'],root_name}|{m[k]['repo'] for k in e.read_yaml(e.SPEC)['initial_assets']}
            result['preflight']=[
                {'status':'passed' if validate_request(d)['valid'] else 'failed','title':'填写与命名格式','detail':'必填内容、字符格式、长度及简称冲突检查。依据：本工具输入规则。'},
                {'status':'passed' if expected==set(plan['names']) else 'failed','title':'仓库名称与创建范围','detail':'领域短名生成领域仓库；英文全名生成资料仓库后缀。依据：资产章程第五、六条及原始新建流程。'},
                {'status':'manual','title':'用途、英文含义与领域边界','detail':'请阅读下方需求摘要，确认准确表达你的需求；程序不能替你判断。'},
                {'status':'manual','title':'本次操作位置','detail':'本机独立测试空间，不写入 GitHub。' if plan['provider']=='local' else '将写入 '+plan['organization']+' 的公开 GitHub 仓库；请核对账号、公开属性与已有规则。'}]
            result['plan']={'id':plan['id'],'domain':d,'root_repo':root_name,'root_mode':'new' if plan['config'].get('new_root') else 'existing','provider':plan['provider'],'workspace':plan['workspace'],'repositories':[dict(name='quanttide-'+d['short_name'],role='领域首页',purpose='本领域的介绍和资料导航。',path='domains/quanttide-'+d['short_name'])]+[dict(name=m[k]['repo'],role=ROLES[k][0],purpose=ROLES[k][1],path=m[k]['path']) for k in ROLES]+[dict(name=root_name,role='总入口',purpose='从这里查找各领域。',path='总入口')],'inspection':plan['inspection']}
        if log.get('events'):result['last_operation']=log['events'][-1].get('kind')
        if plan:
            result['observation']={'at':plan['created_at'],'provider':plan['provider'],'organization':plan['organization'],'scope':'仅本次计划涉及的仓库，非持续监控。','rules':plan['sources']['bylaw'],'spec_sha256':plan['spec_sha256']}
            for row in result['plan']['repositories']:
                before=plan['before'][row['name']]
                row['observed_commit']=before['remote']
                row['action']='拟更新已有总入口' if before.get('remote_exists') and row['name']==root_name else '冲突：新建禁止复用' if before.get('remote_exists') else '拟新建本地仓库' if plan['provider']=='local' else '未发现可见仓库；仅尝试新建，重名时停止'
                row['writes']=[op['kind'] for op in plan['operations'] if op['repo']==row['name']]
        result['report']=read(folder/'ui-report.json')
        acceptance=read(folder/'human-acceptance.json')
        if acceptance and result['report']:acceptance['stale']=acceptance['signature']!=result['report']['signature']
        result['acceptance']=acceptance
        return result

    def document(self,key,name):
        folder=self.folder(key);plan=e.load_plan(folder)
        repo,sep,relative=name.partition('/')
        allowed={'README.md','LICENSE','CHANGELOG.md','.gitmodules','domains/README.md'}
        e.require(repo in plan['names'] and relative in allowed,'只能查看本次计划中的说明和登记文件。')
        path=e.safe_path(e.Provider(plan['workspace'],plan['provider'],plan['organization']).repo(repo),relative)
        e.require(path.is_file() and path.stat().st_size<=1_000_000,'文件不存在或过大。')
        return {'title':name,'text':path.read_text(encoding='utf-8')}

    def export(self,key):
        view=self.view(key);report=view.get('report');e.require(report,'尚无报告可导出。')
        esc=lambda x:html.escape(str(x))
        rows=''.join('<tr><td>'+esc(x['title'])+'</td><td>'+esc(x['standard'])+'</td><td>'+esc(x['actual'])+'</td><td>'+('通过' if x['status']=='passed' else '未通过')+'</td><td>'+esc(x['source'])+'</td></tr>' for x in report['rows'])
        acceptance=view.get('acceptance')
        check=view.get('pre_execution')
        execution_evidence=('执行前复核：'+({'passed':'通过','blocked':'已阻止执行'}.get(check['status'],check['status']))+'；开始：'+check['started_at']+'；结束：'+check['finished_at']+'；'+check.get('reason','本次涉及 '+str(len(check['scope']))+' 个仓库。')) if check else '此历史记录未保存执行前复核证据。'
        github_links=''
        if report['provider']=='github':
            github_links='<h2>GitHub 实际产物</h2>'+''.join('<p><a href="'+esc(x['url'])+'">'+esc(x['name'])+'</a>；提交：'+esc(x.get('commit') or '未取得')+'；查询：'+esc(x.get('checked_at') or '未取得')+'</p>' for x in report.get('repositories',[]) if x.get('url'))
        human='尚未完成人工验收。'
        if acceptance:
            labels={'meaning':'领域内容','navigation':'资料导航','usability':'使用体验'}
            human=('模拟反馈，不能作为真实用户验收。' if acceptance['simulated'] else '验收人：'+acceptance['reviewer'])+'；'+('旧报告意见，需重新确认。' if acceptance['stale'] else '；'.join(labels[k]+'：'+('通过' if v=='passed' else '需改进') for k,v in acceptance['choices'].items()))+'；意见：'+acceptance['notes']
        return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>第二大脑验收报告</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:40px auto;padding:20px;color:#18352f}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd9d2;padding:12px;text-align:left;overflow-wrap:anywhere}h1{font-size:28px}@media print{body{margin:0}}</style><h1>'+esc(view['title'])+' · 验收报告</h1><p>检查时间：'+esc(report['checked_at'])+'</p><p>任务状态：'+esc({'completed':'已完成','paused':'已暂停','verifying':'检查中'}.get(view['status'],view['status']))+'</p><p>'+esc(report['scope'])+'</p><p>确认方式：'+('模拟确认（自动化测试）' if report['simulated'] else '已记录审阅者确认')+'</p><table><tr><th>检查项目</th><th>标准</th><th>实际结果</th><th>状态</th><th>依据</th></tr>'+rows+'</table>'+github_links+'<h2>执行前复核</h2><p>'+esc(execution_evidence)+'</p><h2>人工验收</h2><p>'+esc(human)+'</p><h2>验证边界</h2><p>配套仓库是初始骨架，不代表业务应用已开发。技术检查通过不代表领域内容准确。此工具尚未作为资产云在线页面部署。</p></html>'

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,data,content_type='application/json; charset=utf-8',download=False):
        raw=json.dumps(data,ensure_ascii=False).encode() if isinstance(data,(dict,list)) else data.encode() if isinstance(data,str) else data
        self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if download:self.send_header('Content-Disposition','attachment; filename="second-brain-acceptance.html"')
        self.end_headers();self.wfile.write(raw)
    def guard(self):
        expected='127.0.0.1:'+str(self.server.server_port)
        e.require(self.headers.get('Host')==expected,'请求地址无效，请使用启动器打开的窗口。')
        origin=self.headers.get('Origin')
        e.require(not origin or origin=='http://'+expected,'不接受其他网页发起的请求。')
        e.require(secrets.compare_digest(self.headers.get('X-Session-Token',''),self.server.token),'窗口会话已失效，请从启动器重新打开。')
    def do_GET(self):
        try:
            path=urlsplit(self.path).path
            if path in ('/','/app.js','/style.css'):
                name={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]
                kind={'/':'text/html','/app.js':'text/javascript','/style.css':'text/css'}[path]
                return self.send(200,(HERE/'static'/name).read_bytes(),kind+'; charset=utf-8')
            self.guard();studio=self.server.studio
            if path=='/api/github/login':return self.send(200,studio.login.status())
            if path=='/api/info':return self.send(200,{'version':VERSION,'storage':str(studio.storage),'github_enabled':studio.enable_github,'simulated':studio.test_mode,'git':shutil.which('git') is not None})
            if path=='/api/runs':return self.send(200,sorted([read(p,{}) for p in studio.storage.glob('runs/*/ui.json')],key=lambda x:x.get('created_at',''),reverse=True))
            if path=='/api/naming-rules':return self.send(200,naming_rules())
            survey_match=re.fullmatch('/api/surveys/([a-f0-9]{16})',path)
            if survey_match:return self.send(200,studio.survey_view(survey_match[1]))
            m=re.fullmatch('/api/runs/([a-f0-9]{16})(/export)?',path)
            if m:return self.send(200,studio.export(m[1]),'text/html; charset=utf-8',True) if m[2] else self.send(200,studio.view(m[1]))
            self.send(404,{'error':'找不到此页面。'})
        except Exception as exc:self.send(400,{'error':cleaned_error(exc)})
    def do_POST(self):
        try:
            self.guard();size=int(self.headers.get('Content-Length','0'));e.require(0<size<=32768,'请求内容过大或为空。')
            payload=json.loads(self.rfile.read(size));e.require(isinstance(payload,dict),'请求格式错误。')
            path=urlsplit(self.path).path;studio=self.server.studio
            if path.startswith('/api/github/'):
                e.require(studio.enable_github and not studio.test_mode,'当前未启用真实账号连接。')
                e.require(not studio.active,'请等待当前任务完成，再操作登录。')
                if path=='/api/github/check':return self.send(200,studio.login.inspect())
                if path=='/api/github/login':return self.send(200,studio.login.start())
                if path=='/api/github/cancel':return self.send(200,studio.login.cancel())
            if path=='/api/plan':return self.send(200,studio.create(payload))
            if path=='/api/survey':return self.send(200,studio.start_survey(payload))
            m=re.fullmatch('/api/runs/([a-f0-9]{16})/(execute|resume|verify|acceptance|document)',path)
            e.require(m,'不支持此操作。');key,action=m.groups()
            if action in ('execute','resume'):data=studio.execute(key,payload,action=='resume')
            elif action=='verify':data=studio.verify(key)
            elif action=='acceptance':data=studio.acceptance(key,payload)
            else:data=studio.document(key,payload.get('name',''))
            self.send(200,data)
        except Exception as exc:self.send(400,{'error':cleaned_error(exc)})

def main():
    p=argparse.ArgumentParser(description='第二大脑中文创建向导，仅在本机运行')
    p.add_argument('--storage',type=Path,default=Path.home()/'QuanttideSecondBrain')
    p.add_argument('--port',type=int,default=0);p.add_argument('--no-browser',action='store_true')
    p.add_argument('--enable-github',action='store_true',help='兼容旧启动参数；个人 GitHub 入口默认可见')
    p.add_argument('--local-only',action='store_true',help='关闭真实 GitHub 入口')
    p.add_argument('--test-mode',action='store_true',help='明确标注自动化试用反馈为模拟')
    args=p.parse_args();e.require(not(args.test_mode and args.enable_github),'自动测试模式不能启用真实 GitHub。')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.token=secrets.token_urlsafe(32);server.studio=Studio(args.storage,not(args.local_only or args.test_mode),args.test_mode)
    url=f'http://127.0.0.1:{server.server_port}/#'+server.token
    print('第二大脑创建向导已启动。关闭此窗口将停止服务。',flush=True)
    print(url,flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.studio.login.cancel();server.server_close()

if __name__=='__main__':main()
