"""Real local Git plus fault injection; never writes to GitHub."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import test_recovery

e=test_recovery.e
ui=test_recovery.ui

class PushRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.provider=e.Provider(self.tmp.name)
        self.name='project-arbitrary-789';self.provider.ensure(self.name,True,'test')
        self.repo=self.provider.repo(self.name)
        (self.repo/'content.txt').write_text('approved content')
        e.git(self.repo,'add','content.txt');e.git(self.repo,'commit','-m','approved content')
        self.head=e.git(self.repo,'rev-parse','HEAD').stdout.strip()
        e.request_observer.http1=False
        self.addCleanup(setattr,e.request_observer,'http1',False)

    def test_lost_response_is_verified_without_second_push(self):
        original=e.git;pushes=[]
        def interrupted(repo,*args,**kw):
            result=original(repo,*args,**kw)
            if args[0]=='push':
                pushes.append(args);raise e.WorkflowError('连接中断或超时')
            return result
        with patch.object(e,'git',interrupted):self.provider.push_verified(self.name,'main')
        self.assertEqual(len(pushes),1)
        self.assertEqual(self.provider.head(self.name),self.head)
        self.assertEqual(e.git(self.repo,'rev-parse','HEAD').stdout.strip(),self.head)

    def test_connection_failure_retries_same_commit_with_compatibility(self):
        original=e.git;attempts=[]
        def interrupted(repo,*args,**kw):
            if args[0]=='push':
                attempts.append((args,e.request_observer.http1))
                if len(attempts)==1:raise e.WorkflowError('连接中断或超时')
            return original(repo,*args,**kw)
        with patch.object(e,'git',interrupted),patch.object(e.time,'sleep'):
            self.provider.push_verified(self.name,'main')
        self.assertEqual(len(attempts),2)
        self.assertEqual(attempts[0][0],attempts[1][0])
        self.assertTrue(attempts[1][1])
        self.assertEqual(self.provider.head(self.name),self.head)

    def test_persistent_outage_has_three_attempt_bound_and_keeps_commit(self):
        original=e.git;pushes=[]
        def interrupted(repo,*args,**kw):
            if args[0]=='push':pushes.append(args);raise e.WorkflowError('连接中断或超时')
            return original(repo,*args,**kw)
        with patch.object(e,'git',interrupted),patch.object(e.time,'sleep'):
            with self.assertRaisesRegex(e.WorkflowError,'3 次'):self.provider.push_verified(self.name,'main')
        self.assertEqual(len(pushes),3)
        self.assertEqual(e.git(self.repo,'rev-parse','HEAD').stdout.strip(),self.head)
        self.assertEqual(e.git(self.repo,'status','--porcelain').stdout,'')

    def test_unknown_remote_after_failure_cannot_license_retry(self):
        original=e.git;pushes=[];head=self.provider.head
        def interrupted(repo,*args,**kw):
            if args[0]=='push':pushes.append(args);raise e.WorkflowError('连接中断或超时')
            return original(repo,*args,**kw)
        def read(*args,**kw):
            if pushes:raise e.RemoteReadError('远端无法读取')
            return head(*args,**kw)
        with patch.object(e,'git',interrupted),patch.object(self.provider,'head',read):
            with self.assertRaises(e.RemoteReadError):self.provider.push_verified(self.name,'main')
        self.assertEqual(len(pushes),1)

    def test_concurrent_remote_change_blocks_second_push(self):
        original=e.git;pushes=[]
        other=Path(self.tmp.name)/'other';e.command(['git','clone',self.provider.remote(self.name),other])
        e.git(other,'config','user.name','Other');e.git(other,'config','user.email','other@example.invalid')
        (other/'other.txt').write_text('other author');e.git(other,'add','.');e.git(other,'commit','-m','other')
        otherhead=e.git(other,'rev-parse','HEAD').stdout.strip()
        def interrupted(repo,*args,**kw):
            if args[0]=='push':
                pushes.append(args);original(other,'push','origin','HEAD:main')
                raise e.WorkflowError('连接中断或超时')
            return original(repo,*args,**kw)
        with patch.object(e,'git',interrupted):
            with self.assertRaisesRegex(e.WorkflowError,'远端提交已变化'):self.provider.push_verified(self.name,'main')
        self.assertEqual(len(pushes),1);self.assertEqual(self.provider.head(self.name),otherhead)

    def test_changed_push_destination_blocks_write(self):
        e.git(self.repo,'config','remote.origin.pushurl','https://github.com/other/repo.git')
        with self.assertRaisesRegex(e.WorkflowError,'推送目标已变化'):self.provider.push_verified(self.name,'main')

class StatusRecoveryTests(unittest.TestCase):
    def test_connection_notice_cannot_hide_execution_failure(self):
        log={'error':'current push failure','first_error':'old mount failure'}
        self.assertEqual(ui.current_failure({'error':'连接检测完成，请查看三项结果'},log),'current push failure')
        self.assertEqual(ui.current_failure({'error':'new preflight drift'},log),'new preflight drift')

    def test_compatible_plan_drift_and_lock_override_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);e.save(folder/'approval-record.json',{'accepted':True})
            plan={'operations':[{},{}],'engine_sha256':e.engine_sha256()}
            for reason in ['文件内容已变化','残留锁','认证或权限受限']:
                with self.subTest(reason=reason):
                    result=ui.recovery_guidance(folder,{'status':'paused','error':reason},plan,{'completed':['001']},[])
                    self.assertEqual(result['action'],'diagnostics' if '已变化' in reason else 'resume')

    def test_connection_check_preserves_current_error_when_api_passes_git_fails(self):
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            studio=ui.Studio(tmp,test_mode=True);folder=Path(tmp)/'runs'/('a'*16);folder.mkdir(parents=True)
            plan={'provider':'github','workspace':tmp,'organization':'Owner','names':['project'],
                  'config':{'root_repo':'project'}}
            e.save(folder/'execution-plan.json',plan)
            e.save(folder/'ui.json',{'status':'paused','error':'current push failure'})
            e.save(folder/'execution-log.json',{'error':'current push failure','first_error':'old mount failure'})
            def synchronous(_folder,fn):fn()
            with patch.object(studio,'spawn',synchronous),patch.object(e,'load_plan',return_value=plan),patch.object(e,'check_identity'),patch.object(e.Provider,'head',return_value='abc'),patch.object(e,'clone_isolated',side_effect=e.WorkflowError('连接中断或超时')):
                studio.connection_task('a'*16)
            meta=e.read_json(folder/'ui.json');report=e.read_json(folder/'connection-check.json')
            self.assertEqual(meta['status'],'paused');self.assertEqual(meta['error'],'current push failure')
            self.assertEqual([r['status'] for r in report['checks']],['passed','passed','unknown'])
            self.assertTrue(report['finished_at'])

    def test_worker_remembers_run_transport_without_global_config(self):
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            studio=ui.Studio(tmp,test_mode=True);folder=Path(tmp)/'runs'/('a'*16);folder.mkdir(parents=True)
            e.save(folder/'requests.json',[{'tool':'git','target':'Owner/project','category':'connection'}])
            seen=[];done=threading.Event()
            studio.spawn(folder,lambda:(seen.append(e.request_observer.http1),done.set()))
            self.assertTrue(done.wait(5));self.assertEqual(seen,[True])

if __name__=='__main__':unittest.main()
