"""Read-only public GitHub observations. A 404 never proves a name is available."""
import base64
from datetime import datetime, timezone
import json
import time
import threading
observer=threading.local()
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

def now():
    return datetime.now(timezone.utc).isoformat()

def _get_once(path):
    try:
        request=Request('https://api.github.com/'+path,headers={'Accept':'application/vnd.github+json','User-Agent':'second-brain-init-readonly'})
        with urlopen(request,timeout=12) as response:
            raw=response.read(2_000_001)
        if len(raw)>2_000_000:return {'status':'unknown','reason':'返回内容过大，调查不完整。'}
        return {'status':'ok','data':json.loads(raw)}
    except HTTPError as exc:
        reason={404:'未发现公开资源，可能不存在或不可见，不能证明名称可用。',403:'访问被拒绝或请求限流，不能判定资源不存在。',401:'需要身份授权。',429:'请求限流，请稍后重新调查。'}.get(exc.code,'GitHub 服务请求失败。')
        return {'status':'unknown','http_status':exc.code,'reason':reason}
    except (URLError,TimeoutError,OSError,ValueError):
        return {'status':'unknown','reason':'网络失败或响应无效，请重新调查。'}

def get(path):
    # Retry only transient read failures; never bypass unknown/changed rule gates.
    for attempt in range(3):
        callback=getattr(observer,'callback',None)
        parts=path.split('/')
        event={'tool':'github-public-api','operation':'GET','target':'/'.join(parts[1:3]) if parts[0]=='repos' else None,'stage':'survey','attempt':attempt+1,'started_at':now(),'status':'running'}
        if callback:callback(dict(event))
        result = _get_once(path)
        event.update(status='passed' if result['status']=='ok' else 'unknown',finished_at=now(),http_status=result.get('http_status'),reason=result.get('reason'))
        if callback:callback(event)
        if result['status'] == 'ok' or result.get('http_status') not in (None, 500, 502, 503, 504):
            return result
        if attempt < 2:
            time.sleep(0.3 * (attempt + 1))
    return result

def text_file(owner,repo,path,ref=None):
    result=get('repos/'+owner+'/'+repo+'/contents/'+path+('?ref='+quote(ref,safe='') if ref else ''))
    if result['status']!='ok':return result
    data=result['data']
    if not isinstance(data,dict) or data.get('encoding')!='base64':return {'status':'unknown','reason':'资源不是可读取的文本文件。'}
    try:return {'status':'ok','sha':data['sha'],'text':base64.b64decode(data['content'],validate=False).decode('utf-8')}
    except (KeyError,ValueError,UnicodeError):return {'status':'unknown','reason':'文件内容无法解码。'}

def inspect(organization,names,source,root='quanttide'):
    report={'started_at':now(),'organization':organization,'access':'仅公开、未登录的只读调查','scope':'总入口 '+root+' 与本次目标仓库；不是组织全部仓库或持续监控。','repositories':[],'documents':{},'rules':{'adopted':source}}
    for name in names:
        row={'name':name,'url':'https://github.com/'+organization+'/'+name,'checked_at':now()}
        info=get('repos/'+organization+'/'+name)
        if info['status']!='ok':row.update(status='unknown',reason=info['reason'],http_status=info.get('http_status'))
        else:
            data=info['data'];row.update(status='exists',default_branch=data['default_branch'],action='已找到总入口，当前仅查看，未修改' if name==root else '冲突：已有仓库，网页新建不会复用')
            head=get('repos/'+organization+'/'+name+'/commits/'+quote(data['default_branch'],safe=''))
            if head['status']=='ok':row['commit']=head['data']['sha']
            else:row.update(version_status='unknown',reason=head['reason'])
        report['repositories'].append(row)
    root_row=next((r for r in report['repositories'] if r['name']==root),{})
    if root_row.get('commit'):
        for path in ('README.md','domains/README.md','.gitmodules'):
            report['documents'][path]=text_file(organization,root,path,root_row['commit'])
    owner,repo=source['repository'].split('/')
    adopted=text_file(owner,repo,source['path'],source['commit'])
    latest=text_file(owner,repo,source['path'])
    report['rules'].update(adopted_file=adopted,latest_file=latest,status=('same' if adopted['sha']==latest['sha'] else 'changed') if adopted['status']==latest['status']=='ok' else 'unknown')
    report['finished_at']=now()
    report['note']='时间戳表示这次观察的时间；各请求不是原子快照。404 与失败不代表名称可用，创建仍需独立方案及执行前复核。'
    return report


def rules_error(rules):
    """Keep an unavailable observation distinct from a confirmed content change."""
    if rules.get('status') == 'same':
        return ''
    if rules.get('status') == 'changed':
        return '已确认在线章程内容与插件采用版本不同。请维护者审阅差异并更新规则后再生成方案。'
    reasons = []
    for key, label in (('adopted_file', '采用版本'), ('latest_file', '在线版本')):
        item = rules.get(key, {})
        if item.get('status') != 'ok' or not item.get('sha'):
            reasons.append(label + '：' + item.get('reason', '未取得可核对的文件版本。') +
                           ('（HTTP ' + str(item['http_status']) + '）' if item.get('http_status') else ''))
    return '暂时无法读取章程，尚不能判断规则是否变化。' + '；'.join(reasons) + ' 请稍后重试；若尚未生成方案，返回填写后重新生成。持续失败时导出诊断包。'


def rules_diagnostic(rules):
    result = {key: rules.get(key) for key in ('status', 'adopted')}
    for key in ('adopted_file', 'latest_file'):
        result[key] = {k: v for k, v in rules.get(key, {}).items()
                       if k in ('status', 'sha', 'reason', 'http_status')}
    return result
