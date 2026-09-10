"""GitHub transport is simulated; commits, pushes and submodules use real local Git.
No GitHub account login or public repository creation is claimed by these tests.
"""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from test_ui import BASE, ui

e=ui.e
IDENTITY={'login':'BlackCat205','id':205,'owner':'BlackCat205','owner_id':205,'owner_type':'User'}

class GithubUnitTests(unittest.TestCase):
    def test_owner_is_separate_from_domain_slug(self):
        self.assertEqual(e.github_owner('BlackCat205'),'BlackCat205')
        with self.assertRaises(e.WorkflowError):e.slug('BlackCat205')
        for name in ['../org','a/b','-a','a--b','a'*40]:
            with self.assertRaises(e.WorkflowError):e.github_owner(name)

    def test_personal_and_organization_route(self):
        for kind,endpoint in [('User','user/repos'),('Organization','orgs/Example/repos')]:
            with tempfile.TemporaryDirectory() as temp:
                provider=e.Provider(temp,'github','Example')
                with patch.object(provider,'info',return_value={'exists':False}),patch.object(e,'github_identity',return_value=dict(IDENTITY,owner_type=kind,owner='Example')),patch.object(e,'command',side_effect=e.WorkflowError('stop-after-post')) as command:
                    with self.assertRaisesRegex(e.WorkflowError,'stop-after-post'):provider.ensure('test',True,'test',True)
                    args=command.call_args.args[0];self.assertIn(endpoint,args);self.assertIn('POST',args)

    def test_git_credentials_are_process_scoped(self):
        with patch.object(e.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')) as run:
            e.command(['git','ls-remote','https://github.com/BlackCat205/test.git'])
            env=run.call_args.kwargs['env']
            keys=[(env['GIT_CONFIG_KEY_'+str(i)],env['GIT_CONFIG_VALUE_'+str(i)]) for i in range(int(env['GIT_CONFIG_COUNT']))]
            self.assertIn(('credential.https://github.com.helper','!gh auth git-credential'),keys)
            self.assertNotIn('--global',run.call_args.args[0])

    def test_pending_login_blocks_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio=ui.Studio(tmp,enable_github=True);studio.login.state={'status':'waiting'}
            with patch.object(e,'github_identity') as identity:
                with self.assertRaisesRegex(e.WorkflowError,'完成或取消'):studio.create(dict(BASE,provider='github',organization='BlackCat205'))
                identity.assert_not_called()
            self.assertFalse((Path(tmp)/'runs').exists())

    def test_other_personal_account_rejected(self):
        users=[{'login':'BlackCat205','id':205,'type':'User'},{'login':'Other','id':999,'type':'User'}]
        with patch.object(e,'command',side_effect=[subprocess.CompletedProcess([],0,json.dumps(x),'') for x in users]):
            with self.assertRaisesRegex(e.WorkflowError,'不能写入其他个人账号'):e.github_identity('Other')

    def test_account_change_stops_before_execution(self):
        plan={'provider':'github','organization':'BlackCat205','github_identity':IDENTITY}
        with patch.object(e,'github_identity',return_value=dict(IDENTITY,id=999)):
            with self.assertRaisesRegex(e.WorkflowError,'账号或目标归属已变化'):e.check_identity(plan)

    def test_redirected_repo_rejected(self):
        data={'visibility':'public','full_name':'other/test'}
        with patch.object(e,'command',return_value=subprocess.CompletedProcess([],0,json.dumps(data),'')):
            with self.assertRaisesRegex(e.WorkflowError,'重定向'):e.Provider('/tmp/test','github','BlackCat205').info('test')

    def test_login_extracts_only_device_code(self):
        login=ui.Login()
        class Process:
            stdin=io.BytesIO()
            stdout=io.BytesIO(b'! First copy your one-time code: ABCD-1234\nsecret-output-should-not-be-saved\n')
            def wait(self):return 1
            def poll(self):return 1
        with patch('github_login.shutil.which',return_value='/fake/gh'),patch('github_login.subprocess.Popen',return_value=Process()),patch.dict(os.environ,{'GH_TOKEN':'','GITHUB_TOKEN':''}):
            login.start()
            for _ in range(100):
                if login.status()['status']!='waiting':break
                time.sleep(.01)
            self.assertEqual(login.status()['status'],'failed')
            self.assertNotIn('secret-output',json.dumps(login.status()))

    def test_unauthed_login_missing_cli_is_actionable(self):
        with patch('github_login.shutil.which',return_value=None):
            self.assertEqual(ui.Login().inspect()['status'],'missing')

class LocalGithubTransport:
    def __init__(self,path):
        self.path=path;self.owner='BlackCat205';self.mutations=[];self.clones=[];self.commands=[];self.real=e.command
    def command(self,args,cwd=None,check=True):
        args=list(map(str,args))
        self.commands.append(list(args))
        if args[0]=='gh':
            if args[1:]==['auth','status']:return subprocess.CompletedProcess(args,0,'','')
            if args[1]=='api':
                if args[2]=='user':data={'login':self.owner,'id':205,'type':'User'}
                elif args[2:4]==['--method','POST']:
                    assert args[4]=='user/repos',args
                    name=next(x[5:] for x in args if x.startswith('name='));remote=self.path/(name+'.git')
                    if remote.exists():raise e.WorkflowError('HTTP 422 simulated name conflict')
                    self.real(['git','init','--bare','--initial-branch=main',remote]);self.mutations.append(name);data={}
                elif args[2].startswith('repos/'+self.owner+'/'):
                    parts=args[2].split('/');name=parts[2];remote=self.path/(name+'.git')
                    if not remote.exists():return subprocess.CompletedProcess(args,1,'','gh: Not Found (HTTP 404)')
                    if len(parts)>3 and parts[3]=='commits':
                        found=self.real(['git','--git-dir',remote,'rev-parse',parts[4]],check=False)
                        if found.returncode:return subprocess.CompletedProcess(args,1,'','gh: Git Repository is empty. (HTTP 409)')
                        data={'sha':found.stdout.strip()}
                    elif len(parts)>5 and parts[3:6]==['git','ref','tags']:
                        found=self.real(['git','--git-dir',remote,'rev-parse','refs/tags/'+'/'.join(parts[6:])],check=False)
                        if found.returncode:return subprocess.CompletedProcess(args,1,'','gh: Not Found (HTTP 404)')
                        data={'object':{'sha':found.stdout.strip()}}
                    else:data={'id':name,'owner':{'id':205},'full_name':self.owner+'/'+name,'default_branch':'main','visibility':'public','permissions':{'push':True}}
                else:raise AssertionError(args)
                return subprocess.CompletedProcess(args,0,json.dumps(data),'')
        if args[0]=='git':
            if 'clone' in args:self.clones.append(args[-1])
            args=[x.replace('protocol.file.allow=never','protocol.file.allow=always') for x in args]
            args[1:1]=['-c','url.'+self.path.as_uri()+'/.insteadOf=https://github.com/'+self.owner+'/', '-c','protocol.file.allow=always']
        return self.real(args,cwd,check)
    def survey(self,owner,names,source,root='quanttide',inspection_paths=(),get_fn=None):
        rows=[]
        for name in names:
            remote=self.path/(name+'.git');commit=None
            if remote.exists():commit=self.real(['git','--git-dir',remote,'rev-parse','HEAD']).stdout.strip()
            rows.append({'name':name,'status':'exists' if remote.exists() else 'unknown','commit':commit,'http_status':200 if remote.exists() else 404})
        documents={}
        root_row=next((row for row in rows if row['name']==root),{})
        if root_row.get('commit'):
            remote=self.path/(root+'.git')
            for path in dict.fromkeys(('README.md','domains/README.md','.gitmodules',*inspection_paths)):
                found=self.real(['git','--git-dir',remote,'show',root_row['commit']+':'+path],check=False)
                documents[path]={'status':'ok','sha':'fixture-'+path,'text':found.stdout} if found.returncode==0 else {'status':'unknown','http_status':404,'reason':'fixture missing'}
        return {'rules':{'status':'same','adopted_file':{'sha':'fixture-rules'}},'repositories':rows,'documents':documents,'scope':'SIMULATED GITHUB TRANSPORT','started_at':e.now(),'finished_at':e.now()}

class GithubWorkflowTests(unittest.TestCase):
    def wait(self,studio,key):
        until=time.monotonic()+180
        while key in studio.active:
            if time.monotonic()>until:self.fail('worker timed out')
            time.sleep(.03)
        return studio.view(key)
    def test_four_domains_share_remote_root_without_redundant_mount_downloads(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);remotes=base/'bare';remotes.mkdir();transport=LocalGithubTransport(remotes)
            studio=ui.Studio(base/'studio',enable_github=True)
            real_which=e.shutil.which
            with patch.object(e,'command',side_effect=transport.command),patch.object(e.shutil,'which',side_effect=lambda name: '/fake/gh' if name=='gh' else real_which(name)),patch.object(ui.survey,'inspect',side_effect=transport.survey),patch.object(ui.survey,'text_file',return_value={'status':'ok','sha':'fixture-rules'}):
                domains=[('firsttrial','new'),('secondtrial','existing'),('thirdtrial','existing'),('fourthtrial','existing')]
                for short,mode in domains:
                    payload=dict(BASE,short_name=short,english_name=short+'-engineering',provider='github',organization='BlackCat205',root_repo='second-brain-test',root_mode=mode)
                    clones_before_plan=len(transport.clones)
                    key=studio.create(payload)['id'];view=self.wait(studio,key)
                    self.assertEqual(view['status'],'review',view.get('error'));self.assertEqual(view['completed'],0)
                    self.assertEqual(len(transport.clones),clones_before_plan,'UI planning must not clone an existing root')
                    if mode=='new':self.assertFalse(transport.mutations)
                    studio.execute(key,{'plan_id':view['plan']['id'],'confirmed':True,'reviewer':'自动测试：GitHub 接口模拟','github_confirmation':'BlackCat205'})
                    view=self.wait(studio,key);self.assertEqual(view['status'],'completed',(view.get('error'),view.get('report')));self.assertTrue(view['report']['technical_passed'])
                    self.assertEqual(view['completed'],27)
                    self.assertTrue(any(x['status']=='running' for x in view['events']))
                    self.assertTrue(all(x['commit'] for x in view['report']['repositories']))
                    self.assertIn('https://github.com/BlackCat205/second-brain-test',studio.export(key))
                    if mode=='new':
                        count=len(transport.mutations)
                        studio.connection_task(key);view=self.wait(studio,key)
                        self.assertEqual(view['status'],'completed')
                        self.assertEqual([x['status'] for x in view['connection_check']['checks']],
                                         ['passed','passed','passed'])
                        self.assertEqual(len(transport.mutations),count)
                self.assertEqual(transport.mutations.count('second-brain-test'),1)
                self.assertEqual(len(transport.mutations),29)
                root=Path(view['plan']['workspace'])/'repositories/second-brain-test'
                expected={'domains/quanttide-'+short for short,_ in domains}
                self.assertEqual(set(e.modules(root)),expected)
                for name,_ in domains:self.assertIn('quanttide-'+name,e.text_at(root,'domains/README.md'))
                network_submodules=[args for args in transport.commands if args[0]=='git' and 'submodule' in args and any(value.startswith('https://github.com/') for value in args)]
                self.assertFalse(network_submodules,'planned mounts must reuse verified local repositories')
                # Existing generated names must stop the plan before any further create request.
                count=len(transport.mutations)
                key=studio.create(payload)['id'];blocked=self.wait(studio,key)
                self.assertEqual(blocked['status'],'paused');self.assertEqual(len(transport.mutations),count)

if __name__=='__main__':unittest.main()
