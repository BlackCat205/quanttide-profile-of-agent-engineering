#!/usr/bin/env python3
"""Confirmed, resumable Git workflow. No shell command strings are evaluated."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import threading
from datetime import datetime, timezone
from urllib.parse import quote

import yaml

VERSION = '0.4.3'
COMPATIBLE_ENGINE_SHA256S = {
    # 0.4.1: execution operations and generated content are unchanged. 0.4.2
    # replaces redundant Git read probes with authenticated GitHub API reads
    # and adds exact local-phase reconciliation for interrupted runs.
    'b186fe8ed1b59b4fbb2f3636870531f6e41ca6cb98e8fb1306719fa115ce1258',
    # 0.4.2: same execution contract; 0.4.3 hardens local record writes and
    # makes optional progress/request observers non-blocking.
    '3269648a78a0547c79390a3ef18662fcd079434c878fccdcab0bf1a56b36e6ad',
}
verification_observer = threading.local()
request_observer = threading.local()
SKILL = Path(__file__).resolve().parents[1]
SPEC = SKILL / 'assets' / 'specification.yaml'
SLUG = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
CC = 'Creative Commons Attribution 4.0 International (CC BY 4.0)\n\nThis work is licensed under CC BY 4.0.\nhttps://creativecommons.org/licenses/by/4.0/legalcode\n'
APACHE = 'Apache License, Version 2.0\n\nLicensed under the Apache License, Version 2.0 (the "License");\nyou may not use this work except in compliance with the License.\nYou may obtain a copy of the License at\n\n    https://www.apache.org/licenses/LICENSE-2.0\n\nUnless required by applicable law or agreed to in writing, software\ndistributed under the License is distributed on an "AS IS" BASIS,\nWITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\nSee the License for the specific language governing permissions and\nlimitations under the License.\n'

class WorkflowError(Exception):
    pass

class RemoteReadError(WorkflowError):
    """Remote state was not observed; this is not evidence of invalid assets."""
    pass

def require(condition, message):
    if not condition:
        raise WorkflowError(message)

def now():
    return datetime.now(timezone.utc).isoformat()

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

_save_locks_guard=threading.Lock()
_save_locks={}

def _save_lock(path):
    key=str(Path(path).resolve())
    with _save_locks_guard:
        return _save_locks.setdefault(key,threading.RLock())

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    with _save_lock(path):
        temporary=None
        try:
            with tempfile.NamedTemporaryFile('w',encoding='utf-8',newline='\n',delete=False,
                                             dir=path.parent,prefix='.'+path.name+'.',suffix='.tmp') as handle:
                temporary=Path(handle.name);handle.write(payload);handle.flush();os.fsync(handle.fileno())
            for attempt in range(8):
                try:
                    os.replace(temporary,path)
                    temporary=None
                    return
                except PermissionError:
                    if attempt==7:raise
                    time.sleep(min(.05*(2**attempt),.4))
        finally:
            if temporary is not None:
                try:temporary.unlink(missing_ok=True)
                except OSError:pass

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def read_yaml(path):
    value = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    require(isinstance(value, dict), '配置必须为 YAML 对象。')
    return value

def slug(value):
    require(isinstance(value, str) and len(value) < 100 and bool(SLUG.fullmatch(value)), f'非法名称：{value!r}')
    return value

def github_owner(value):
    require(isinstance(value,str) and bool(re.fullmatch(r'[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*',value)) and len(value)<=39, 'GitHub 账号名只能包含字母、数字和单个连字符，最多 39 字符。')
    return value

def github_identity(owner):
    owner=github_owner(owner)
    user=json.loads(command(['gh','api','user']).stdout)
    target=user if user['login'].lower()==owner.lower() else json.loads(command(['gh','api','users/'+owner]).stdout)
    require(target['type']=='Organization' or target['id']==user['id'], '只能创建在当前登录个人账号或获授权组织下，不能写入其他个人账号。')
    return {'login':user['login'],'id':user['id'],'owner':target['login'],'owner_id':target['id'],'owner_type':target['type']}

def check_identity(plan):
    if plan['provider']=='github':
        require(github_identity(plan['organization'])==plan.get('github_identity'), '登录账号或目标归属已变化，请重新登录并生成方案。')

def safe_path(base, relative):
    require(isinstance(relative, str) and '\\' not in relative, '路径须使用 / 分隔。')
    p = PurePosixPath(relative)
    require(not p.is_absolute() and all(s not in ('..', '.', '.git') for s in p.parts) and bool(p.parts), '路径不能越界或包含 .git。')
    target = Path(base).joinpath(*p.parts)
    current = Path(base)
    require(not current.is_symlink(), '工作区不能是符号链接。')
    for part in p.parts:
        current = current / part
        require(not current.is_symlink(), f'拒绝符号链接路径：{relative}')
    require(target.resolve().is_relative_to(Path(base).resolve()), '路径超出工作区。')
    return target

def command_kind(argv):
    args=list(map(str,argv));i=1
    while i<len(args) and args[i].startswith('-'):
        i+=2 if args[i] in ('-c','-C','--git-dir','--work-tree') else 1
    return args[i] if i<len(args) else ''

def notify_observer(callback,event):
    """Observers are diagnostic only and must never change workflow outcome."""
    if callback:
        try:callback(event)
        except Exception:pass

def command(argv, cwd=None, check=True):
    args=list(map(str,argv));kind=command_kind(args)
    target=next((m.group(1).removesuffix('.git') for arg in args if (m:=re.fullmatch(r'https://github.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?:/)?',arg))),None)
    if args[0]=='gh':
        endpoint=next((arg for arg in args if re.fullmatch(r'repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./-]+)?',arg)),None)
        target='/'.join(endpoint.split('/')[1:3]) if endpoint else None
    target=target or getattr(request_observer,'target',None)
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never', GH_HOST='github.com', GH_PROMPT_DISABLED='1')
    count=int(env.get('GIT_CONFIG_COUNT','0'))
    if args[0]=='git':
        for key,value in [('credential.https://github.com.helper',''),('credential.https://github.com.helper','!gh auth git-credential')]:
            env['GIT_CONFIG_KEY_'+str(count)]=key;env['GIT_CONFIG_VALUE_'+str(count)]=value;count+=1
        env['GIT_CONFIG_COUNT']=str(count)
    gh_readonly=(args[0]=='gh' and kind=='api' and not any(
        value.upper() in ('POST','PUT','PATCH','DELETE')
        for flag,value in zip(args,args[1:]) if flag in ('--method','-X')))
    readonly=(args[0]=='git' and kind=='ls-remote') or gh_readonly
    attempts=3 if readonly else 1
    network=(args[0]=='gh' or kind in ('ls-remote','clone','fetch','push','submodule'))
    callback=getattr(request_observer,'callback',None)
    for attempt in range(attempts):
        compatibility=args[0]=='git' and bool(target) and (getattr(request_observer,'http1',False) or (readonly and attempt>0))
        run_env=dict(env)
        if compatibility:
            run_env['GIT_CONFIG_KEY_'+str(count)]='http.https://github.com/.version'
            run_env['GIT_CONFIG_VALUE_'+str(count)]='HTTP/1.1';run_env['GIT_CONFIG_COUNT']=str(count+1)
        event={'target':target,'operation':kind,'tool':args[0],'stage':getattr(request_observer,'stage',None),'attempt':attempt+1,'started_at':now(),'status':'running','protocol':'HTTP/1.1' if compatibility else 'default'}
        started=time.monotonic()
        if network:notify_observer(callback,dict(event))
        try:
            result=subprocess.run(args,cwd=cwd,env=run_env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=25 if readonly else 120)
        except FileNotFoundError:
            event.update(status='failed',category='missing-tool',finished_at=now())
            if network:notify_observer(callback,event)
            raise WorkflowError(f'找不到 {args[0]}，请按使用说明安装。') from None
        except subprocess.TimeoutExpired:
            result=subprocess.CompletedProcess(args,124,'','timed out')
        transient=any(x in result.stderr.lower() for x in ('could not resolve','failed to connect','connection was reset','connection reset','timed out','recv failure','http/2','remote end hung up','502','503','504'))
        category='connection' if transient else 'authorization' if any(x in result.stderr.lower() for x in ('authentication','permission denied','403','401')) else 'git-or-service'
        event.update(status='passed' if result.returncode==0 else 'failed',category=None if result.returncode==0 else category,exit_code=result.returncode,finished_at=now(),elapsed_seconds=round(time.monotonic()-started,3))
        if network:notify_observer(callback,event)
        if not result.returncode:
            if compatibility:request_observer.http1=True
            break
        if not(readonly and transient and attempt+1<attempts):break
        time.sleep(.3*(attempt+1))
    if check and result.returncode:
        reason={'connection':'连接中断或超时','authorization':'认证或权限受限','git-or-service':'读取或 Git 状态异常'}[category]
        raise (RemoteReadError if readonly else WorkflowError)(f'{target or "当前目标"} · {args[0]} {kind} 失败（退出码 {result.returncode}）：{reason}。本次已尝试 {attempt+1} 次。'+('暂时无法核验远端。' if readonly else '结果待核对，不会自动重复写入。'))
    return result

def git(path, *args, check=True):
    return command(['git', '-c', 'core.autocrlf=false', *args], cwd=path, check=check)

def text_at(repo, name):
    path = safe_path(repo, name)
    return path.read_text(encoding='utf-8') if path.is_file() else ''

def modules(repo):
    if not (repo / '.gitmodules').is_file():
        return {}
    raw = git(repo, 'config', '-f', '.gitmodules', '--get-regexp', r'^submodule\..*\.path$', check=False).stdout
    result = {}
    for line in raw.splitlines():
        key, path = line.split(' ', 1)
        url = git(repo, 'config', '-f', '.gitmodules', '--get', key[:-4]+'url').stdout.strip()
        result[path] = {'url': url, 'key': key[:-4]}
    return result

class Provider:
    def __init__(self, workspace, kind='local', organization='quanttide'):
        self.workspace = Path(workspace).resolve()
        self.kind = kind
        self.organization = github_owner(organization)
        require(kind in ('local', 'github'), 'provider 只能为 local 或 github。')

    def repo(self, name):
        return safe_path(self.workspace, 'repositories/' + slug(name))

    def remote(self, name):
        if self.kind == 'local':
            return str(safe_path(self.workspace, 'remotes/' + slug(name) + '.git'))
        return f'https://github.com/{self.organization}/{slug(name)}.git'

    def info(self, name):
        if self.kind == 'local':
            remote = Path(self.remote(name))
            return {'exists': remote.is_dir(), 'branch': 'main', 'visibility': 'local'}
        result = command(['gh', 'api', f'repos/{self.organization}/{slug(name)}'], check=False)
        if result.returncode:
            if '(HTTP 404)' not in result.stderr: raise RemoteReadError(f'无法读取 {name}；网络、登录或权限错误，不能当作仓库不存在。')
            return {'exists': False, 'branch': 'main', 'visibility': 'public'}
        data = json.loads(result.stdout)
        require(data.get('visibility') == 'public', '本插件仅处理公开第二大脑；检测到非公开仓库。')
        require(data['full_name'].lower()==(self.organization+'/'+name).lower(), '仓库重定向到其他位置，停止。')
        return {'exists': True, 'branch': data['default_branch'], 'visibility': 'public', 'id':data['id'], 'owner_id':data['owner']['id'], 'can_push':bool(data.get('permissions',{}).get('push')), 'archived':data.get('archived',False)}

    def head(self, name, info=None):
        info = self.info(name) if info is None else info
        if not info['exists']:
            return None
        if self.kind == 'github':
            endpoint = f'repos/{self.organization}/{slug(name)}/commits/'+quote(info['branch'], safe='')
            result=command(['gh','api',endpoint],check=False)
            if result.returncode:
                if '(HTTP 409)' in result.stderr:return None
                raise RemoteReadError(f'无法核对 {name} 的默认分支提交；网络、登录或权限错误。')
            data = json.loads(result.stdout)
            require(bool(data.get('sha')), f'{name} 的默认分支没有可核对的提交。')
            return data['sha']
        raw = command(['git', 'ls-remote', self.remote(name), 'refs/heads/'+info['branch']]).stdout.strip()
        return raw.split()[0] if raw else None

    def tag_exists(self, name, tag):
        if self.kind == 'github':
            endpoint=f'repos/{self.organization}/{slug(name)}/git/ref/tags/'+quote(tag,safe='')
            result=command(['gh','api',endpoint],check=False)
            if result.returncode:
                if '(HTTP 404)' in result.stderr:return False
                raise RemoteReadError(f'无法核对 {name} 的标签；网络、登录或权限错误。')
            return True
        return bool(command(['git','ls-remote',self.remote(name),'refs/tags/'+tag]).stdout)

    def ensure(self, name, allow_create, title, require_new=False):
        path = self.repo(name)
        info = self.info(name)
        resume_created = getattr(self, 'created_receipts', {}).get(name)
        if resume_created:
            require(info.get('id') == resume_created.get('repository_id') and info.get('owner_id') == resume_created.get('owner_id') and info['exists'], '中断仓库身份已变化，不能接续。')
            require_new = False
        require(not require_new or not info['exists'], f'新建目标 {name} 已存在；停止，不能自动复用。')
        if not info['exists']:
            require(allow_create, f'仓库 {name} 不存在。')
            if self.kind == 'local':
                remote = Path(self.remote(name))
                remote.parent.mkdir(parents=True, exist_ok=True)
                command(['git', 'init', '--bare', '--initial-branch=main', remote])
            else:
                identity=github_identity(self.organization)
                endpoint='user/repos' if identity['owner_type']=='User' else 'orgs/'+identity['owner']+'/repos'
                response=command(['gh', 'api', '--method', 'POST', endpoint, '-f', 'name='+name, '-F', 'private=false', '-F', 'auto_init=true'])
                data=json.loads(response.stdout)
                if getattr(self,'phase',None):
                    self.phase(name,'creation-response',{'repository_id':data.get('id'),'owner_id':data.get('owner',{}).get('id'),'full_name':data.get('full_name')})
            if getattr(self, 'phase', None): self.phase(name, 'remote-created')
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            # Clone in an isolated attempt directory; never overwrite/delete remnants.
            import tempfile
            downloads = path.parent.parent/'downloads'
            downloads.mkdir(parents=True,exist_ok=True)
            attempt = Path(tempfile.mkdtemp(prefix=name+'-clone-', dir=downloads))
            candidate = attempt/'repository'
            command(['git', 'clone', self.remote(name), candidate])
            require(not path.exists(), '下载期间目标目录出现，保留下载结果并停止。')
            candidate.rename(path)
            attempt.rmdir()
            if getattr(self, 'phase', None): self.phase(name, 'downloaded')
        require((path / '.git').exists(), f'{path} 不是 Git 仓库。')
        if self.kind == 'github':
            identity=github_identity(self.organization)
            git(path,'config','user.name',identity['login'])
            git(path,'config','user.email',str(identity['id'])+'+'+identity['login']+'@users.noreply.github.com')
        if self.kind == 'local':
            git(path, 'config', 'user.name', 'Second Brain Local Test')
            git(path, 'config', 'user.email', 'second-brain@example.invalid')
        if not git(path, 'rev-parse', '--verify', 'HEAD', check=False).returncode == 0:
            require(allow_create, f'{name} 没有初始提交。')
            (path/'README.md').write_text('# '+title+'\n', encoding='utf-8')
            git(path, 'add', '--', 'README.md')
            git(path, 'commit', '-m', 'feat(asset): 初始化仓库')
            git(path, 'push', '-u', 'origin', 'HEAD:main')
            if getattr(self,'phase',None):self.phase(name,'initialized')

    def rename(self, old, new):
        old_path, new_path = self.repo(old), self.repo(new)
        require(not self.info(new)['exists'] and not new_path.exists(), '更名目标已存在。')
        if self.kind == 'local':
            Path(self.remote(old)).rename(self.remote(new))
        else:
            command(['gh', 'api', '--method', 'PATCH', f'repos/{self.organization}/{old}', '-f', 'name='+new])
        old_path.rename(new_path)
        git(new_path, 'remote', 'set-url', 'origin', self.remote(new))


def snapshot(provider, names, strict=False, baseline=None):
    result = {}
    for name in sorted(set(names)):
        path = provider.repo(name)
        if baseline is not None:
            item=json.loads(json.dumps(baseline[name]))
        else:
            info=provider.info(name)
            item = {'remote': provider.head(name,info), 'remote_exists': info['exists'], 'local': None, 'status': None, 'rules': {}}
            if provider.kind=='github':item['repository_id']=info.get('id');item['owner_id']=info.get('owner_id')
        if path.exists():
            require((path/'.git').exists(), f'已有目录不是仓库：{name}')
            item['local'] = git(path, 'rev-parse', 'HEAD', check=False).stdout.strip()
            item['status'] = git(path, 'status', '--porcelain=v1', '--untracked-files=all').stdout
            item['branch'] = git(path, 'symbolic-ref', '--quiet', '--short', 'HEAD', check=False).stdout.strip()
            item['origin'] = git(path, 'remote', 'get-url', 'origin', check=False).stdout.strip()
            for p in ['AGENTS.md', '.quanttide/agent/contract.yaml', '.quanttide/docs/contract.yaml', '.quanttide/asset/contract.yaml']:
                item['rules'][p] = text_at(path, p)
            if strict:
                require(not item['status'], f'{name} 有未提交修改，先处理再生成计划。')
                require(bool(item['branch']), f'{name} 处于 detached HEAD，请先切换分支。')
                require(item['origin'] == provider.remote(name), f'{name} 的 origin 与目标不符。')
                require(item['local'] == item['remote'], f'{name} 与远端不同步，请先处理。')
        result[name] = item
    return result


def asset_map(domain, spec):
    return {key: {'repo': rule['repo'].format(**domain), 'path': rule['path'].format(**domain)} for key, rule in spec['asset_types'].items()}

def content_block(text, key, body):
    begin, end = f'<!-- second-brain-init:{key}:begin -->', f'<!-- second-brain-init:{key}:end -->'
    block = begin+'\n'+body.rstrip()+'\n'+end
    if begin in text:
        require(end in text, '托管文档标记不完整。')
        start, stop = text.index(begin), text.index(end)+len(end)
        return text[:start]+block+text[stop:]
    return text.rstrip()+'\n\n'+block+'\n'

def validate_config(cfg, spec):
    require(cfg.get('scenario') in spec['scenarios'], '请明确选择 scenario，支持范围见示例。')
    require(cfg.get('schema_version') == 1, 'schema_version 必须为 1。')
    scenario = cfg['scenario']
    require(isinstance(cfg.get('new_root',False),bool) and (not cfg.get('new_root') or scenario=='new-domain'), 'new_root 仅适用于新建领域，须为布尔值。')
    known = {'schema_version','scenario','domain','target_repo','asset_type','assets','mounts','root_repo','register_root','renames','reference_repos','version','notes','new_repositories_only','new_root'}
    require(not set(cfg)-known, '未知配置字段：'+', '.join(sorted(set(cfg)-known)))
    require(isinstance(cfg.get('new_repositories_only',False),bool), 'new_repositories_only 必须为布尔值。')
    require(not cfg.get('new_repositories_only') or scenario=='new-domain', '仅新建领域可启用禁止复用模式。')
    require(isinstance(cfg.get('register_root', True), bool), 'register_root 必须为布尔值。')
    for field in spec['scenarios'][scenario]['required_inputs']:
        require(bool(cfg.get(field)), f'缺少输入 {field}，请补充后重试。')
    if scenario in ('new-domain', 'complete-existing', 'append-assets'):
        domain = cfg['domain']
        require(isinstance(domain, dict), 'domain 必须是对象。')
        for key in ('chinese_name','english_name','short_name','overview','boundary','neighbors'):
            require(isinstance(domain.get(key), str) and bool(domain[key].strip()), f'domain 缺少 {key}。')
            require('\x00' not in domain[key] and '\r' not in domain[key], '领域文字含非法字符。')
        slug(domain['english_name']); slug(domain['short_name'])
        require('\n' not in domain['chinese_name'], '中文名须为单行。')
        require(domain['short_name'] not in spec['reserved_names'], '领域简称与资产类型容器冲突。')
    if scenario == 'append-assets':
        require(isinstance(cfg['assets'], list) and all(isinstance(k, str) for k in cfg['assets']), 'assets 必须是资产类型名称列表。')
        require(len(set(cfg['assets'])) == len(cfg['assets']), 'assets 不能重复。')
    if scenario == 'aggregate-container':
        require(cfg['asset_type'] in spec['reserved_names'], '未知资产容器类型。')
    require(isinstance(cfg.get('mounts', []), list), 'mounts 必须是列表。')
    for m in cfg.get('mounts', []):
        require(isinstance(m, dict) and set(m) == {'repo','path'}, 'mounts 每项只包含 repo 和 path。')
        slug(m['repo']); safe_path(Path('/tmp'), m['path'])
        if scenario == 'mount-product':
            require(m['path'] == 'apps/'+m['repo'], '产品挂载路径必须为 apps/仓库名。')
        if scenario == 'aggregate-container':
            require(m['path'].startswith(('domains/','default/')), '容器路径必须位于 domains 或 default。')
            require(m['repo'].startswith('quanttide-'+cfg['asset_type']+'-of-'), '容器中仓库类型不匹配。')
    if scenario == 'rename':
        require(isinstance(cfg['renames'], dict), 'renames 应为旧仓库名到新仓库名的映射。')
        for old, new in cfg['renames'].items():
            slug(old); slug(new)
            require(old != new and old.startswith('quanttide-') and new.startswith('quanttide-') and '-of-' in old and '-of-' in new, '英文更名需完整且不同的配套资产仓库名（含 -of-）。')
            require(old.split('-of-')[0]==new.split('-of-')[0], '更名不能改变资产类型。')
        require(not set(cfg['renames']) & set(cfg['renames'].values()), '不支持循环或链式更名。')
        require(len(set(cfg['renames'].values())) == len(cfg['renames']), '更名目标重复。')
    if scenario == 'release':
        require(isinstance(cfg['notes'], str) and bool(cfg['notes'].strip()), 'notes 必须是非空文字。')
        require(bool(re.fullmatch(r'\d+\.\d+\.\d+', str(cfg['version']))), '版本必须是 X.Y.Z。')
    return cfg


def make_plan(config, workspace, run_dir, provider_kind='local', organization='quanttide'):
    spec = read_yaml(SPEC)
    cfg = validate_config(read_yaml(config), spec)
    work, run = Path(workspace).resolve(), Path(run_dir).resolve()
    require(not work.is_relative_to(run) and not run.is_relative_to(work), '运行记录目录与目标工作区必须分开。')
    require(not (run/'execution-plan.json').exists(), '运行记录已存在，请使用新的运行目录。')
    require(shutil.which('git'), '需要安装 Git。')
    if provider_kind == 'github':
        require(shutil.which('gh'), 'GitHub 模式需要 GitHub CLI 和已登录账号。')
        command(['gh','auth','status'])
    provider = Provider(work, provider_kind, organization)
    identity=github_identity(organization) if provider_kind=='github' else None
    if identity:organization=identity['owner'];provider.organization=organization
    scenario = cfg['scenario']
    domain = cfg.get('domain', {})
    target = cfg.get('target_repo') or ('quanttide-'+domain['short_name'] if domain else 'quanttide-'+cfg.get('asset_type','profile'))
    root = slug(cfg.get('root_repo','quanttide'))
    slug(target)
    require(target != root, '领域或资产容器不能与根仓库相同。')
    register = cfg.get('register_root', True) and scenario not in ('rename','release')
    ops, checks, names = [], [], set()
    def add(kind, repo, **kwargs):
        names.add(slug(repo))
        ops.append(dict(id=f'{len(ops)+1:03}', kind=kind, repo=repo, **kwargs))
    def ensure(name, allow, title=None):
        add('ensure-repo', name, allow_create=allow, title=title or name, require_new=bool((cfg.get('new_repositories_only') and name!=root) or (cfg.get('new_root') and name==root)))
    def finish(name):
        add('finish', name)
    mounts = list(cfg.get('mounts', []))
    if scenario == 'new-domain':
        mapping = asset_map(domain, spec)
        mounts = [mapping[k] for k in spec['initial_assets']]
    if scenario == 'append-assets':
        require(all(k in spec['asset_types'] for k in cfg['assets']), 'assets 包含未知资产类型。')
        mounts = [asset_map(domain, spec)[k] for k in cfg['assets']]
    if scenario not in ('rename','release'):
        require(all(m['repo'] not in (target, root) for m in mounts), '不能自挂载或形成根仓库循环。')
        require(len({m['path'] for m in mounts})==len(mounts), '挂载路径重复。')
        for m in mounts:
            ensure(m['repo'], scenario in ('new-domain','append-assets'))
            finish(m['repo'])
        ensure(target, scenario in ('new-domain','aggregate-container'), domain.get('chinese_name', target))
        for m in mounts:
            add('mount', target, child=m['repo'], path=m['path'])
            checks.append({'kind':'mount','repo':target, 'path':m['path'], 'child':m['repo']})
        if scenario in ('new-domain','complete-existing'):
            add('domain-docs', target, domain=domain, directories=spec['domain_directories'])
            checks.append({'kind':'domain','repo':target,'directories':spec['domain_directories']})
        elif scenario == 'aggregate-container':
            add('container-docs', target, asset_type=cfg['asset_type'])
        add('catalog', target)
        finish(target)
        if register:
            ensure(root, provider_kind == 'local' or cfg.get('new_root',False))
            path = ('assets/' if scenario == 'aggregate-container' else 'domains/')+target
            add('mount', root, child=target, path=path)
            checks.append({'kind':'mount','repo':root,'child':target,'path':path})
            add('catalog', root)
            add('root-index', root)
            finish(root)
    elif scenario == 'rename':
        for old, new in cfg['renames'].items():
            ensure(old, False)
            add('rename-repo', old, new_name=new)
            names.add(new)
        references = cfg['reference_repos']
        require(isinstance(references, list) and bool(references), 'reference_repos 需列出领域和根仓库。')
        for name in references:
            ensure(name, False)
        ordered = list(cfg['renames'].values()) + references
        for name in ordered:
            add('replace-references', name, renames=cfg['renames'])
            add('refresh-mounts', name)
            finish(name)
        checks.append({'kind':'no-old-references','repos':ordered,'old_names':list(cfg['renames'])})
    else:
        ensure(target, False)
        add('release-notes', target, version=str(cfg['version']), notes=cfg['notes'])
        finish(target)
        add('release', target, version=str(cfg['version']), notes=cfg['notes'])
        checks.append({'kind':'tag','repo':target,'version':str(cfg['version'])})
    initial = snapshot(provider, names, strict=True)
    if provider_kind=='github':
        for name in names:
            if initial[name]['remote_exists']:
                info=provider.info(name)
                require(info.get('owner_id')==identity['owner_id'] and info.get('can_push') and not info.get('archived'), '目标归属、写入权限或归档状态不允许本次操作：'+name)
    for op in ops:
        if op['kind'] == 'ensure-repo':
            require(op['allow_create'] or initial[op['repo']]['remote'], f'已有仓库场景要求远端存在：{op["repo"]}')
            require(not op.get('require_new') or not initial[op['repo']]['remote_exists'], f'新建目标 {op["repo"]} 已存在；请改名或单独调查维护，不能自动复用。')
        if op['kind'] == 'rename-repo':
            require(not initial[op['new_name']]['remote'] and not initial[op['new_name']]['local'], '更名目标已经存在。')
    # Read-only materialization of remote README/rules for review is a clone into run_dir, not the target workspace.
    inspection = {}
    for name in sorted(names):
        state = initial[name]
        if not state['remote']:
            continue
        src = provider.repo(name)
        if not src.exists():
            src = run/'inspection'/name
            src.parent.mkdir(parents=True, exist_ok=True)
            command(['git','clone','--depth','1',provider.remote(name),src])
        require(git(src,'rev-parse','HEAD').stdout.strip()==state['remote'], '读取说明期间仓库版本已变化，请重新生成方案。')
        inspection[name] = {p: text_at(src,p) for p in ['README.md','AGENTS.md','.gitmodules','.quanttide/agent/contract.yaml','.quanttide/docs/contract.yaml','.quanttide/asset/contract.yaml']}
        if scenario == 'new-domain' and name == target:
            require('second-brain-init:domain:begin' in inspection[name]['README.md'], '同名领域已存在；请使用 complete-existing 调查补全，不能按新建处理。')
    plan = dict(schema_version=2, plugin='second-brain-init', version=VERSION, created_at=now(), scenario=scenario,
                provider=provider_kind, organization=organization, github_identity=identity, workspace=str(work), config=cfg,
                operations=ops, checks=checks, names=sorted(names), before=initial, inspection=inspection,
                engine_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), spec_sha256=hashlib.sha256(SPEC.read_bytes()).hexdigest(), sources=spec['sources'])
    plan['id'] = digest(plan)
    save(run/'execution-plan.json', plan)
    lines = ['# 第二大脑执行计划','','状态：等待人工确认。','',f'计划编号：{plan["id"]}', '',f'执行环境：{provider_kind}', '', '## 已确认的输入','', '```yaml',yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False).rstrip(),'```','','## 操作清单','']
    for op in ops:
        lines.append(f'- {op["id"]} {op["kind"]}：{op["repo"]}'+(f' → {op["path"]}' if 'path' in op else '')+'。')
    lines += ['','## 执行与审阅','','本计划包含建仓、文件写入、提交与推送。local 模式仅操作指定工作区内的本地仓库；github 模式将操作公开 GitHub 仓库。', '', '请检查 execution-plan.json 的 inspection 中的原有契约及 config 中的名称、边界和挂载目标。确认后运行 approve，修改输入则新建一份计划。','']
    (run/'execution-plan.md').write_text('\n'.join(lines), encoding='utf-8')
    return plan


def recovery_snapshot_matches(current, state):
    expected = state['checkpoint']
    if current == expected: return True
    adjusted = json.loads(json.dumps(expected))
    for name, before in expected.items():
        phases = [p for p in state.get('phases', []) if p['repo'] == name]
        if phases and phases[-1]['kind'] == 'committed' and before.get('local') and before.get('status') == '':
            candidate = dict(before, remote=before['local'])
            if current.get(name) == candidate: adjusted[name] = candidate
    return current == adjusted

def engine_sha256():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

def engine_compatible(plan):
    return plan.get('engine_sha256') in ({engine_sha256()} | COMPATIBLE_ENGINE_SHA256S)

def local_changed_paths(repo):
    pending=set(filter(None,git(repo,'ls-files','--modified','--others','--exclude-standard','-z').stdout.split('\0')))
    staged=set(filter(None,git(repo,'diff','--cached','--name-only','-z').stdout.split('\0')))
    return pending | staged

def reconcile_pending_local_phase(provider,plan,state):
    """Recognize an exact local phase receipt left by an interrupted process.

    Network writes are never repeated here. Files, repository identity and the
    local commit boundary must match the durable workflow-owned hashes before a
    checkpoint is advanced.
    """
    pending=state.get('pending_phase') or {}
    stage,name=pending.get('stage'),pending.get('repo')
    if stage not in ('downloaded','files-written','staged','committed') or name not in plan['names']:
        return False
    before=state['checkpoint'][name]
    observed=snapshot(provider,[name])[name]
    identity_keys=('remote','remote_exists','repository_id','owner_id')
    require(all(observed.get(key)==before.get(key) for key in identity_keys),
            '断点恢复时远端仓库身份或提交已变化，请人工检查。')
    repo=provider.repo(name)
    if stage=='downloaded':
        require(before.get('local') is None and observed.get('local')==observed.get('remote')
                and not observed.get('status') and observed.get('origin')==provider.remote(name),
                '下载断点与远端状态不一致，不能自动接续。')
    else:
        executor=Executor(plan,state.get('owned_files'))
        require(bool(state.get('owned_content')) and executor.owned_content()==state['owned_content'],
                '断点中的工作流文件内容已变化，不能自动接续。')
        allowed=set((state.get('owned_files') or {}).get(name,[]))
        require(all(observed.get(key)==before.get(key) for key in ('branch','origin')),
                '断点中的本地分支或来源已变化，不能自动接续。')
        old_rules,new_rules=before.get('rules',{}),observed.get('rules',{})
        require(all(old_rules.get(path)==new_rules.get(path) for path in set(old_rules)|set(new_rules) if path not in allowed),
                '断点中的非工作流规则文件已变化，不能自动接续。')
        if stage in ('files-written','staged'):
            require(observed.get('local')==before.get('local')
                    and local_changed_paths(repo)<=allowed,
                    '断点中的本地变更超出工作流范围，不能自动接续。')
        else:
            require(not observed.get('status') and before.get('local')
                    and git(repo,'rev-parse','HEAD^').stdout.strip()==before.get('local'),
                    '断点中的本地提交不是已核对提交的直接后继，不能自动接续。')
            changed=set(filter(None,git(repo,'diff','--name-only','-z',before['local'],observed['local']).stdout.split('\0')))
            require(changed<=allowed,'断点提交包含工作流范围外的文件，不能自动接续。')
    state['checkpoint'][name]=observed
    state.setdefault('phases',[]).append({'op':pending.get('op'),'repo':name,'kind':stage,
                                          'status':'passed','at':now(),'recovered_from':'durable-local-receipt'})
    state.pop('pending_phase',None)
    return True

def operation_names(plan, op):
    """Repositories whose state can affect this one operation."""
    return sorted({op.get(key) for key in ('repo', 'child', 'new_name')
                   if op.get(key) in plan['names']})

def next_operation(plan, state):
    return next((op for op in plan['operations'] if op['id'] not in state.get('completed', [])), None)

def preflight_names(plan,state):
    # A newly approved plan gets one complete drift check before any write.
    # Resumes check only the next operation here; every later operation checks
    # its own dependencies immediately before touching them.
    if not state.get('completed') and not state.get('events') and not state.get('pending_phase'):
        return plan['names']
    upcoming=next_operation(plan,state)
    return operation_names(plan,upcoming) if upcoming else plan['names']

def reconcile_creation_response(provider, plan, state):
    """Turn a durable GitHub create response into a resumable checkpoint.

    This is intentionally narrow: without the exact repository and owner IDs
    returned by the create call, an unexpected same-name repository is never
    adopted automatically.
    """
    pending=state.get('pending_phase') or {}
    name=pending.get('repo')
    saved=(state.get('creation_responses') or {}).get(name,{}).get('receipt') or {}
    if pending.get('stage') not in ('creation-response','remote-created') or not name or not saved:
        return False
    require(saved.get('full_name','').lower()==(plan['organization']+'/'+name).lower(),
            '创建响应中的仓库名称与计划不一致。')
    observed=snapshot(provider,[name])[name]
    require(observed.get('remote_exists') and observed.get('repository_id')==saved.get('repository_id')
            and observed.get('owner_id')==saved.get('owner_id'),
            '已创建仓库的身份无法与创建响应对应，不能自动接续。')
    require(observed.get('remote') and observed.get('local') is None,
            '已创建仓库的本地或远端状态超出自动接续范围。')
    state['checkpoint'][name]=observed
    state.setdefault('created_receipts',{})[name]=dict(observed)
    state.setdefault('phases',[]).append({'op':pending.get('op'),'repo':name,
                                          'kind':'remote-created','status':'passed',
                                          'at':now(),'recovered_from':'creation-response'})
    state.pop('pending_phase',None)
    return True


def load_plan(run, readonly=False):
    plan = read_json(Path(run)/'execution-plan.json')
    expected = plan.pop('id')
    require(digest(plan) == expected, '计划内容已变化，请重新生成并确认。')
    plan['id'] = expected
    require(readonly or engine_compatible(plan), '执行器版本已变化；旧任务请使用检查或专用修复入口，未开始任务需重新生成计划。')
    require(plan['spec_sha256'] == hashlib.sha256(SPEC.read_bytes()).hexdigest(), '配置规格已变化，请重新生成计划。')
    return plan

def approve(run, reviewer, accepted_id=None, simulated=False):
    plan = load_plan(run)
    require(bool(reviewer.strip()), '需要填写审阅者。')
    if accepted_id is None:
        print(Path(run,'execution-plan.md').read_text(encoding='utf-8'))
        accepted_id = input('确认后输入完整计划编号（回车取消）：').strip()
    require(accepted_id == plan['id'], '未确认这份计划。')
    require(not simulated or plan['provider']=='local', '模拟反馈只能用于 local 测试。')
    record = {'plan_id':plan['id'], 'reviewer':reviewer, 'at':now(), 'simulated':simulated, 'accepted':True}
    save(Path(run)/'approval-record.json', record)
    return record

class Executor:
    def __init__(self, plan, changed=None):
        self.plan = plan
        self.provider = Provider(plan['workspace'],plan['provider'],plan['organization'])
        self.changed = {name:set(paths) for name,paths in (changed or {}).items()}

    def owned_content(self):
        result={}
        for name,paths in self.changed.items():
            result[name]={}
            for relative in sorted(paths):
                path=safe_path(self.provider.repo(name),relative)
                result[name][relative]=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        return result

    def write(self, repo, name, content, missing_only=False):
        path = safe_path(repo, name)
        if path.exists() and (missing_only or path.read_text(encoding='utf-8') == content):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        self.changed.setdefault(repo.name,set()).add(name)
        if getattr(self.provider, 'phase', None): self.provider.phase(repo.name, 'files-written')

    def block(self, repo, path, key, body):
        self.write(repo, path, content_block(text_at(repo,path),key,body))

    def refresh(self, repo, mount_path, url):
        path = safe_path(repo,mount_path)
        git(repo,'-c','protocol.file.allow=always' if self.provider.kind=='local' else 'protocol.file.allow=never','submodule','update','--init','--',mount_path)
        git(path,'fetch','origin')
        branch_ref = command(['git','ls-remote','--symref',url,'HEAD']).stdout
        match = re.search(r'ref: refs/heads/(\S+)\s+HEAD',branch_ref)
        require(match, '子模块远端默认分支不可识别。')
        git(path,'checkout','--detach','origin/'+match.group(1))
        self.changed.setdefault(repo.name,set()).add(mount_path)

    def execute(self, op):
        provider = self.provider
        repo = provider.repo(op['repo'])
        kind = op['kind']
        if kind == 'ensure-repo':
            provider.ensure(op['repo'],op['allow_create'],op['title'],require_new=op.get('require_new',False))
            if not self.plan['before'][op['repo']]['remote_exists']:
                container=self.plan['scenario']=='aggregate-container' and op['repo']!=self.plan['config'].get('root_repo','quanttide')
                self.write(repo,'LICENSE',APACHE if container else CC,missing_only=True)
                self.write(repo,'CHANGELOG.md','# 变更记录\n\n## [Unreleased]\n\n## [0.1.0]\n\n- 初始化第二大脑仓库。\n',missing_only=True)
        elif kind == 'mount':
            path, url = op['path'], provider.remote(op['child'])
            existing = modules(repo)
            if path in existing:
                require(existing[path]['url']==url, f'{path} 已挂载其他仓库，拒绝覆盖。')
                self.refresh(repo,path,url)
            else:
                location = safe_path(repo,path)
                if location.is_dir() and sorted(p.name for p in location.iterdir()) == ['.gitkeep']:
                    git(repo,'rm','--',path+'/.gitkeep')
                    self.changed.setdefault(repo.name,set()).add(path+'/.gitkeep')
                    if location.exists(): location.rmdir()
                require(not location.exists(), f'{path} 已存在，需人工处理。')
                git(repo,'-c','protocol.file.allow=always' if provider.kind=='local' else 'protocol.file.allow=never','submodule','add',url,path)
                self.changed.setdefault(repo.name,set()).update(['.gitmodules',path])
            if getattr(provider,'phase',None):provider.phase(repo.name,'files-written')
        elif kind == 'domain-docs':
            d = op['domain']
            base = text_at(repo,'README.md') or '# '+d['chinese_name']+'\n'
            if base.strip() == '# '+repo.name: base='# '+d['chinese_name']+'\n'
            body = '## 概述\n\n'+d['overview']+'\n\n## 领域边界\n\n'+d['boundary']+'\n\n## 相邻领域分工\n\n'+d['neighbors']
            # Existing human sections remain intact; generated block is the only managed part.
            if 'second-brain-init:domain:begin' not in base:
                parts=[('概述',d['overview']),('领域边界',d['boundary']),('相邻领域分工',d['neighbors'])]
                body='\n\n'.join('## '+heading+'\n\n'+value for heading,value in parts if '## '+heading not in base)
            if body: self.write(repo,'README.md',content_block(base,'domain',body))
            self.write(repo,'LICENSE',CC,missing_only=True)
            if '## 许可' not in text_at(repo,'README.md'):
                self.block(repo,'README.md','license','## 许可\n\n见 [LICENSE](LICENSE)。已有仓库沿用原有许可。')
            for path in op['directories']:
                location = safe_path(repo,path)
                if not location.exists():
                    self.write(repo,path+'/.gitkeep','')
            self.write(repo,'CHANGELOG.md','# 变更记录\n\n## [Unreleased]\n\n## [0.1.0]\n\n- 初始化领域第二大脑。\n',missing_only=True)
        elif kind == 'container-docs':
            self.write(repo,'LICENSE',APACHE,missing_only=True)
            self.block(repo,'README.md','container','## 聚合范围\n\n按 default 和 domains 汇集 '+op['asset_type']+' 资产。')
        elif kind == 'catalog':
            entries = modules(repo)
            body = '## 资产目录\n\n'+'\n'.join(f'- [{path}]({path}/)：{value["url"]}。' for path,value in sorted(entries.items()))
            if not entries: body += '当前尚未挂载资产。'
            self.block(repo,'README.md','catalog',body)
        elif kind == 'root-index':
            entries = modules(repo)
            domains = [(p,v) for p,v in sorted(entries.items()) if p.startswith('domains/')]
            body = f'## 领域清单\n\n已登记领域数量：{len(domains)}。\n\n'+ '\n'.join(f'- [{p.split("/")[-1]}]({p}/)。' for p,_ in domains)
            self.block(repo,'README.md','domains',body)
            index = '# 领域目录\n\n## 目录结构\n\n'+ '\n'.join(f'- {p}。' for p,_ in domains)+'\n\n## 领域清单\n\n'+'\n'.join(f'- [{p.split("/")[-1]}]({p.split("/")[-1]}/)。' for p,_ in domains)+'\n\n## 领域项目\n\n'+'\n\n'.join(f'### {p.split("/")[-1]}\n\n仓库：{v["url"]}' for p,v in domains)
            original = text_at(repo,'domains/README.md')
            index = content_block(original or '# 领域目录\n', 'domains-index', index.replace('# 领域目录\n\n','',1))
            self.write(repo,'domains/README.md',index)
        elif kind == 'finish':
            # Restrict staging to files this workflow changed; recover touched paths from porcelain after resume.
            status = git(repo,'status','--porcelain=v1','--untracked-files=all').stdout
            if status:
                paths = set(self.changed.get(repo.name,set()))
                pending = set(filter(None,git(repo,'ls-files','--modified','--others','--exclude-standard','-z').stdout.split('\0')))
                staged = set(filter(None,git(repo,'diff','--cached','--name-only','-z').stdout.split('\0')))
                require(bool(paths) and (pending | staged) <= paths, '发现未归属到工作流的变更，请人工检查；不会提交额外文件。')
                changelog = text_at(repo,'CHANGELOG.md') or '# 变更记录\n\n## [Unreleased]\n'
                entry = '- second-brain-init '+self.plan['id'][:12]+'：'+self.plan['scenario']+'。'
                if entry not in changelog:
                    if '## [Unreleased]' not in changelog:
                        changelog += '\n## [Unreleased]\n'
                    changelog = changelog.replace('## [Unreleased]','## [Unreleased]\n\n'+entry,1)
                    self.write(repo,'CHANGELOG.md',changelog)
                paths.add('CHANGELOG.md')
                for path in sorted(paths): safe_path(repo,path)
                stage_paths=[p for p in sorted(paths) if not any(p.startswith(parent+'/') for parent in paths if parent!=p)]
                git(repo,'add','--',*stage_paths)
                if getattr(provider, 'phase', None): provider.phase(repo.name, 'staged')
                if git(repo,'diff','--cached','--quiet',check=False).returncode:
                    git(repo,'commit','-m','feat(asset): '+self.plan['scenario'])
                    if getattr(provider, 'phase', None): provider.phase(repo.name, 'committed')
            branch = git(repo,'symbolic-ref','--short','HEAD').stdout.strip()
            require(not git(repo,'status','--porcelain').stdout, '提交后仍有遗漏文件，请保留任务并检查。')
            if provider.head(repo.name) != git(repo,'rev-parse','HEAD').stdout.strip():
                git(repo,'push','origin','HEAD:refs/heads/'+branch)
            if getattr(provider, 'phase', None): provider.phase(repo.name, 'pushed')
        elif kind == 'rename-repo':
            provider.rename(op['repo'],op['new_name'])
        elif kind == 'replace-references':
            files = git(repo,'ls-files','-z').stdout.split('\0')
            for name in filter(None,files):
                path = safe_path(repo,name)
                if not path.is_file() or path.stat().st_size > 2_000_000:
                    continue
                try: content = path.read_text(encoding='utf-8')
                except UnicodeError: continue
                if '\x00' in content: continue
                new = content
                for old, fresh in op['renames'].items():
                    new = re.sub(re.escape(old)+r'(?![a-z0-9-])',lambda _:fresh,new)
                if new != content: self.write(repo,name,new)
            git(repo,'submodule','sync','--recursive')
        elif kind == 'refresh-mounts':
            for path, value in modules(repo).items(): self.refresh(repo,path,value['url'])
            if getattr(provider,'phase',None):provider.phase(repo.name,'files-written')
        elif kind == 'release-notes':
            text = text_at(repo,'CHANGELOG.md')
            require('## [Unreleased]' in text, '发布要求存在 Unreleased 章节。')
            require('## ['+op['version']+']' not in text, '该版本已经存在。')
            heading = '## [Unreleased]\n\n## ['+op['version']+'] - '+self.plan['created_at'][:10]+'\n\n'+op['notes']
            self.write(repo,'CHANGELOG.md',text.replace('## [Unreleased]',heading,1))
        elif kind == 'release':
            tag = 'v'+op['version']
            git(repo,'tag','-a',tag,'-m',op['notes'])
            git(repo,'push','origin','refs/tags/'+tag)
            if provider.kind == 'github':
                command(['gh','release','create',tag,'--repo',provider.organization+'/'+op['repo'],'--verify-tag','--notes',op['notes']])
        else:
            raise WorkflowError('未知操作类型：'+kind)


def markdown_errors(text):
    errors, h1, fence = [], 0, False
    for line in text.splitlines():
        if line.startswith('```'):
            if not fence and line == '```': errors.append('代码块未标注语言')
            fence = not fence
        elif not fence:
            if line.startswith('# '): h1 += 1
            if re.match(r'^#{4,}\s',line): errors.append('标题超过三级')
    if h1 != 1: errors.append('需要且仅允许一个一级标题')
    if fence: errors.append('代码块未闭合')
    return errors


def verify(plan, approval=None):
    provider = Provider(plan['workspace'],plan['provider'],plan['organization'])
    details = []
    final_names = set(plan['names']) - set(plan['config'].get('renames',{}))
    total=len(final_names)+len(plan['checks'])
    def progress(repo,label):
        callback=getattr(verification_observer,'callback',None)
        notify_observer(callback,{'repo':repo,'label':label,'completed':len(details),'total':total,'at':now()})
    for name in sorted(final_names):
        progress(name,'检查文件与远端提交（远端读取最多尝试 3 次）')
        path = provider.repo(name)
        try:
            require(path.exists(), '本地仓库不存在')
            dirty=git(path,'status','--porcelain').stdout
            require(not dirty, '存在未提交文件：'+dirty.strip())
            require(git(path,'rev-parse','HEAD').stdout.strip()==provider.head(name), 'HEAD 与远端不一致')
            for filename in ['README.md','CHANGELOG.md']:
                content = text_at(path,filename)
                if content: require(not markdown_errors(content), filename+'：'+'；'.join(markdown_errors(content)))
            if not plan['before'][name]['remote_exists']:
                require(all(text_at(path,f) for f in ['README.md','LICENSE','CHANGELOG.md']), '新仓库缺少说明、许可或变更记录')
            details.append({'check':'repository','repo':name,'passed':True,'commit':git(path,'rev-parse','HEAD').stdout.strip(),'checked_at':now(), 'url':'https://github.com/'+plan['organization']+'/'+name if plan['provider']=='github' else None})
        except WorkflowError as exc:
            details.append({'check':'repository','repo':name,'passed':False,'status':'unknown' if isinstance(exc,RemoteReadError) else 'failed','reason':str(exc),'checked_at':now(),'url':'https://github.com/'+plan['organization']+'/'+name if plan['provider']=='github' else None})
    for check in plan['checks']:
        progress(check.get('repo','本次范围'),{'mount':'检查仓库连接','domain':'检查目录结构','tag':'检查远端版本标签'}.get(check['kind'],'检查资料引用'))
        try:
            if check['kind']=='mount':
                parent = provider.repo(check['repo'])
                record = modules(parent).get(check['path'])
                require(record and record['url']==provider.remote(check['child']), '子模块 URL 不一致')
                raw = git(parent,'ls-tree','HEAD','--',check['path']).stdout.split()
                require(raw and raw[0]=='160000' and raw[2]==provider.head(check['child']), '子模块指针与远端 HEAD 不一致')
            elif check['kind']=='domain':
                repo = provider.repo(check['repo'])
                require(all(safe_path(repo,p).is_dir() for p in check['directories']), '领域目录缺失')
                require(bool(text_at(repo,'LICENSE')), 'LICENSE 缺失')
                require(all('## '+name in text_at(repo,'README.md') for name in ['概述','领域边界','相邻领域分工']), '领域 README 缺少必要章节')
            elif check['kind']=='no-old-references':
                for name in check['repos']:
                    repo = provider.repo(name)
                    for old in check['old_names']:
                        require(git(repo,'grep','-l','-F','--',old,check=False).returncode==1, '仍存在旧仓库名称引用')
            elif check['kind']=='tag':
                require(provider.tag_exists(check['repo'],'v'+check['version']), '远端版本标签不存在')
            details.append({'check':check,'passed':True})
        except WorkflowError as exc:
            details.append({'check':check,'repo':check.get('repo'),'passed':False,'status':'unknown' if isinstance(exc,RemoteReadError) else 'failed','reason':str(exc),'checked_at':now()})
    progress('全部目标仓库','本轮核验结束')
    for detail in details:
        detail.setdefault('status','passed' if detail['passed'] else 'failed')
        detail.setdefault('checked_at',now())
    return {'status':'passed' if all(d['passed'] for d in details) and details else 'failed','at':now(),
            'plan_id':plan['id'], 'provider':plan['provider'],
            'approval_kind':('simulated' if approval.get('simulated') else 'human-recorded') if approval else 'not-supplied',
            'human_acceptance':'not-assessed', 'real_github_execution':plan['provider']=='github', 'details':details}


@contextmanager
def execution_locks(run, workspace):
    work = Path(workspace)
    paths = [work.parent / ('.'+work.name+'.second-brain-init.lock'), run/'execution.lock']
    acquired = []
    try:
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            try: handle = path.open('x')
            except FileExistsError:
                raise WorkflowError('目标工作区或运行记录已有执行锁；确认没有进程运行后再处理。') from None
            acquired.append((path,handle))
            handle.write(str(os.getpid())+'\n'); handle.flush()
        yield
    finally:
        for path, handle in reversed(acquired):
            handle.close()
            path.unlink()


def apply(run,prechecked=None):
    run = Path(run)
    plan = load_plan(run)
    require((run/'approval-record.json').is_file(), '尚未确认，未执行任何操作。请先审阅并运行 approve。')
    approval = read_json(run/'approval-record.json')
    require(approval.get('accepted') is True and approval.get('plan_id')==plan['id'], '确认记录不对应此计划。')
    require(not approval.get('simulated') or plan['provider']=='local', 'GitHub 模式不能使用模拟反馈。')
    check_identity(plan)
    with execution_locks(run,plan['workspace']):
        state_file = run/'execution-log.json'
        provider = Provider(plan['workspace'],plan['provider'],plan['organization'])
        state = read_json(state_file) if state_file.exists() else {
            'plan_id':plan['id'],'completed':[],
            # Phase checkpoints must never mutate the immutable approved plan.
            'checkpoint':json.loads(json.dumps(plan['before'])),'events':[]}
        require(state['plan_id']==plan['id'], '执行日志不对应此计划。')
        state['approval_kind']='simulated' if approval.get('simulated') else 'human-recorded'
        state['provider']=plan['provider']
        if state.get('status') == 'completed':
            report = verify(plan,approval)
            save(run/'verification-report.json',report)
            require(report['status']=='passed','既有结果已发生漂移，请检查报告。')
            return report
        if reconcile_creation_response(provider,plan,state):
            save(state_file,state)
        if reconcile_pending_local_phase(provider,plan,state):
            save(state_file,state)
        initial_names = preflight_names(plan,state)
        if prechecked is None:
            current=snapshot(provider,initial_names)
        else:
            require(set(prechecked)==set(initial_names),'执行前检查范围与下一步不一致。')
            current=json.loads(json.dumps(prechecked))
        require(recovery_snapshot_matches(current, {'checkpoint': {name:state['checkpoint'][name] for name in initial_names},
                                                     'phases': state.get('phases', [])}),
                '下一步涉及的仓库在计划或上次检查点之后已变化，请人工检查。')
        if any(current[name]!=state['checkpoint'][name] for name in initial_names):
            state['checkpoint'].update(current)
            pending=state.get('pending_phase') or {}
            if pending.get('repo') in initial_names and pending.get('stage')=='pushed':
                state.setdefault('phases',[]).append({'op':pending.get('op'),'repo':pending['repo'],
                                                      'kind':'pushed','status':'passed','at':now(),
                                                      'recovered_from':'remote-observation'})
                state.pop('pending_phase',None)
            save(state_file,state)
        executor, started = Executor(plan,state.get("owned_files")), time.monotonic()
        require(not state.get('owned_content') or executor.owned_content()==state['owned_content'], '工作流文件内容已变化，请人工检查，不能自动提交。')
        executor.provider.created_receipts = state.get('created_receipts', {})
        def phase(name, stage, receipt=None):
            if stage=='creation-response':
                state['pending_phase']={'op':state.get('current',{}).get('op'),'repo':name,'stage':stage,
                                        'at':now(),'status':'executed-unverified','receipt':receipt}
                state.setdefault('creation_responses',{})[name]=state['pending_phase']
                save(state_file,state)
                return
            state['owned_files']={n:sorted(paths) for n,paths in executor.changed.items()}
            state['owned_content']=executor.owned_content()
            state['pending_phase']={'op':state.get('current',{}).get('op'),'repo':name,'stage':stage,
                                    'at':now(),'status':'executed-unverified','receipt':receipt}
            save(state_file,state)
            observed = snapshot(provider, [name], baseline=state['checkpoint'] if stage in ('downloaded','files-written','staged','committed') else None)[name]
            state['checkpoint'][name] = observed
            if stage == 'remote-created':
                state.setdefault('created_receipts', {})[name] = dict(observed)
                executor.provider.created_receipts = state['created_receipts']
            state['owned_files'] = {n:sorted(paths) for n,paths in executor.changed.items()}
            state['owned_content'] = executor.owned_content()
            event = {'op':state.get('current',{}).get('op'),'repo':name,'kind':stage,'status':'passed','at':now()}
            state.setdefault('phases', []).append(event)
            state.pop('pending_phase',None)
            save(state_file,state)
        executor.provider.phase = phase
        state['status']='running'
        state.pop('error',None)
        save(state_file,state)
        try:
            for op in plan['operations']:
                if op['id'] in state['completed']: continue
                request_observer.stage=op['kind']
                request_observer.target=plan['organization']+'/'+op['repo']
                state['intent']={'op':op['id'],'repo':op['repo'],'kind':op['kind'],'at':now()}
                save(state_file,state)
                state['current']={'op':op['id'],'kind':op['kind'],'repo':op['repo'],'at':now(),'status':'running'}
                state['events'].append(dict(state['current']));save(state_file,state)
                affected=operation_names(plan, op)
                observed=snapshot(provider,affected)
                require(all(observed[n]==state['checkpoint'][n] for n in affected),
                        '执行过程中仓库已变化（仅核对当前相关仓库）；停止并保留已完成记录，请重新调查。')
                require(not state.get('owned_content') or executor.owned_content()==state['owned_content'], '工作流文件内容已变化，请人工检查，不能自动提交。')
                executor.execute(op)
                state['completed'].append(op['id'])
                state['events'].append({'op':op['id'],'kind':op['kind'],'repo':op['repo'],'at':now(),'status':'passed'})
                state['owned_content']=executor.owned_content()
                state['owned_files']={name:sorted(paths) for name,paths in executor.changed.items()}
                # Local/file phases already update their checkpoint without a
                # network call. Rename is the only operation here that changes
                # repository identity and therefore needs a fresh observation.
                if op['kind']=='rename-repo':
                    state['checkpoint'].update(snapshot(provider,affected))
                state['current']['status']='passed'
                save(state_file,state)
            state['current']={'kind':'verify','repo':'全部目标仓库','at':now(),'status':'running'};save(state_file,state)
            report=verify(plan,approval)
            save(run/'verification-report.json',report)
            require(report['status']=='passed','结果校验未通过，请查看 verification-report.json。')
            state['status']='completed'
            state['current']['status']='passed'
        except (WorkflowError, OSError, KeyboardInterrupt) as exc:
            state['status']='paused'
            state['error']=str(exc) or '用户中断'
            state.setdefault('first_error',state['error'])
            if state.get('current'):
                state['current']['status']='failed';state['events'].append(dict(state['current'],at=now()))
            # Keep the last successful checkpoint; do not bless partial mutations as known-safe.
            raise WorkflowError(state['error']) from None
        finally:
            state['elapsed_seconds']=round(time.monotonic()-started,3)
            save(state_file,state)
            confirmation='模拟确认（自动化测试）' if approval.get('simulated') else '已记录审阅者确认'
            result=['# 执行结果','', '状态：'+state['status'],'',
                    '完成操作：'+str(len(state['completed']))+'/'+str(len(plan['operations'])),'',
                    '环境：'+plan['provider'],'','确认类型：'+confirmation,'',
                    '真实用户验收：未评估。','',
                    '真实 GitHub 操作：'+('本次使用 GitHub provider，详情见执行日志。' if plan['provider']=='github' else '未执行；使用工作区内的本地 Git 远端。'),'',
                    ('错误：'+state.get('error','') if state['status']!='completed' else '仓库、文档、子模块与远端一致性检查通过。'),'']
            (run/'result.md').write_text('\n'.join(result),encoding='utf-8')
        return report


def cli(argv=None):
    parser = argparse.ArgumentParser(description='第二大脑创建配置执行器；默认仅显示帮助。')
    sub = parser.add_subparsers(dest='action')
    p=sub.add_parser('plan',help='读取配置、调查现状并生成待确认计划')
    p.add_argument('--config',type=Path,required=True); p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--run-dir',type=Path,required=True); p.add_argument('--provider',choices=['local','github'],default='local')
    p.add_argument('--organization',default='quanttide')
    p=sub.add_parser('approve',help='人工审阅后确认具体计划')
    p.add_argument('--run-dir',type=Path,required=True); p.add_argument('--reviewer',required=True)
    p.add_argument('--accept',help='已在外部审阅的完整计划编号；缺省时交互确认')
    p.add_argument('--simulated',action='store_true',help='仅供自动化本地测试，记录为模拟反馈')
    for action in ['apply','verify']:
        p=sub.add_parser(action); p.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.action=='plan':
            plan=make_plan(args.config,args.workspace,args.run_dir,args.provider,args.organization)
            print('计划已生成，等待审阅：'+str(args.run_dir/'execution-plan.md'))
            print('计划编号：'+plan['id'])
        elif args.action=='approve':
            approve(args.run_dir,args.reviewer,args.accept,args.simulated); print('确认已记录。')
        elif args.action=='apply':
            report=apply(args.run_dir); print('执行与验证：'+report['status'])
        elif args.action=='verify':
            record=args.run_dir/'approval-record.json'
            report=verify(load_plan(args.run_dir),read_json(record) if record.is_file() else None); save(args.run_dir/'verification-report.json',report)
            print('验证：'+report['status']); return 0 if report['status']=='passed' else 1
        else: parser.print_help()
        return 0
    except (WorkflowError, ValueError, OSError, yaml.YAMLError) as exc:
        print('已暂停：'+str(exc),file=sys.stderr); return 1

if __name__=='__main__':
    raise SystemExit(cli())
